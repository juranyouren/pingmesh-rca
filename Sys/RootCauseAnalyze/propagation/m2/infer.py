from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Mapping, Sequence, Set

from Sys.RootCauseAnalyze.propagation.schema import (
    M2_SCHEMA_VERSION,
    PropagationConfig,
    build_root_hypotheses,
    normalize_config,
    root_devices,
)
from Sys.RootCauseAnalyze.propagation.solver import solve_propagation_dags


def _candidate_graph(hypothesis_graph: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "nodes": [dict(item) for item in hypothesis_graph.get("nodes", [])],
        "edges": [dict(item) for item in hypothesis_graph.get("candidate_topology_edges", [])],
        "targets": [dict(item) for item in hypothesis_graph.get("affected_targets", [])],
        "source_anchors": list(hypothesis_graph.get("source_anchors", [])),
        "sink_anchors": list(hypothesis_graph.get("sink_anchors", [])),
    }


def _adjacency(candidate_graph: Mapping[str, Any]) -> Dict[str, Set[str]]:
    result: Dict[str, Set[str]] = {
        str(item.get("device_id")): set()
        for item in candidate_graph.get("nodes", [])
        if isinstance(item, Mapping) and item.get("device_id")
    }
    for item in candidate_graph.get("edges", []):
        if not isinstance(item, Mapping):
            continue
        a = str(item.get("endpoint_a", "") or "")
        b = str(item.get("endpoint_b", "") or "")
        if a and b and a != b:
            result.setdefault(a, set()).add(b)
            result.setdefault(b, set()).add(a)
    return result


def _distances(adjacency: Mapping[str, Set[str]], roots: Sequence[str]) -> Dict[str, int]:
    distance: Dict[str, int] = {}
    queue = deque()
    for root in sorted(set(roots)):
        if root in adjacency:
            distance[root] = 0
            queue.append(root)
    while queue:
        node = queue.popleft()
        for neighbor in sorted(adjacency.get(node, set())):
            if neighbor not in distance:
                distance[neighbor] = distance[node] + 1
                queue.append(neighbor)
    return distance


def _effective_relation_weight(pair: Mapping[str, Any]) -> float:
    probabilities = pair.get("state_probabilities", {})
    if not isinstance(probabilities, Mapping):
        return 0.0
    forward = float(probabilities.get("endpoint_a_to_b", 0.0) or 0.0)
    reverse = float(probabilities.get("endpoint_b_to_a", 0.0) or 0.0)
    no_direct = float(probabilities.get("no_direct_propagation", 0.0) or 0.0)
    directional = max(forward, reverse)
    return directional if directional > no_direct else 0.0


