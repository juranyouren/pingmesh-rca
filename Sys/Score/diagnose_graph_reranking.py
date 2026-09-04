from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.RootCauseAnalyze.propagation.m1 import reconstruct_hypothesis_graph
from Sys.RootCauseAnalyze.propagation.m2 import infer_root_paths
from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig
from Sys.RootCauseAnalyze.propagation.topology_context import load_topology_context
from Sys.RootCauseAnalyze.stage1.neural_graph import (
    RawCase,
    load_raw_cases,
    load_training_label,
)
from Sys.utils.io_utils import load_json, save_json


DIAGNOSTIC_VERSION = "graph-rerank-signal-diagnostic-v1"
SCORE_METHODS = (
    "legacy_explanation_score",
    "solver_graph_score",
    "target_coverage",
    "edge_direction_preference",
    "target_path_support",
    "structured_reasonableness",
)
DEFAULT_THRESHOLDS = (0.0, 0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30)
BOOTSTRAP_SEED = 20260904
BOOTSTRAP_SAMPLES = 2000


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _mean(values: Sequence[float], default: float = 0.0) -> float:
    return sum(values) / len(values) if values else default


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = max(0.0, min(1.0, percentile)) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _bootstrap_mean_interval(
    values: Sequence[float], *, seed_offset: int
) -> Dict[str, float]:
    """Incident-level percentile interval; candidates are never resampled alone."""

    if not values:
        return {"mean": 0.0, "ci95_low": 0.0, "ci95_high": 0.0}
    rng = random.Random(BOOTSTRAP_SEED + seed_offset)
    count = len(values)
    samples = [
        _mean([values[rng.randrange(count)] for _index in range(count)])
        for _sample in range(BOOTSTRAP_SAMPLES)
    ]
    return {
        "mean": round(_mean(values), 8),
        "ci95_low": round(_percentile(samples, 0.025), 8),
        "ci95_high": round(_percentile(samples, 0.975), 8),
    }


def _normalized_path(value: Any) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(value or ""))))


def _root_result_map(path: str) -> Dict[str, Dict[str, Any]]:
    records = load_json(path, default=None)
    if not isinstance(records, list):
        raise ValueError("root result file must contain a JSON list")
    result: Dict[str, Dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, Mapping) or not raw.get("dir"):
            continue
        key = _normalized_path(raw["dir"])
        if key in result:
            raise ValueError(f"duplicate root result path: {raw['dir']}")
        result[key] = dict(raw)
    return result


