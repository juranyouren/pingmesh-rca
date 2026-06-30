from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .common import top3_overlap, unique_ips

POLICY_VERSION = "trust_tree_v1"


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


def route_with_trust_trees(
    *,
    combined_ips: Sequence[str],
    topo_ips: Sequence[str],
    temporal_ips: Sequence[str],
    topo_tree: Dict[str, Any],
    temporal_tree: Dict[str, Any],
) -> Dict[str, Any]:
    """Route one case using topo/temporal trust tree states."""
    combined_ips = unique_ips(combined_ips)
    topo_ips = unique_ips(topo_ips)
    temporal_ips = unique_ips(temporal_ips)
    topo_state = _state(topo_tree)
    temporal_state = _state(temporal_tree)
    overlap_n, overlap_ips = top3_overlap(topo_ips, temporal_ips)
    rank_near = bool(topo_ips and temporal_ips and topo_ips[0] == temporal_ips[0]) or overlap_n >= 2

    if topo_state == "weak" and temporal_state == "weak":
        decision, route, reason = "operator_review", "operator", "both_rankers_weak_operator_review"
    elif rank_near:
        decision, route, reason = "bypass_llm", "combined", "rankers_near_accept_combined"
    elif topo_state == "strong" and temporal_state != "strong":
        decision, route, reason = "bypass_llm", "topo", "topo_strong_accept_topo"
    elif temporal_state == "strong" and topo_state != "strong":
        decision, route, reason = "bypass_llm", "temporal", "temporal_strong_accept_temporal"
    elif topo_state == "strong" and temporal_state == "strong":
        decision, route, reason = "invoke_llm", "llm", "strong_ranker_conflict_invoke_llm"
    else:
        decision, route, reason = "invoke_llm", "llm", "unresolved_ranker_uncertainty_invoke_llm"

    return {
        "enabled": True,
        "decision": decision,
        "route": route,
        "reason": reason,
        "policy_version": POLICY_VERSION,
        "recommended_ips": _recommended_for(route, combined_ips, topo_ips, temporal_ips),
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
        "trust_trees": {
            "topo": topo_tree,
            "temporal": temporal_tree,
        },
    }
