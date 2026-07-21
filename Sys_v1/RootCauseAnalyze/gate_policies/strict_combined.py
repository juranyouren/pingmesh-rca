"""P1 — Stricter combined bypass: requires both strong AND top-1 match.

Copies baseline, but replaces the relaxed ``rank_near`` rule with a
stricter condition: only bypass LLM when *both* topo and temporal trees
are *strong* **and** their top-1 IPs are identical.

1. both weak                        → operator_review
2. both strong + top1 same          → combined (bypass LLM)   ← stricter
3. topo strong alone                → invoke LLM
4. temporal strong alone            → temporal (bypass LLM)
5. both strong (top1 differs)       → invoke LLM
6. else (uncertain)                 → invoke LLM
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

from Sys_v1.RootCauseAnalyze.trust_trees.common import top3_overlap, unique_ips

POLICY_NAME = "strict_combined"
POLICY_LABEL = "Strict combined (both strong + top1 match → combined)"

POLICY_VERSION = "ablation_strict_combined"


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

    # ── stricter rank_near ──────────────────────────────────────────
    rank_near_strict = (
        topo_state == "strong"
        and temporal_state == "strong"
        and bool(topo_ips)
        and bool(temporal_ips)
        and topo_ips[0] == temporal_ips[0]
    )
    # (keep a loose view for logging)
    rank_near_loose = (
        bool(topo_ips) and bool(temporal_ips) and topo_ips[0] == temporal_ips[0]
    ) or overlap_n >= 2

    # ── decision tree ───────────────────────────────────────────────
    if topo_state == "weak" and temporal_state == "weak":
        decision, route_, reason = "operator_review", "operator", "both_rankers_weak_operator_review"
    elif rank_near_strict:
        decision, route_, reason = "bypass_llm", "combined", "both_strong_top1_match_accept_combined"
    elif topo_state == "strong" and temporal_state != "strong":
        decision, route_, reason = "invoke_llm", "llm", "topo_strong_defer_to_llm"
    elif temporal_state == "strong" and topo_state != "strong":
        decision, route_, reason = "bypass_llm", "temporal", "temporal_strong_accept_temporal"
    elif topo_state == "strong" and temporal_state == "strong":
        decision, route_, reason = "invoke_llm", "llm", "both_strong_top1_differ_invoke_llm"
    else:
        decision, route_, reason = "invoke_llm", "llm", "unresolved_ranker_uncertainty_invoke_llm"

    return {
        "enabled": True,
        "decision": decision,
        "route": route_,
        "reason": reason,
        "policy_version": POLICY_VERSION,
        "recommended_ips": _recommended_for(route_, combined_ips, topo_ips, temporal_ips),
        "agreement": {
            "rank_near": rank_near_strict,
            "rank_near_loose": rank_near_loose,
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