def _condition_edges(
    hypothesis_graph: Mapping[str, Any],
    root_hypothesis: Mapping[str, Any],
    config: PropagationConfig,
) -> List[Dict[str, Any]]:
    candidate_graph = _candidate_graph(hypothesis_graph)
    distance = _distances(_adjacency(candidate_graph), root_devices(root_hypothesis))
    topology_edge_ids_by_pair = {
        tuple(sorted((str(item.get("endpoint_a", "")), str(item.get("endpoint_b", ""))))): {
            str(edge_id)
            for edge_id in item.get("topology_edge_ids", [])
            if edge_id
        }
        for item in candidate_graph.get("edges", [])
        if isinstance(item, Mapping)
        and item.get("endpoint_a")
        and item.get("endpoint_b")
    }
    rows: List[Dict[str, Any]] = []
    for pair in hypothesis_graph.get("edge_hypotheses", []):
        if not isinstance(pair, Mapping):
            continue
        endpoint_pair = tuple(
            sorted(
                (
                    str(pair.get("endpoint_a", "")),
                    str(pair.get("endpoint_b", "")),
                )
            )
        )
        candidate_topology_ids = topology_edge_ids_by_pair.get(endpoint_pair, set())
        hypothesis_topology_ids = {
            str(edge_id) for edge_id in pair.get("topology_edge_ids", []) if edge_id
        }
        validated_topology_ids = sorted(
            candidate_topology_ids & hypothesis_topology_ids
        )
        if not validated_topology_ids:
            continue
        no_direct = float(
            pair.get("state_probabilities", {}).get("no_direct_propagation", 0.0) or 0.0
        )
        for raw_direction in pair.get("directions", []):
            if not isinstance(raw_direction, Mapping):
                continue
            direction = dict(raw_direction)
            source = str(direction.get("from", "") or "")
            target = str(direction.get("to", "") or "")
            probability = float(direction.get("state_probability", 0.0) or 0.0)
            source_distance = distance.get(source)
            target_distance = distance.get(target)
            outward = (
                source_distance is not None
                and target_distance is not None
                and target_distance > source_distance
            )
            eligible = outward and probability > no_direct and probability >= config.min_edge_support
            rows.append(
                {
                    "edge_hypothesis_id": pair.get("edge_hypothesis_id"),
                    "from": source,
                    "to": target,
                    "edge_type": pair.get("edge_type", "physical"),
                    "relation": direction.get("relation", "inferred_impact"),
                    "direction_status": "likely" if eligible else "unresolved",
                    "lag_interval_ms": direction.get("lag_interval_ms"),
                    "support_level": (
                        "strong"
                        if eligible and probability >= config.strong_edge_support
                        else "moderate"
                        if eligible and probability >= config.moderate_edge_support
                        else "weak"
                        if eligible
                        else "rejected"
                    ),
                    "case_support_score": direction.get("case_support_score", 0.0),
                    "state_probability": round(probability, 6),
                    "support_score": round(probability if eligible else 0.0, 6),
                    "features": {
                        **dict(direction.get("features", {})),
                        "topology_valid": 1.0,
                        "root_distance_consistency": 1.0 if outward else 0.0,
                        "contradiction": 0.0 if outward else 1.0,
                    },
                    "topology_edge_ids": validated_topology_ids,
                    "topology_validation": "raw_edge_match",
                    "evidence_ids": list(direction.get("evidence_ids", [])),
                    "counter_evidence_ids": list(direction.get("counter_evidence_ids", [])),
                    "alternative_group": None,
                }
            )
    return sorted(rows, key=lambda item: (item["from"], item["to"]))


def _max_normalize(values: Sequence[float]) -> List[float]:
    maximum = max(values, default=0.0)
    if maximum <= 0.0:
        return [0.0 for _value in values]
    return [value / maximum for value in values]


def _rank_change(initial_rank: int, final_rank: int) -> str:
    if final_rank < initial_rank:
        return "promote"
    if final_rank > initial_rank:
        return "demote"
    return "unchanged"


def _selected_probability_sum(
    hypothesis_graph: Mapping[str, Any],
    propagation_graph: Mapping[str, Any],
) -> float:
    selected_directions = {
        (
            str(edge.get("edge_hypothesis_id", "") or ""),
            str(edge.get("from", "") or ""),
            str(edge.get("to", "") or ""),
        )
        for edge in propagation_graph.get("edges", [])
        if isinstance(edge, Mapping) and edge.get("edge_hypothesis_id")
    }
    total = 0.0
    for pair in hypothesis_graph.get("edge_hypotheses", []):
        if not isinstance(pair, Mapping):
            continue
        pair_id = str(pair.get("edge_hypothesis_id", "") or "")
        total += max(
            (
                float(direction.get("state_probability", 0.0) or 0.0)
                for direction in pair.get("directions", [])
                if isinstance(direction, Mapping)
                and (
                    pair_id,
                    str(direction.get("from", "") or ""),
                    str(direction.get("to", "") or ""),
                )
                in selected_directions
            ),
            default=0.0,
        )
    return total


