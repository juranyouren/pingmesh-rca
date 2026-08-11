"""P0 — Frozen legacy trust_tree_v1 policy for ablation comparisons.

Keeps the former 6-rule decision tree unchanged so the active strict policy can
still be compared against it:

1. both weak                        → operator_review
2. rank_near (top1 match or ≥2 top3 overlap) → combined (bypass LLM)
3. topo strong alone                → invoke LLM
4. temporal strong alone            → temporal (bypass LLM)
5. both strong (disagree)           → invoke LLM
6. else (uncertain)                 → invoke LLM
"""

from __future__ import annotations

from typing import Any, Dict

from Sys.RootCauseAnalyze.trust_trees.common import top3_overlap, unique_ips

POLICY_NAME = "baseline"
POLICY_LABEL = "Baseline (trust_tree_v1 — rank_near → combined)"


def _state(tree: Dict[str, Any]) -> str:
    value = tree.get("state") if isinstance(tree, dict) else None
    return value if value in {"strong", "weak", "uncertain"} else "uncertain"


def _recommended_for(route_name, combined_ips, topo_ips, temporal_ips):
    if route_name == "topo":
        return unique_ips(topo_ips)
    if route_name == "temporal":
        return unique_ips(temporal_ips)
    if route_name == "operator":
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
    rank_near = bool(topo_ips and temporal_ips and topo_ips[0] == temporal_ips[0]) or overlap_n >= 2

    if topo_state == "weak" and temporal_state == "weak":
        decision, route_name, reason = "operator_review", "operator", "both_rankers_weak_operator_review"
    elif rank_near:
        decision, route_name, reason = "bypass_llm", "combined", "rankers_near_accept_combined"
    elif topo_state == "strong" and temporal_state != "strong":
        decision, route_name, reason = "invoke_llm", "llm", "topo_strong_defer_to_llm"
    elif temporal_state == "strong" and topo_state != "strong":
        decision, route_name, reason = "bypass_llm", "temporal", "temporal_strong_accept_temporal"
    elif topo_state == "strong" and temporal_state == "strong":
        decision, route_name, reason = "invoke_llm", "llm", "strong_ranker_conflict_invoke_llm"
    else:
        decision, route_name, reason = "invoke_llm", "llm", "unresolved_ranker_uncertainty_invoke_llm"

    return {
        "enabled": True,
        "decision": decision,
        "route": route_name,
        "reason": reason,
        "policy_version": "trust_tree_v1",
        "recommended_ips": _recommended_for(route_name, combined_ips, topo_ips, temporal_ips),
        "agreement": {
            "rank_near": rank_near,
            "top3_overlap": overlap_n,
            "top3_overlap_ips": overlap_ips,
        },
        "trust_trees": {"topo": topo_tree, "temporal": temporal_tree},
    }
