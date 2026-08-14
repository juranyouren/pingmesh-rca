from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple

if __package__ in (None, ""):
    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

from Sys.RootCauseAnalyze.propagation.schema import root_devices
from Sys.RootCauseAnalyze.propagation.solver import is_dag
from Sys.utils.io_utils import load_json, save_json


def _safe_ratio(numerator: float, denominator: float, *, empty: float = 0.0) -> float:
    return numerator / denominator if denominator else empty


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _prediction(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("propagation")
    return value if isinstance(value, Mapping) else record


def prediction_validity(record: Mapping[str, Any]) -> Dict[str, Any]:
    prediction = _prediction(record)
    edges = [dict(item) for item in prediction.get("edges", []) if isinstance(item, Mapping)]
    nodes = [dict(item) for item in prediction.get("nodes", []) if isinstance(item, Mapping)]
    temporal_edges = [
        edge for edge in edges if edge.get("features", {}).get("temporal_available")
    ]
    topology_validity = _safe_ratio(
        sum(float(edge.get("features", {}).get("topology_valid", 0.0) or 0.0) for edge in edges),
        len(edges),
        empty=1.0,
    )
    temporal_consistency = _safe_ratio(
        sum(
            1
            for edge in temporal_edges
            if float(edge.get("features", {}).get("temporal_compatibility", 0.0) or 0.0) > 0
        ),
        len(temporal_edges),
        empty=0.0,
    )
    evidence_grounding = _safe_ratio(
        sum(1 for edge in edges if edge.get("evidence_ids")),
        len(edges),
        empty=0.0,
    )
    trust = prediction.get("trust", {}) if isinstance(prediction.get("trust"), Mapping) else {}
    passed = set(trust.get("passed", [])) if isinstance(trust.get("passed"), list) else set()
    ranking_feedback = (
        prediction.get("ranking_feedback", {})
        if isinstance(prediction.get("ranking_feedback"), Mapping)
        else {}
    )
    hypothesis_graph = (
        prediction.get("hypothesis_graph", {})
        if isinstance(prediction.get("hypothesis_graph"), Mapping)
        else {}
    )
    hypothesis_summary = (
        hypothesis_graph.get("summary", {})
        if isinstance(hypothesis_graph.get("summary"), Mapping)
        else {}
    )
    return {
        "topology_validity": round(topology_validity, 6),
        "temporal_consistency": round(temporal_consistency, 6),
        "temporal_edge_count": len(temporal_edges),
        "evidence_grounding": round(evidence_grounding, 6),
        "dag_validity": is_dag(edges),
        "root_reachability": "root_reachable" in passed,
        "observed_impact_coverage": float(prediction.get("target_coverage", 0.0) or 0.0),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "diagnosability": prediction.get("diagnosability", "unknown"),
        "root_ranking_rewritten": bool(ranking_feedback.get("ranking_rewritten")),
        "fallback_to_stage1": bool(ranking_feedback.get("fallback_to_stage1")),
        "relation_candidate_pair_count": int(
            hypothesis_summary.get("candidate_pair_count", 0) or 0
        ),
    }


def _set_scores(predicted: Set[Any], required: Set[Any], allowed: Set[Any]) -> Dict[str, float]:
    correct = len(predicted & allowed)
    precision = _safe_ratio(correct, len(predicted), empty=1.0 if not required else 0.0)
    recall = _safe_ratio(len(predicted & required), len(required), empty=1.0)
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(_f1(precision, recall), 6),
    }


def _label_edges(label: Mapping[str, Any]) -> Tuple[Dict[str, Tuple[str, str]], Set[Tuple[str, str]], Set[Tuple[str, str]]]:
    by_id: Dict[str, Tuple[str, str]] = {}
    required: Set[Tuple[str, str]] = set()
    allowed: Set[Tuple[str, str]] = set()
    for item in label.get("edges", []):
        if not isinstance(item, Mapping):
            continue
        edge = (str(item.get("from", "")), str(item.get("to", "")))
        if not all(edge):
            continue
        edge_id = str(item.get("edge_id", "") or "")
        if edge_id:
            by_id[edge_id] = edge
        membership = item.get("membership")
        if membership == "definite":
            required.add(edge)
            allowed.add(edge)
        elif membership == "possible":
            allowed.add(edge)
    return by_id, required, allowed


