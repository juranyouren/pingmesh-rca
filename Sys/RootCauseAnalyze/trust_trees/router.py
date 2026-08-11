from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .common import as_float, top3_overlap, truthy, unique_ips

POLICY_VERSION = "strict_fail_closed_v2"


def _state(tree: Dict[str, Any]) -> str:
    value = tree.get("state") if isinstance(tree, dict) else None
    return value if value in {"strong", "weak", "uncertain"} else "uncertain"


def _recommended_for(route: str, combined_ips: Sequence[str], topo_ips: Sequence[str], temporal_ips: Sequence[str]) -> List[str]:
    if route == "topo":
        return unique_ips(topo_ips)
    if route == "temporal":
        return unique_ips(temporal_ips)
    if route == "operator":
        return unique_ips([*combined_ips, *topo_ips, *temporal_ips])
    return unique_ips(combined_ips)


def _evidence(tree: Dict[str, Any]) -> Dict[str, Any]:
    value = tree.get("evidence", {}) if isinstance(tree, dict) else {}
    return value if isinstance(value, dict) else {}


def _margin_ok(value: float | None, threshold: float) -> bool:
    return value is not None and value > 0 and value >= max(float(threshold), 0.0)


def _failure_reason(checks: Dict[str, bool]) -> str:
    priorities = (
        ("rankings_complete", "strict_incomplete_rankings_invoke_llm"),
        ("top1_unanimous", "strict_top1_disagreement_invoke_llm"),
        ("both_trees_strong", "strict_ranker_trust_not_both_strong_invoke_llm"),
        ("topo_direction_unanimous", "strict_topology_direction_conflict_invoke_llm"),
        ("direct_root_evidence", "strict_missing_direct_root_evidence_invoke_llm"),
        ("temporal_data_available", "strict_temporal_data_insufficient_invoke_llm"),
        ("temporal_subsignal_top1_unanimous", "strict_temporal_causality_conflict_invoke_llm"),
        ("topo_margin_ok", "strict_topology_margin_too_small_invoke_llm"),
        ("temporal_margin_ok", "strict_temporal_margin_too_small_invoke_llm"),
        ("combined_margin_ok", "strict_combined_margin_too_small_invoke_llm"),
    )
    for check, reason in priorities:
        if not checks.get(check, False):
            return reason
    return "strict_safety_certificate_failed_invoke_llm"


def route_with_trust_trees(
    *,
    combined_ips: Sequence[str],
    topo_ips: Sequence[str],
    temporal_ips: Sequence[str],
    topo_tree: Dict[str, Any],
    temporal_tree: Dict[str, Any],
    combined_margin_percent: float | None = None,
    topo_margin_percent: float | None = None,
    temporal_margin_percent: float | None = None,
    min_combined_margin_percent: float = 15.0,
    min_ranker_margin_percent: float = 15.0,
) -> Dict[str, Any]:
    """Fail-closed routing: bypass only with a complete safety certificate."""
    combined_ips = unique_ips(combined_ips)
    topo_ips = unique_ips(topo_ips)
    temporal_ips = unique_ips(temporal_ips)
    topo_state = _state(topo_tree)
    temporal_state = _state(temporal_tree)
    overlap_n, overlap_ips = top3_overlap(topo_ips, temporal_ips)
    rank_near = bool(topo_ips and temporal_ips and topo_ips[0] == temporal_ips[0]) or overlap_n >= 2

    topo_evidence = _evidence(topo_tree)
    temporal_evidence = _evidence(temporal_tree)
    topo_entry = topo_evidence.get("top_entry", {})
    topo_entry = topo_entry if isinstance(topo_entry, dict) else {}

    directed_top3 = topo_evidence.get("directed_top3", [])
    undirected_top3 = topo_evidence.get("undirected_top3", [])
    directed_top3 = directed_top3 if isinstance(directed_top3, list) else []
    undirected_top3 = undirected_top3 if isinstance(undirected_top3, list) else []

    burst_top3 = temporal_evidence.get("burst_top3", [])
    early_top3 = temporal_evidence.get("early_top3", [])
    burst_top3 = burst_top3 if isinstance(burst_top3, list) else []
    early_top3 = early_top3 if isinstance(early_top3, list) else []

    if topo_margin_percent is None:
        topo_margin_percent = topo_evidence.get("top1_margin_percent")
    if temporal_margin_percent is None:
        temporal_margin_percent = temporal_evidence.get("top1_margin_percent")

    top_ip = combined_ips[0] if combined_ips else None
    checks = {
        "rankings_complete": bool(combined_ips and topo_ips and temporal_ips),
        "top1_unanimous": bool(
            combined_ips
            and topo_ips
            and temporal_ips
            and combined_ips[0] == topo_ips[0] == temporal_ips[0]
        ),
        "both_trees_strong": topo_state == "strong" and temporal_state == "strong",
        "topo_direction_unanimous": bool(
            top_ip
            and directed_top3
            and undirected_top3
            and directed_top3[0] == undirected_top3[0] == top_ip
        ),
        "direct_root_evidence": truthy(topo_entry.get("high_weight_alarm_hit"))
        or as_float(topo_entry.get("max_alarm_weight")) > 0,
        "temporal_data_available": truthy(temporal_evidence.get("temporal_data_available"))
        or (
            temporal_evidence.get("ref_time_ms") is not None
            and as_float(temporal_evidence.get("devices_with_timestamps")) >= 2
            and as_float(temporal_evidence.get("top_event_count")) > 0
        ),
        "temporal_subsignal_top1_unanimous": bool(
            top_ip and burst_top3 and early_top3 and burst_top3[0] == early_top3[0] == top_ip
        ),
        "topo_margin_ok": _margin_ok(topo_margin_percent, min_ranker_margin_percent),
        "temporal_margin_ok": _margin_ok(temporal_margin_percent, min_ranker_margin_percent),
        "combined_margin_ok": _margin_ok(combined_margin_percent, min_combined_margin_percent),
    }
    safe_to_bypass = all(checks.values())
    if safe_to_bypass:
        decision, route, reason = (
            "bypass_llm",
            "combined",
            "strict_consensus_certificate_accept_combined",
        )
    else:
        decision, route, reason = "invoke_llm", "llm", _failure_reason(checks)

    recommended_ips = (
        [combined_ips[0]]
        if safe_to_bypass and combined_ips
        else _recommended_for(route, combined_ips, topo_ips, temporal_ips)
    )

    return {
        "enabled": True,
        "decision": decision,
        "route": route,
        "reason": reason,
        "policy_version": POLICY_VERSION,
        "recommended_ips": recommended_ips,
        "agreement": {
            "rank_near": rank_near,
            "top3_overlap": overlap_n,
            "top3_overlap_ips": overlap_ips,
            "method_top_ips": {
                "topo": topo_ips[0] if topo_ips else None,
                "temporal": temporal_ips[0] if temporal_ips else None,
                "combined": combined_ips[0] if combined_ips else None,
            },
        },
        "safety_certificate": {
            "safe_to_bypass": safe_to_bypass,
            "checks": checks,
            "passed": [name for name, ok in checks.items() if ok],
            "failed": [name for name, ok in checks.items() if not ok],
            "margins_percent": {
                "combined": combined_margin_percent,
                "topo": topo_margin_percent,
                "temporal": temporal_margin_percent,
            },
            "thresholds_percent": {
                "combined": min_combined_margin_percent,
                "ranker": min_ranker_margin_percent,
            },
        },
        "trust_trees": {
            "topo": topo_tree,
            "temporal": temporal_tree,
        },
    }