def _root_rankings(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    stage1 = record.get("stage1", {})
    for raw in (
        record.get("initial_root_rankings"),
        record.get("base_root_rankings"),
        stage1.get("root_rankings") if isinstance(stage1, Mapping) else None,
    ):
        if isinstance(raw, list):
            rankings = [dict(item) for item in raw if isinstance(item, Mapping)]
            if rankings:
                return rankings
    return []


def _root_ip(item: Mapping[str, Any]) -> str:
    root = item.get("root_hypothesis", {})
    devices = root.get("root_devices", []) if isinstance(root, Mapping) else []
    return str(devices[0]) if isinstance(devices, list) and devices else ""


def _edge_state_index(
    hypothesis_graph: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for pair in hypothesis_graph.get("edge_hypotheses", []):
        if not isinstance(pair, Mapping):
            continue
        hypothesis_id = str(pair.get("edge_hypothesis_id", "") or "")
        if not hypothesis_id:
            continue
        probabilities = pair.get("state_probabilities", {})
        result[hypothesis_id] = {
            "no_direct": (
                _safe_float(probabilities.get("no_direct_propagation"))
                if isinstance(probabilities, Mapping)
                and "no_direct_propagation" in probabilities
                else None
            ),
            "endpoint_a": str(pair.get("endpoint_a", "") or ""),
            "endpoint_b": str(pair.get("endpoint_b", "") or ""),
        }
    return result


def _interval_order_support(
    source_interval: Any, target_interval: Any
) -> float | None:
    if not (
        isinstance(source_interval, list)
        and len(source_interval) == 2
        and isinstance(target_interval, list)
        and len(target_interval) == 2
    ):
        return None
    source_start = _safe_float(source_interval[0])
    source_end = _safe_float(source_interval[1])
    target_start = _safe_float(target_interval[0])
    target_end = _safe_float(target_interval[1])
    if source_end <= target_start:
        return 1.0
    if source_start <= target_end:
        return 0.5
    return 0.0


def _edge_diagnostics(
    graph: Mapping[str, Any],
    edge_states: Mapping[str, Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[Tuple[str, str], Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    by_direction: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for edge in graph.get("edges", []):
        if not isinstance(edge, Mapping):
            continue
        source = str(edge.get("from", "") or "")
        target = str(edge.get("to", "") or "")
        if not source or not target:
            continue
        hypothesis_id = str(edge.get("edge_hypothesis_id", "") or "")
        state = edge_states.get(hypothesis_id, {})
        direction_probability = max(
            0.0,
            min(
                1.0,
                _safe_float(
                    edge.get("state_probability", edge.get("support_score", 0.0))
                ),
            ),
        )
        no_direct_raw = state.get("no_direct")
        no_direct = (
            max(0.0, min(1.0, _safe_float(no_direct_raw)))
            if no_direct_raw is not None
            else None
        )
        if no_direct is None:
            log_odds = None
            direction_preference = None
        else:
            log_odds = max(
                -8.0,
                min(
                    8.0,
                    math.log(direction_probability + 1e-8)
                    - math.log(no_direct + 1e-8),
                ),
            )
            direction_preference = direction_probability / (
                direction_probability + no_direct + 1e-8
            )
        features = edge.get("features", {})
        features = features if isinstance(features, Mapping) else {}
        temporal_available = bool(features.get("temporal_available", False))
        temporal_support = (
            _safe_float(
                features.get(
                    "temporal_order_support",
                    features.get("temporal_compatibility", 0.0),
                )
            )
            if temporal_available
            else None
        )
        contradiction = max(
            _safe_float(features.get("case_contradiction", 0.0)),
            _safe_float(features.get("contradiction", 0.0)),
        )
        row = {
            "from": source,
            "to": target,
            "edge_hypothesis_id": hypothesis_id,
            "direction_probability": direction_probability,
            "no_direct_probability": no_direct,
            "direction_log_odds": log_odds,
            "direction_preference": direction_preference,
            "temporal_support": temporal_support,
            "contradiction": contradiction,
            "grounded": bool(edge.get("evidence_ids")),
            "weak": str(edge.get("support_level", "")) == "weak",
        }
        rows.append(row)
        by_direction[(source, target)] = row
    return rows, by_direction


def _target_ids(graph: Mapping[str, Any]) -> List[str]:
    diagnostics = graph.get("diagnostics", {})
    diagnostics = diagnostics if isinstance(diagnostics, Mapping) else {}
    values = {
        str(value)
        for value in graph.get("covered_targets", [])
        if value
    }
    values.update(
        str(value)
        for value in diagnostics.get("uncovered_targets", [])
        if value
    )
    return sorted(values)


def _path_quality(path: Sequence[Mapping[str, Any]]) -> float:
    if not path:
        return 1.0
    preferences = [
        (
            float(edge["direction_preference"])
            if edge.get("direction_preference") is not None
            else 0.5
        )
        for edge in path
    ]
    geometric = math.exp(
        _mean([math.log(max(value, 1e-8)) for value in preferences])
    )
    length_penalty = math.exp(-0.08 * max(0, len(path) - 1))
    return geometric * length_penalty


def _best_path(
    roots: Sequence[str],
    target: str,
    edge_by_direction: Mapping[Tuple[str, str], Mapping[str, Any]],
    *,
    max_depth: int,
) -> Tuple[float, int | None]:
    if target in set(roots):
        return 1.0, 0
    outgoing: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for (source, _target), edge in edge_by_direction.items():
        outgoing[source].append(edge)
    best_quality = 0.0
    best_hops: int | None = None
    stack: List[Tuple[str, List[Mapping[str, Any]], frozenset[str]]] = [
        (root, [], frozenset({root})) for root in sorted(set(roots))
    ]
    while stack:
        node, path, visited = stack.pop()
        if len(path) >= max_depth:
            continue
        for edge in outgoing.get(node, []):
            neighbor = str(edge.get("to", "") or "")
            if not neighbor or neighbor in visited:
                continue
            next_path = [*path, edge]
            if neighbor == target:
                quality = _path_quality(next_path)
                if quality > best_quality:
                    best_quality = quality
                    best_hops = len(next_path)
            else:
                stack.append((neighbor, next_path, visited | {neighbor}))
    return best_quality, best_hops


def score_candidate_graph(
    *,
    root_item: Mapping[str, Any],
    hypothesis_graph: Mapping[str, Any],
    max_path_depth: int,
) -> Dict[str, Any]:
    """Return label-free graph evidence components for one candidate root."""

    graph = root_item.get("propagation_graph", {})
    graph = graph if isinstance(graph, Mapping) else {}
    root_ip = _root_ip(root_item)
    edge_rows, edge_by_direction = _edge_diagnostics(
        graph, _edge_state_index(hypothesis_graph)
    )
    targets = _target_ids(graph)
    path_qualities: List[float] = []
    path_hops: List[int] = []
    for target in targets:
        quality, hops = _best_path(
            [root_ip], target, edge_by_direction, max_depth=max_path_depth
        )
        path_qualities.append(quality)
        if hops is not None:
            path_hops.append(hops)

    preferences = [
        float(edge["direction_preference"])
        for edge in edge_rows
        if edge.get("direction_preference") is not None
    ]
    log_odds = [
        float(edge["direction_log_odds"])
        for edge in edge_rows
        if edge.get("direction_log_odds") is not None
    ]
    temporal = [
        float(edge["temporal_support"])
        for edge in edge_rows
        if edge.get("temporal_support") is not None
    ]
    node_rows = [
        node for node in graph.get("nodes", []) if isinstance(node, Mapping)
    ]
    node_by_id = {
        str(node.get("device_id", "")): node
        for node in node_rows
        if node.get("device_id")
    }
    edge_onset_support = []
    for edge in edge_rows:
        source_node = node_by_id.get(str(edge["from"]), {})
        target_node = node_by_id.get(str(edge["to"]), {})
        support = _interval_order_support(
            source_node.get("onset_interval_ms"),
            target_node.get("onset_interval_ms"),
        )
        if support is not None:
            edge_onset_support.append(support)

    root_onset_support = []
    root_node = node_by_id.get(root_ip, {})
    for device_id, node in node_by_id.items():
        if device_id == root_ip:
            continue
        support = _interval_order_support(
            root_node.get("onset_interval_ms"),
            node.get("onset_interval_ms"),
        )
        if support is not None:
            root_onset_support.append(support)

    diagnostics = graph.get("diagnostics", {})
    diagnostics = diagnostics if isinstance(diagnostics, Mapping) else {}
    target_coverage = max(
        0.0, min(1.0, _safe_float(graph.get("target_coverage", 0.0)))
    )
    edge_direction_preference = _mean(preferences, 0.5 if edge_rows else 0.0)
    target_path_support = _mean(path_qualities, 0.0)
    temporal_consistency = _mean(temporal, 0.5)
    edge_onset_consistency = _mean(edge_onset_support, 0.5)
    root_earliness = _mean(root_onset_support, 0.5)
    grounded_edge_ratio = _mean(
        [float(bool(edge["grounded"])) for edge in edge_rows], 0.0
    )
    weak_edge_ratio = _mean(
        [float(bool(edge["weak"])) for edge in edge_rows], 0.0
    )
    contradiction_score = max(
        [float(edge["contradiction"]) for edge in edge_rows], default=0.0
    )
    node_evidence_coverage = _mean(
        [float(bool(node.get("evidence_ids"))) for node in node_rows], 0.0
    )
    mean_path_hops = _mean([float(value) for value in path_hops], 0.0)
    path_length_penalty = min(
        mean_path_hops / max(1.0, float(max_path_depth)), 1.0
    )

    structured_reasonableness = (
        0.30 * target_path_support
        + 0.20 * target_coverage
        + 0.15 * edge_direction_preference
        + 0.10 * temporal_consistency
        + 0.10 * root_earliness
        + 0.10 * grounded_edge_ratio
        + 0.05 * node_evidence_coverage
        - 0.10 * weak_edge_ratio
        - 0.10 * contradiction_score
        - 0.05 * path_length_penalty
    )
    explanation_score = _safe_float(root_item.get("explanation_score", 0.0))
    graph_score = _safe_float(graph.get("graph_score", 0.0))
    scores = {
        "legacy_explanation_score": explanation_score,
        "solver_graph_score": graph_score,
        "target_coverage": target_coverage,
        "edge_direction_preference": edge_direction_preference,
        "target_path_support": target_path_support,
        "structured_reasonableness": structured_reasonableness,
    }
    components = {
        "target_count": len(targets),
        "covered_target_count": len(graph.get("covered_targets", [])),
        "selected_edge_count": len(edge_rows),
        "selected_node_count": len(node_rows),
        "target_coverage": target_coverage,
        "edge_direction_preference": edge_direction_preference,
        "mean_direction_log_odds": _mean(log_odds, 0.0),
        "target_path_support": target_path_support,
        "minimum_target_path_support": min(path_qualities, default=0.0),
        "mean_path_hops": mean_path_hops,
        "temporal_consistency": temporal_consistency,
        "temporal_evidence_ratio": len(temporal) / len(edge_rows) if edge_rows else 0.0,
        "edge_onset_consistency": edge_onset_consistency,
        "edge_onset_comparison_ratio": (
            len(edge_onset_support) / len(edge_rows) if edge_rows else 0.0
        ),
        "root_earliness": root_earliness,
        "root_onset_comparison_ratio": (
            len(root_onset_support) / max(1, len(node_rows) - 1)
        ),
        "grounded_edge_ratio": grounded_edge_ratio,
        "node_evidence_coverage": node_evidence_coverage,
        "weak_edge_ratio": weak_edge_ratio,
        "contradiction_score": contradiction_score,
        "path_length_penalty": path_length_penalty,
        "reachable_target_count": int(
            diagnostics.get("reachable_target_count", len(graph.get("covered_targets", [])))
            or 0
        ),
    }
    return {
        "root_ip": root_ip,
        "scores": {key: round(float(value), 8) for key, value in scores.items()},
        "components": {
            key: round(float(value), 8) if isinstance(value, float) else value
            for key, value in components.items()
        },
        "selected_edges": [
            {
                key: value
                for key, value in edge.items()
                if key
                in {
                    "from",
                    "to",
                    "direction_probability",
                    "no_direct_probability",
                    "direction_log_odds",
                    "direction_preference",
                    "temporal_support",
                    "contradiction",
                    "grounded",
                    "weak",
                }
            }
            for edge in edge_rows
        ],
    }


def _candidate_edge_set(candidate: Mapping[str, Any]) -> frozenset[Tuple[str, str]]:
    return frozenset(
        (str(edge.get("from", "")), str(edge.get("to", "")))
        for edge in candidate.get("selected_edges", [])
        if isinstance(edge, Mapping) and edge.get("from") and edge.get("to")
    )


def graph_diversity(candidates: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    distances: List[float] = []
    identical = 0
    for left_index, left in enumerate(candidates):
        left_edges = _candidate_edge_set(left)
        for right in candidates[left_index + 1 :]:
            right_edges = _candidate_edge_set(right)
            union = left_edges | right_edges
            similarity = (
                len(left_edges & right_edges) / len(union)
                if union
                else 1.0
            )
            distance = 1.0 - similarity
            distances.append(distance)
            identical += int(distance <= 1e-12)
    return {
        "pair_count": float(len(distances)),
        "mean_pairwise_jaccard_distance": _mean(distances, 0.0),
        "identical_graph_pair_ratio": (
            identical / len(distances) if distances else 0.0
        ),
    }


def build_case_diagnostics(
    cases: Sequence[RawCase],
    root_records: Mapping[str, Mapping[str, Any]],
    *,
    config: PropagationConfig,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for index, case in enumerate(cases, 1):
        record = root_records.get(_normalized_path(case.dirpath))
        if record is None:
            raise ValueError(f"root result is missing for case: {case.dirpath}")
        rankings = _root_rankings(record)[: config.root_top_k]
        if not rankings:
            raise ValueError(f"root ranking is empty for case: {case.dirpath}")
        topology_context = load_topology_context(
            case.dirpath, node_list=case.nodes, info=case.info
        )
        hypothesis_graph = reconstruct_hypothesis_graph(
            nodes=case.nodes,
            info=case.info,
            topology_context=topology_context,
            config=config,
        )
        inference = infer_root_paths(
            hypothesis_graph=hypothesis_graph,
            initial_root_rankings=rankings,
            config=config,
        )
        graph_items = {
            _root_ip(item): item
            for item in inference.get("root_conditioned_propagation_graphs", [])
            if isinstance(item, Mapping) and _root_ip(item)
        }
        candidates: List[Dict[str, Any]] = []
        for fallback_rank, ranking in enumerate(rankings, 1):
            ip = str(ranking.get("ip", ranking.get("device_id", "")) or "")
            if not ip or ip not in graph_items:
                continue
            scored = score_candidate_graph(
                root_item=graph_items[ip],
                hypothesis_graph=hypothesis_graph,
                max_path_depth=config.max_path_depth,
            )
            candidates.append(
                {
                    "ip": ip,
                    "initial_rank": int(
                        ranking.get("rank", fallback_rank) or fallback_rank
                    ),
                    "stage1_score": _safe_float(
                        ranking.get(
                            "combined_score",
                            ranking.get("neural_score", ranking.get("score", 0.0)),
                        )
                    ),
                    **scored,
                }
            )
        candidates.sort(key=lambda row: (int(row["initial_rank"]), str(row["ip"])))
        results.append(
            {
                "dir": case.dirpath,
                "initial_top1": candidates[0]["ip"] if candidates else None,
                "candidates": candidates,
                "graph_diversity": graph_diversity(candidates),
            }
        )
        if index % 20 == 0:
            print(f"Graph-rerank diagnostic: {index}/{len(cases)}")
    return results


def attach_ground_truth_after_graph_construction(
    cases: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Reveal labels only after every candidate graph and score already exists."""

    labeled: List[Dict[str, Any]] = []
    for case in cases:
        gt_ip = load_training_label(str(case.get("dir", "") or ""))
        if not gt_ip:
            raise ValueError(f"root label is missing for case: {case.get('dir')}")
        candidates = list(case.get("candidates", []))
        labeled.append(
            {
                **dict(case),
                "gt_ip": gt_ip,
                "candidate_recall": any(
                    str(candidate.get("ip", "")) == gt_ip
                    for candidate in candidates
                    if isinstance(candidate, Mapping)
                ),
            }
        )
    return labeled


def _initial_metrics(cases: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    total = len(cases)
    hits = {1: 0, 3: 0, 5: 0}
    reciprocal_rank = 0.0
    candidate_hits = 0
    for case in cases:
        gt = str(case.get("gt_ip", "") or "")
        candidates = case.get("candidates", [])
        ips = [str(candidate.get("ip", "")) for candidate in candidates]
        if gt in ips:
            candidate_hits += 1
            rank = ips.index(gt) + 1
            reciprocal_rank += 1.0 / rank
            for cutoff in hits:
                hits[cutoff] += int(rank <= cutoff)
    return {
        "case_count": total,
        "candidate_recall": round(candidate_hits / total, 6) if total else 0.0,
        "top1": round(hits[1] / total, 6) if total else 0.0,
        "top3": round(hits[3] / total, 6) if total else 0.0,
        "top5": round(hits[5] / total, 6) if total else 0.0,
        "mrr": round(reciprocal_rank / total, 6) if total else 0.0,
    }


def _threshold_curve(
    cases: Sequence[Mapping[str, Any]],
    method: str,
    thresholds: Sequence[float],
) -> List[Dict[str, Any]]:
    rows = []
    for threshold in thresholds:
        corrections = 0
        corruptions = 0
        reranked = 0
        final_correct = 0
        for case in cases:
            gt = str(case.get("gt_ip", "") or "")
            candidates = list(case.get("candidates", []))
            if not candidates:
                continue
            initial = candidates[0]
            best = sorted(
                candidates,
                key=lambda row: (
                    -_safe_float(row.get("scores", {}).get(method)),
                    int(row.get("initial_rank", 0) or 0),
                    str(row.get("ip", "")),
                ),
            )[0]
            advantage = _safe_float(best.get("scores", {}).get(method)) - _safe_float(
                initial.get("scores", {}).get(method)
            )
            promote = best.get("ip") != initial.get("ip") and advantage > threshold
            final_ip = str(best.get("ip")) if promote else str(initial.get("ip"))
            initial_correct = str(initial.get("ip")) == gt
            final_is_correct = final_ip == gt
            corrections += int(not initial_correct and final_is_correct)
            corruptions += int(initial_correct and not final_is_correct)
            reranked += int(promote)
            final_correct += int(final_is_correct)
        total = len(cases)
        rows.append(
            {
                "threshold": threshold,
                "top1": round(final_correct / total, 6) if total else 0.0,
                "reranked_cases": reranked,
                "corrections": corrections,
                "corruptions": corruptions,
                "net_corrections": corrections - corruptions,
            }
        )
    return rows


def evaluate_score_method(
    cases: Sequence[Mapping[str, Any]],
    method: str,
    *,
    tie_epsilon: float,
    thresholds: Sequence[float],
) -> Dict[str, Any]:
    total = len(cases)
    eligible = 0
    graph_top1 = 0
    graph_mrr = 0.0
    pair_wins = 0
    pair_ties = 0
    pair_losses = 0
    pair_differences: List[float] = []
    top_false_wins = 0
    top_false_ties = 0
    top_false_losses = 0
    top_candidate_credits: List[float] = []
    random_candidate_baselines: List[float] = []
    wrong_but_eligible = 0
    correctable = 0
    strict_correctable = 0
    wrong_case_ties = 0
    initial_correct = 0
    wrong_preference = 0
    no_variation = 0
    gt_vs_initial_differences: List[float] = []
    for case in cases:
        gt = str(case.get("gt_ip", "") or "")
        candidates = list(case.get("candidates", []))
        if not candidates:
            continue
        initial = candidates[0]
        initial_is_correct = str(initial.get("ip")) == gt
        initial_correct += int(initial_is_correct)
        scores = [_safe_float(row.get("scores", {}).get(method)) for row in candidates]
        no_variation += int(max(scores, default=0.0) - min(scores, default=0.0) <= tie_epsilon)
        candidate_by_ip = {str(row.get("ip", "")): row for row in candidates}
        gt_candidate = candidate_by_ip.get(gt)
        if gt_candidate is None:
            continue
        eligible += 1
        gt_score = _safe_float(gt_candidate.get("scores", {}).get(method))
        false_scores = [
            _safe_float(candidate.get("scores", {}).get(method))
            for candidate in candidates
            if str(candidate.get("ip")) != gt
        ]
        strongest_false = max(false_scores, default=float("-inf"))
        if gt_score > strongest_false + tie_epsilon:
            top_false_wins += 1
        elif gt_score < strongest_false - tie_epsilon:
            top_false_losses += 1
        else:
            top_false_ties += 1
        maximum_score = max(scores)
        maximum_tie_count = sum(
            abs(score - maximum_score) <= tie_epsilon for score in scores
        )
        top_candidate_credits.append(
            1.0 / maximum_tie_count
            if abs(gt_score - maximum_score) <= tie_epsilon
            else 0.0
        )
        random_candidate_baselines.append(1.0 / len(candidates))
        ordered = sorted(
            candidates,
            key=lambda row: (
                -_safe_float(row.get("scores", {}).get(method)),
                int(row.get("initial_rank", 0) or 0),
                str(row.get("ip", "")),
            ),
        )
        rank = next(
            index
            for index, row in enumerate(ordered, 1)
            if str(row.get("ip")) == gt
        )
        graph_top1 += int(rank == 1)
        graph_mrr += 1.0 / rank
        for candidate in candidates:
            if str(candidate.get("ip")) == gt:
                continue
            difference = gt_score - _safe_float(
                candidate.get("scores", {}).get(method)
            )
            pair_differences.append(difference)
            if difference > tie_epsilon:
                pair_wins += 1
            elif difference < -tie_epsilon:
                pair_losses += 1
            else:
                pair_ties += 1
        if not initial_is_correct:
            wrong_but_eligible += 1
            initial_score = _safe_float(initial.get("scores", {}).get(method))
            difference = gt_score - initial_score
            gt_vs_initial_differences.append(difference)
            correctable += int(difference > tie_epsilon)
            strict_correctable += int(gt_score > strongest_false + tie_epsilon)
            wrong_case_ties += int(abs(difference) <= tie_epsilon)
        else:
            challenger_scores = [
                _safe_float(candidate.get("scores", {}).get(method))
                for candidate in candidates[1:]
            ]
            wrong_preference += int(
                challenger_scores
                and max(challenger_scores) > gt_score + tie_epsilon
            )
    pair_count = pair_wins + pair_ties + pair_losses
    top_false_count = top_false_wins + top_false_ties + top_false_losses
    top_credit_lifts = [
        credit - baseline
        for credit, baseline in zip(
            top_candidate_credits, random_candidate_baselines
        )
    ]
    top_credit_lift_interval = _bootstrap_mean_interval(
        top_credit_lifts,
        seed_offset=sum((index + 1) * ord(char) for index, char in enumerate(method)),
    )
    curve = _threshold_curve(cases, method, thresholds)
    best_curve = max(
        curve,
        key=lambda row: (
            int(row["net_corrections"]),
            int(row["corrections"]),
            -int(row["corruptions"]),
            float(row["threshold"]),
        ),
    )
    return {
        "method": method,
        "case_count": total,
        "eligible_case_count": eligible,
        "graph_only_top1": round(graph_top1 / total, 6) if total else 0.0,
        "conditional_graph_only_top1": (
            round(graph_top1 / eligible, 6) if eligible else 0.0
        ),
        "graph_only_mrr": round(graph_mrr / total, 6) if total else 0.0,
        "pairwise_comparison_count": pair_count,
        "pairwise_win_rate": round(pair_wins / pair_count, 6) if pair_count else 0.0,
        "pairwise_tie_rate": round(pair_ties / pair_count, 6) if pair_count else 0.0,
        "tie_adjusted_pairwise_win_rate": (
            round((pair_wins + 0.5 * pair_ties) / pair_count, 6)
            if pair_count
            else 0.0
        ),
        "gt_vs_strongest_false_win_rate": (
            round(top_false_wins / top_false_count, 6)
            if top_false_count
            else 0.0
        ),
        "gt_vs_strongest_false_tie_rate": (
            round(top_false_ties / top_false_count, 6)
            if top_false_count
            else 0.0
        ),
        "gt_vs_strongest_false_loss_rate": (
            round(top_false_losses / top_false_count, 6)
            if top_false_count
            else 0.0
        ),
        "fractional_graph_best_accuracy": round(
            _mean(top_candidate_credits), 6
        ),
        "random_candidate_baseline": round(
            _mean(random_candidate_baselines), 6
        ),
        "fractional_graph_best_lift": top_credit_lift_interval,
        "mean_gt_minus_false_score": round(_mean(pair_differences, 0.0), 8),
        "median_gt_minus_false_score": round(
            statistics.median(pair_differences) if pair_differences else 0.0, 8
        ),
        "initial_top1_correct_cases": initial_correct,
        "stage1_wrong_but_gt_in_candidates": wrong_but_eligible,
        "correctable_cases": correctable,
        "correctable_rate": (
            round(correctable / wrong_but_eligible, 6)
            if wrong_but_eligible
            else 0.0
        ),
        "strict_graph_top1_correctable_cases": strict_correctable,
        "strict_graph_top1_correctable_rate": (
            round(strict_correctable / wrong_but_eligible, 6)
            if wrong_but_eligible
            else 0.0
        ),
        "wrong_case_score_ties": wrong_case_ties,
        "wrong_preference_cases": wrong_preference,
        "mean_gt_advantage_over_initial_wrong_top1": round(
            _mean(gt_vs_initial_differences, 0.0), 8
        ),
        "no_within_case_score_variation_rate": (
            round(no_variation / total, 6) if total else 0.0
        ),
        "threshold_sweep": curve,
        "best_in_sample_diagnostic_threshold": {
            **best_curve,
            "warning": "exploratory upper bound; do not report as held-out performance",
        },
    }


def _aggregate_diversity(cases: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    pair_count = sum(
        int(_safe_float(case.get("graph_diversity", {}).get("pair_count")))
        for case in cases
    )
    if not pair_count:
        return {
            "candidate_pair_count": 0,
            "mean_pairwise_jaccard_distance": 0.0,
            "identical_graph_pair_ratio": 0.0,
        }
    distance_sum = sum(
        _safe_float(
            case.get("graph_diversity", {}).get("mean_pairwise_jaccard_distance")
        )
        * int(_safe_float(case.get("graph_diversity", {}).get("pair_count")))
        for case in cases
    )
    identical_sum = sum(
        _safe_float(case.get("graph_diversity", {}).get("identical_graph_pair_ratio"))
        * int(_safe_float(case.get("graph_diversity", {}).get("pair_count")))
        for case in cases
    )
    return {
        "candidate_pair_count": pair_count,
        "mean_pairwise_jaccard_distance": round(distance_sum / pair_count, 6),
        "identical_graph_pair_ratio": round(identical_sum / pair_count, 6),
    }


def _diagnostic_verdict(
    methods: Sequence[Mapping[str, Any]], diversity: Mapping[str, Any]
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    diverse_enough = (
        _safe_float(diversity.get("mean_pairwise_jaccard_distance")) >= 0.05
        and _safe_float(diversity.get("identical_graph_pair_ratio")) < 0.95
    )
    for method in methods:
        lift = method.get("fractional_graph_best_lift", {})
        lift = lift if isinstance(lift, Mapping) else {}
        curve = method.get("threshold_sweep", [])
        positive_threshold_net = max(
            (
                int(row.get("net_corrections", 0) or 0)
                for row in curve
                if isinstance(row, Mapping)
                and _safe_float(row.get("threshold")) > 0.0
            ),
            default=0,
        )
        no_variation = _safe_float(
            method.get("no_within_case_score_variation_rate")
        )
        strong = (
            diverse_enough
            and _safe_float(lift.get("ci95_low")) > 0.0
            and positive_threshold_net > 0
            and no_variation < 0.5
        )
        weak = (
            diverse_enough
            and (
                _safe_float(lift.get("mean")) > 0.0
                or positive_threshold_net > 0
            )
            and no_variation < 0.8
        )
        grade = "strong" if strong else "weak" if weak else "none"
        rows.append(
            {
                "method": method.get("method"),
                "grade": grade,
                "fractional_best_lift_ci95_low": _safe_float(
                    lift.get("ci95_low")
                ),
                "best_positive_threshold_net_corrections": positive_threshold_net,
                "no_within_case_score_variation_rate": no_variation,
            }
        )
    grade_order = {"none": 0, "weak": 1, "strong": 2}
    best = max(
        rows,
        key=lambda row: (
            grade_order[str(row["grade"])],
            _safe_float(row["fractional_best_lift_ci95_low"]),
            int(row["best_positive_threshold_net_corrections"]),
        ),
        default=None,
    )
    best_grade = str(best["grade"]) if best else "none"
    conclusion = {
        "strong": "promising_signal_proceed_to_grouped_oof_calibration",
        "weak": "weak_exploratory_signal_validate_before_training",
        "none": "no_reranking_evidence_from_current_graph_and_scores",
    }[best_grade]
    return {
        "conclusion": conclusion,
        "best_method": best.get("method") if best else None,
        "best_grade": best_grade,
        "candidate_graphs_diverse_enough": diverse_enough,
        "method_checks": rows,
        "rule": (
            "strong requires non-degenerate candidate graphs, a positive 95% "
            "incident-bootstrap lift over the random-candidate baseline, and "
            "positive net corrections at a nonzero exploratory threshold"
        ),
        "scope_warning": (
            "none means the current graph constructor and tested label-free scores "
            "show no evidence; it does not disprove propagation-graph reranking in general"
        ),
    }


def _write_candidate_csv(cases: Sequence[Mapping[str, Any]], path: str) -> None:
    fields = [
        "dir",
        "gt_ip",
        "ip",
        "initial_rank",
        "stage1_score",
        *SCORE_METHODS,
        "selected_edge_count",
        "target_count",
        "target_coverage",
        "target_path_support",
        "mean_direction_log_odds",
        "temporal_consistency",
        "root_earliness",
        "grounded_edge_ratio",
        "weak_edge_ratio",
        "contradiction_score",
    ]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            for candidate in case.get("candidates", []):
                scores = candidate.get("scores", {})
                components = candidate.get("components", {})
                writer.writerow(
                    {
                        "dir": case.get("dir"),
                        "gt_ip": case.get("gt_ip"),
                        "ip": candidate.get("ip"),
                        "initial_rank": candidate.get("initial_rank"),
                        "stage1_score": candidate.get("stage1_score"),
                        **{method: scores.get(method) for method in SCORE_METHODS},
                        **{
                            key: components.get(key)
                            for key in fields
                            if key in components
                        },
                    }
                )


def _write_method_csv(methods: Sequence[Mapping[str, Any]], path: str) -> None:
    fields = [
        "method",
        "graph_only_top1",
        "conditional_graph_only_top1",
        "graph_only_mrr",
        "pairwise_win_rate",
        "pairwise_tie_rate",
        "tie_adjusted_pairwise_win_rate",
        "gt_vs_strongest_false_win_rate",
        "gt_vs_strongest_false_tie_rate",
        "gt_vs_strongest_false_loss_rate",
        "fractional_graph_best_accuracy",
        "random_candidate_baseline",
        "fractional_graph_best_lift_mean",
        "fractional_graph_best_lift_ci95_low",
        "fractional_graph_best_lift_ci95_high",
        "mean_gt_minus_false_score",
        "correctable_cases",
        "correctable_rate",
        "strict_graph_top1_correctable_cases",
        "strict_graph_top1_correctable_rate",
        "wrong_preference_cases",
        "no_within_case_score_variation_rate",
        "best_threshold",
        "best_threshold_top1",
        "best_threshold_net_corrections",
    ]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for method in methods:
            best = method.get("best_in_sample_diagnostic_threshold", {})
            lift = method.get("fractional_graph_best_lift", {})
            writer.writerow(
                {
                    **{key: method.get(key) for key in fields if key in method},
                    "fractional_graph_best_lift_mean": lift.get("mean"),
                    "fractional_graph_best_lift_ci95_low": lift.get("ci95_low"),
                    "fractional_graph_best_lift_ci95_high": lift.get("ci95_high"),
                    "best_threshold": best.get("threshold"),
                    "best_threshold_top1": best.get("top1"),
                    "best_threshold_net_corrections": best.get("net_corrections"),
                }
            )


def run_diagnostic(args: argparse.Namespace) -> str:
    cases = load_raw_cases(args.data_root, require_labels=False)
    root_records = _root_result_map(args.root_results)
    if len(cases) != len(root_records):
        case_paths = {_normalized_path(case.dirpath) for case in cases}
        missing_results = sorted(case_paths - set(root_records))
        extra_results = sorted(set(root_records) - case_paths)
        raise ValueError(
            "case/result cardinality mismatch: "
            f"cases={len(cases)}, results={len(root_records)}, "
            f"missing_results={missing_results[:3]}, extra_results={extra_results[:3]}"
        )
    config = PropagationConfig(
        root_top_k=max(1, int(args.top_k)),
        max_candidate_nodes=max(1, int(args.max_candidate_nodes)),
        max_path_depth=max(1, int(args.max_path_depth)),
        stage1_weight=1.0,
        edge_probability_method=args.edge_probability_method,
    )
    label_free_diagnostics = build_case_diagnostics(
        cases, root_records, config=config
    )
    case_diagnostics = attach_ground_truth_after_graph_construction(
        label_free_diagnostics
    )
    thresholds = [float(value) for value in args.thresholds]
    methods = [
        evaluate_score_method(
            case_diagnostics,
            method,
            tie_epsilon=max(0.0, float(args.tie_epsilon)),
            thresholds=thresholds,
        )
        for method in SCORE_METHODS
    ]
    diversity = _aggregate_diversity(case_diagnostics)
    summary = {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "evaluation": "root_labels_used_only_after_label_free_graph_construction",
        "reporting_status": "exploratory_diagnostic_not_paper_performance",
        "case_count": len(case_diagnostics),
        "root_results": os.path.abspath(args.root_results),
        "propagation_config": config.to_dict(),
        "tie_epsilon": args.tie_epsilon,
        "thresholds": thresholds,
        "initial_stage1": _initial_metrics(case_diagnostics),
        "candidate_graph_diversity": diversity,
        "score_methods": methods,
        "diagnostic_verdict": _diagnostic_verdict(methods, diversity),
        "interpretation_checks": {
            "graph_signal_exists_if": [
                "GT-vs-false pairwise win rate is consistently above 0.5",
                "correctable cases exceed wrong-preference/corruption cases",
                "candidate graphs and scores vary within incidents",
                "a conservative positive threshold has positive net corrections",
            ],
            "important_warning": (
                "threshold sweep uses the same labels for diagnosis; any selected "
                "threshold must be re-estimated inside grouped training folds"
            ),
        },
    }
    os.makedirs(args.output_dir, exist_ok=True)
    case_path = os.path.join(args.output_dir, "candidate_graph_diagnostics.json")
    summary_path = os.path.join(args.output_dir, "summary.json")
    save_json(case_diagnostics, case_path, indent=2)
    save_json(summary, summary_path, indent=2)
    _write_candidate_csv(
        case_diagnostics, os.path.join(args.output_dir, "candidate_scores.csv")
    )
    _write_method_csv(
        methods, os.path.join(args.output_dir, "method_summary.csv")
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose whether root-conditioned propagation graphs contain "
            "candidate-root reranking signal without training a reranker."
        )
    )
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--root-results", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-candidate-nodes", type=int, default=80)
    parser.add_argument("--max-path-depth", type=int, default=8)
    parser.add_argument(
        "--edge-probability-method",
        choices=("deterministic_evidence_v1", "logit_softmax_v1"),
        default="deterministic_evidence_v1",
    )
    parser.add_argument("--tie-epsilon", type=float, default=1e-6)
    parser.add_argument(
        "--thresholds",
        type=float,
        nargs="+",
        default=list(DEFAULT_THRESHOLDS),
        help="Exploratory graph-score advantage thresholds for safe promotion.",
    )
    return parser


def main() -> None:
    run_diagnostic(build_parser().parse_args())


if __name__ == "__main__":
    main()