def _acceptable_edge_sets(label: Mapping[str, Any]) -> List[Tuple[Set[Tuple[str, str]], Set[Tuple[str, str]]]]:
    by_id, base_required, base_allowed = _label_edges(label)
    variants = [(base_required, base_allowed)]
    for hypothesis in label.get("acceptable_hypotheses", []):
        if not isinstance(hypothesis, Mapping):
            continue
        required_ids = hypothesis.get("required_edges", [])
        allowed_ids = hypothesis.get("allowed_edges", [])
        required = {by_id[item] for item in required_ids if item in by_id}
        allowed = required | {by_id[item] for item in allowed_ids if item in by_id}
        if not required_ids:
            required |= base_required
        allowed |= required
        variants.append((required, allowed))
    unique = []
    seen = set()
    for required, allowed in variants:
        key = (tuple(sorted(required)), tuple(sorted(allowed)))
        if key not in seen:
            seen.add(key)
            unique.append((required, allowed))
    return unique


def _root_score(prediction: Mapping[str, Any], label: Mapping[str, Any]) -> float:
    predicted = prediction.get("root_hypothesis", {})
    if not isinstance(predicted, Mapping):
        return 0.0
    scope = str(label.get("root_scope", "uncertain"))
    if scope == "uncertain":
        return 1.0
    if scope == "inter_device_link":
        expected_link = label.get("root_link", {})
        predicted_link = predicted.get("root_link", {})
        if not isinstance(expected_link, Mapping) or not isinstance(predicted_link, Mapping):
            return 0.0
        expected = {str(expected_link.get("endpoint_a", "")), str(expected_link.get("endpoint_b", ""))}
        actual = {str(predicted_link.get("endpoint_a", "")), str(predicted_link.get("endpoint_b", ""))}
        return 1.0 if expected == actual and "" not in expected else 0.0
    expected_devices = {
        str(item) for item in label.get("root_devices", []) if isinstance(item, str) and item
    }
    actual_devices = set(root_devices(predicted))
    return 1.0 if expected_devices and expected_devices & actual_devices else 0.0


def label_components(record: Mapping[str, Any], label: Mapping[str, Any]) -> Dict[str, Any]:
    prediction = _prediction(record)
    predicted_nodes = {
        str(item.get("device_id"))
        for item in prediction.get("nodes", [])
        if isinstance(item, Mapping) and item.get("device_id")
    }
    required_nodes = {
        str(item.get("device_id"))
        for item in label.get("nodes", [])
        if isinstance(item, Mapping)
        and item.get("device_id")
        and item.get("membership") == "definite"
    }
    allowed_nodes = required_nodes | {
        str(item.get("device_id"))
        for item in label.get("nodes", [])
        if isinstance(item, Mapping)
        and item.get("device_id")
        and item.get("membership") == "possible"
    }
    predicted_edges = {
        (str(item.get("from")), str(item.get("to")))
        for item in prediction.get("edges", [])
        if isinstance(item, Mapping) and item.get("from") and item.get("to")
    }
    _edge_by_id, strict_required_edges, _strict_allowed_edges = _label_edges(label)
    edge_variants = _acceptable_edge_sets(label)
    edge_scores = [_set_scores(predicted_edges, required, allowed) for required, allowed in edge_variants]
    best_edge = max(edge_scores, key=lambda item: (item["f1"], item["recall"], item["precision"]))
    node_score = _set_scores(predicted_nodes, required_nodes, allowed_nodes)
    evidence_score = _safe_ratio(
        sum(
            1
            for item in prediction.get("edges", [])
            if isinstance(item, Mapping) and item.get("evidence_ids")
        ),
        len(predicted_edges),
        empty=1.0 if not predicted_edges else 0.0,
    )
    strict = (
        _root_score(prediction, label) == 1.0
        and predicted_nodes == required_nodes
        and predicted_edges == strict_required_edges
    )
    return {
        "root": _root_score(prediction, label),
        "node": node_score,
        "directed_edge": best_edge,
        "evidence": round(evidence_score, 6),
        "strict_exact": strict,
    }


