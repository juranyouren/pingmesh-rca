from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, Mapping, Sequence, Set

from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig, normalize_config, root_devices
from Sys.RootCauseAnalyze.propagation.solver import is_dag


def _root_reachable(result: Mapping[str, Any]) -> bool:
    roots = root_devices(result.get("root_hypothesis", {}))
    nodes = {
        str(item.get("device_id"))
        for item in result.get("nodes", [])
        if isinstance(item, Mapping) and item.get("device_id")
    }
    if not roots or not nodes or not set(roots).issubset(nodes):
        return False
    adjacency: Dict[str, Set[str]] = defaultdict(set)
    for edge in result.get("edges", []):
        if isinstance(edge, Mapping):
            adjacency[str(edge.get("from", ""))].add(str(edge.get("to", "")))
    seen = set(roots)
    queue = deque(roots)
    while queue:
        node = queue.popleft()
        for neighbor in adjacency.get(node, set()):
            if neighbor and neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return nodes.issubset(seen)


def assess_path_trust(
    result: Mapping[str, Any],
    *,
    config: PropagationConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    cfg = normalize_config(config)
    edges = [dict(item) for item in result.get("edges", []) if isinstance(item, Mapping)]
    diagnostics = result.get("diagnostics", {}) if isinstance(result.get("diagnostics"), Mapping) else {}
    target_count = int(diagnostics.get("target_count", 0) or 0)
    coverage = float(result.get("target_coverage", 0.0) or 0.0)
    topology_valid = all(
        float(edge.get("features", {}).get("topology_valid", 0.0) or 0.0) >= 1.0
        for edge in edges
    )
    dag_valid = is_dag(edges)
    reachable = _root_reachable(result)
    grounded_count = sum(1 for edge in edges if edge.get("evidence_ids"))
    grounded_ratio = grounded_count / len(edges) if edges else 0.0
    moderate_or_strong = sum(
        1 for edge in edges if edge.get("support_level") in {"moderate", "strong"}
    )
    strong_ratio = sum(1 for edge in edges if edge.get("support_level") == "strong") / len(edges) if edges else 0.0
    supported_ratio = moderate_or_strong / len(edges) if edges else 0.0
    alternatives = [
        item for item in result.get("alternative_hypotheses", []) if isinstance(item, Mapping)
    ]
    alternative_gap = None
    if alternatives:
        alternative_gap = round(
            float(result.get("hypothesis_score", 0.0) or 0.0)
            - max(float(item.get("hypothesis_score", 0.0) or 0.0) for item in alternatives),
            6,
        )
    unique_hypothesis = alternative_gap is None or alternative_gap >= cfg.unique_hypothesis_margin
    direction_conflict = any(edge.get("alternative_group") for edge in edges)
    only_weak = bool(edges) and all(edge.get("support_level") == "weak" for edge in edges)
    checks = {
        "roots_available": bool(root_devices(result.get("root_hypothesis", {}))),
        "targets_available": target_count > 0,
        "topology_valid": topology_valid,
        "dag_valid": dag_valid,
        "root_reachable": reachable,
        "edges_available": bool(edges),
        "evidence_grounded": grounded_ratio > 0.0,
        "supported_edges_majority": supported_ratio >= 0.5,
        "target_coverage_partial": coverage >= cfg.min_target_coverage_for_partial,
        "target_coverage_full": coverage >= cfg.min_target_coverage_for_full,
        "unique_hypothesis": unique_hypothesis,
        "no_direction_conflict": not direction_conflict,
        "not_only_weak": not only_weak,
    }

    structurally_invalid = not (
        checks["roots_available"]
        and topology_valid
        and dag_valid
        and reachable
    )
    evidence_insufficient = (
        not checks["targets_available"]
        or (target_count > 0 and not edges)
        or not checks["target_coverage_partial"]
        or only_weak
    )
    if structurally_invalid or evidence_insufficient:
        diagnosability = "unidentifiable"
        state = "weak"
        action = "human_review"
    elif (
        checks["target_coverage_full"]
        and supported_ratio == 1.0
        and grounded_ratio >= 0.5
        and unique_hypothesis
        and not direction_conflict
    ):
        diagnosability = "fully_observed"
        state = "strong"
        action = "accept"
    else:
        diagnosability = "partially_observed"
        state = "partial"
        action = "output_alternatives" if alternatives or direction_conflict else "accept_with_uncertainty"

    unresolved = []
    if alternatives and not unique_hypothesis:
        unresolved.append("near_equivalent_hypotheses")
    if direction_conflict:
        unresolved.append("edge_direction_conflict")
    if grounded_ratio < 1.0:
        unresolved.append("ungrounded_intermediate_edge")
    if coverage < 1.0:
        unresolved.append("uncovered_targets")
    if not checks["targets_available"]:
        unresolved.append("missing_impact_target")
    return {
        "diagnosability": diagnosability,
        "unresolved_ambiguity": unresolved,
        "trust": {
            "state": state,
            "action": action,
            "passed": sorted(name for name, passed in checks.items() if passed),
            "failed": sorted(name for name, passed in checks.items() if not passed),
            "evidence": {
                "target_coverage": round(coverage, 6),
                "grounded_edge_ratio": round(grounded_ratio, 6),
                "supported_edge_ratio": round(supported_ratio, 6),
                "strong_edge_ratio": round(strong_ratio, 6),
                "alternative_gap": alternative_gap,
                "edge_count": len(edges),
            },
        },
    }