def infer_root_paths(
    *,
    hypothesis_graph: Mapping[str, Any],
    initial_root_rankings: Sequence[Mapping[str, Any] | str],
    config: PropagationConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Explain one shared M1 graph with each Stage 1 root and rerank roots."""

    cfg = normalize_config(config)
    roots = build_root_hypotheses(initial_root_rankings, top_k=cfg.root_top_k)
    candidate_graph = _candidate_graph(hypothesis_graph)
    episodes = [
        dict(item)
        for item in hypothesis_graph.get("evidence_map", {}).values()
        if isinstance(item, Mapping)
    ]
    denominator = sum(
        _effective_relation_weight(pair)
        for pair in hypothesis_graph.get("edge_hypotheses", [])
        if isinstance(pair, Mapping)
    )

    solved: List[Dict[str, Any]] = []
    for root in roots:
        conditioned = _condition_edges(hypothesis_graph, root, cfg)
        propagation = solve_propagation_dags(
            candidate_graph,
            root,
            conditioned,
            episodes,
            config=cfg,
        )
        numerator = _selected_probability_sum(hypothesis_graph, propagation)
        explanation = numerator / denominator if denominator > 0.0 else 0.0
        solved.append(
            {
                "root_hypothesis": root,
                "propagation_graph": propagation,
                "explanation_score": round(max(0.0, min(1.0, explanation)), 6),
                "explanation_numerator": round(numerator, 6),
                "explanation_denominator": round(denominator, 6),
            }
        )

    stage1_scores = [float(item["root_hypothesis"].get("support_score", 0.0)) for item in solved]
    explanation_scores = [float(item["explanation_score"]) for item in solved]
    normalized_stage1 = _max_normalize(stage1_scores)
    normalized_explanation = _max_normalize(explanation_scores)
    path_evidence_sufficient = denominator > 0.0 and any(
        item.get("propagation_graph", {}).get("edges") for item in solved
    )
    for index, item in enumerate(solved):
        final_score = (
            cfg.stage1_weight * normalized_stage1[index]
            + (1.0 - cfg.stage1_weight) * normalized_explanation[index]
            if path_evidence_sufficient
            else normalized_stage1[index]
        )
        item["normalized_stage1_score"] = round(normalized_stage1[index], 6)
        item["normalized_explanation_score"] = round(normalized_explanation[index], 6)
        item["final_score"] = round(final_score, 6)

    ranked = sorted(
        solved,
        key=lambda item: (
            -float(item["final_score"]),
            int(item["root_hypothesis"].get("rank", 0) or 0),
            str(item["root_hypothesis"].get("hypothesis_id", "")),
        ),
    )
    final_rankings: List[Dict[str, Any]] = []
    for final_rank, item in enumerate(ranked, 1):
        root = item["root_hypothesis"]
        initial_rank = int(root.get("rank", final_rank) or final_rank)
        devices = root_devices(root)
        final_rankings.append(
            {
                "rank": final_rank,
                "ip": devices[0] if devices else "",
                "hypothesis_id": root.get("hypothesis_id"),
                "initial_rank": initial_rank,
                "stage1_score": root.get("support_score", 0.0),
                "normalized_stage1_score": item["normalized_stage1_score"],
                "explanation_score": item["explanation_score"],
                "normalized_explanation_score": item[
                    "normalized_explanation_score"
                ],
                "final_score": item["final_score"],
                "rank_change": _rank_change(initial_rank, final_rank),
            }
        )

    selected = ranked[0] if ranked else None
    return {
        "schema_version": M2_SCHEMA_VERSION,
        "initial_root_rankings": [
            {
                "rank": int(item.get("rank", index) or index),
                "ip": root_devices(item)[0] if root_devices(item) else "",
                "stage1_score": item.get("support_score", 0.0),
                "hypothesis_id": item.get("hypothesis_id"),
            }
            for index, item in enumerate(roots, 1)
        ],
        "final_root_rankings": final_rankings,
        "root_conditioned_propagation_graphs": solved,
        "selected_root": final_rankings[0]["ip"] if final_rankings else None,
        "selected_propagation_graph": (
            dict(selected["propagation_graph"]) if selected is not None else {}
        ),
        "ranking_feedback": {
            "ranking_rewritten": any(
                item["rank_change"] != "unchanged" for item in final_rankings
            ),
            "fallback_to_stage1": not path_evidence_sufficient,
            "stage1_weight": cfg.stage1_weight,
            "explanation_weight": round(1.0 - cfg.stage1_weight, 6),
            "final_score_formula": (
                "stage1_weight * normalized_stage1_score + "
                "(1 - stage1_weight) * normalized_explanation_score"
            ),
            "only_two_weighted_scores": True,
        },
        "config_version": cfg.config_version,
    }
