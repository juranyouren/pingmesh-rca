"""P3 — Conservative gate: minimal bypass, everything else to LLM.

Only two bypass rules exist:

1. both strong + top-1 identical → combined (bypass LLM)
2. temporal strong alone            → temporal (bypass LLM)

All other cases (including topo-strong-alone, both-strong-disagree,
uncertain, weak+weak) are sent to LLM.  There is **no** operator_review
route — weak+weak also goes to LLM.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

from Sys.RootCauseAnalyze.trust_trees.common import top3_overlap, unique_ips

POLICY_NAME = "conservative"
POLICY_LABEL = "Conservative (only both-strong+top1-match → combined, temporal-strong → temporal)"

POLICY_VERSION = "ablation_conservative"


def _state(tree: Dict[str, Any]) -> str:
    value = tree.get("state") if isinstance(tree, dict) else None
    return value if value in {"strong", "weak", "uncertain"} else "uncertain"


def _recommended_for(route: str, combined_ips: Sequence[str], topo_ips: Sequence[str], temporal_ips: Sequence[str]):
    if route == "topo":
        return unique_ips(topo_ips)
    if route == "temporal":
        return unique_ips(temporal_ips)
    if route == "operator":
        return unique_ips([*combined_ips, *topo_ips, *temporal_ips])
    return unique_ips(combined_ips)


def route(
    *,
    combined_ips,
    topo_ips,
    temporal_ips,
    topo_tree: Dict[str, Any],
    temporal_tree: Dict[str, Any],
) -> Dict[str, Any]:
    combined_ips = unique_ips(combined_ips)
    topo_ips = unique_ips(topo_ips)
    temporal_ips = unique_ips(temporal_ips)
    topo_state = _state(topo_tree)
    temporal_state = _state(temporal_tree)
    overlap_n, overlap_ips = top3_overlap(topo_ips, temporal_ips)

    both_strong = topo_state == "strong" and temporal_state == "strong"
    top1_same = (
        bool(topo_ips) and bool(temporal_ips) and topo_ips[0] == temporal_ips[0]
    )

    # ── decision tree (only 2 bypass rules) ─────────────────────────
    if both_strong and top1_same:
        decision, route_, reason = "bypass_llm", "combined", "both_strong_top1_match_accept_combined"
    elif temporal_state == "strong" and topo_state != "strong":
        decision, route_, reason = "bypass_llm", "temporal", "temporal_strong_accept_temporal"
    else:
        decision, route_, reason = "invoke_llm", "llm", "conservative_defer_to_llm"

    return {
        "enabled": True,
        "decision": decision,
        "route": route_,
        "reason": reason,
        "policy_version": POLICY_VERSION,
        "recommended_ips": _recommended_for(route_, combined_ips, topo_ips, temporal_ips),
        "agreement": {
            "rank_near": both_strong and top1_same,
            "top3_overlap": overlap_n,
            "top3_overlap_ips": overlap_ips,
            "method_top_ips": {
                "topo": topo_ips[0] if topo_ips else None,
                "temporal": temporal_ips[0] if temporal_ips else None,
                "combined": combined_ips[0] if combined_ips else None,
            },
        },
        "trust_trees": {"topo": topo_tree, "temporal": temporal_tree},
    }