def combine_similarity(components: Mapping[str, Any], weights: Mapping[str, float]) -> float:
    values = {
        "root": float(components.get("root", 0.0) or 0.0),
        "node": float(components.get("node", {}).get("f1", 0.0) or 0.0),
        "directed_edge": float(components.get("directed_edge", {}).get("f1", 0.0) or 0.0),
        "evidence": float(components.get("evidence", 0.0) or 0.0),
    }
    active = {key: float(value) for key, value in weights.items() if key in values and float(value) > 0}
    if not active:
        raise ValueError("at least one positive similarity weight is required")
    return round(
        sum(values[key] * weight for key, weight in active.items()) / sum(active.values()),
        12,
    )


def decimal_round_half_up(value: float, digits: int) -> float:
    quantum = Decimal("1").scaleb(-digits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def aggregate_validity(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = [prediction_validity(record) for record in records if _prediction(record)]
    if not rows:
        return {"case_count": 0}
    numeric_keys = (
        "topology_validity",
        "temporal_consistency",
        "evidence_grounding",
        "observed_impact_coverage",
        "node_count",
        "edge_count",
        "relation_candidate_pair_count",
    )
    return {
        "case_count": len(rows),
        **{
            f"mean_{key}": round(sum(float(row[key]) for row in rows) / len(rows), 6)
            for key in numeric_keys
        },
        "dag_valid_rate": round(sum(bool(row["dag_validity"]) for row in rows) / len(rows), 6),
        "root_reachable_rate": round(sum(bool(row["root_reachability"]) for row in rows) / len(rows), 6),
        "diagnosability": {
            state: sum(1 for row in rows if row["diagnosability"] == state)
            for state in sorted({str(row["diagnosability"]) for row in rows})
        },
        "root_ranking_rewrite_rate": round(
            sum(bool(row["root_ranking_rewritten"]) for row in rows) / len(rows), 6
        ),
        "stage1_fallback_rate": round(
            sum(bool(row["fallback_to_stage1"]) for row in rows) / len(rows), 6
        ),
    }


def _parse_weights(raw: str | None) -> Dict[str, float] | None:
    if not raw:
        return None
    weights = {}
    for part in raw.split(","):
        key, value = part.split("=", 1)
        weights[key.strip()] = float(value)
    return weights


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate propagation validity and optional path labels.")
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--labels-root", default=None)
    parser.add_argument("--weights", default=None, help="root=1,node=1,directed_edge=2,evidence=0")
    parser.add_argument("--round-digits", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.8)
    args = parser.parse_args()

    records = load_json(args.predictions, default=[])
    if not isinstance(records, list):
        raise ValueError("predictions must contain a JSON list")
    output: Dict[str, Any] = {"validity": aggregate_validity(records), "cases": []}
    weights = _parse_weights(args.weights)
    correct = 0
    labeled = 0
    if args.labels_root:
        for record in records:
            if not isinstance(record, Mapping) or not record.get("dir"):
                continue
            case_id = os.path.basename(os.path.normpath(str(record["dir"])))
            label_path = os.path.join(args.labels_root, case_id, "propagation_label.json")
            label = load_json(label_path, default=None)
            if not isinstance(label, Mapping):
                continue
            components = label_components(record, label)
            case_row: Dict[str, Any] = {"case_id": case_id, "components": components}
            if weights:
                similarity = combine_similarity(components, weights)
                rounded = decimal_round_half_up(similarity, args.round_digits)
                is_correct = rounded >= args.threshold
                case_row.update(
                    {"similarity": similarity, "rounded_similarity": rounded, "correct": is_correct}
                )
                correct += int(is_correct)
            output["cases"].append(case_row)
            labeled += 1
        output["labeled_case_count"] = labeled
        if weights:
            output["tolerant_accuracy"] = round(correct / labeled, 6) if labeled else None
            output["matcher"] = {
                "weights": weights,
                "rounding": "ROUND_HALF_UP",
                "round_digits": args.round_digits,
                "threshold": args.threshold,
            }
    save_json(output, args.out, indent=2)


if __name__ == "__main__":
    main()
