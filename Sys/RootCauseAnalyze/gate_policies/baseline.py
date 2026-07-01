"""P0 — Baseline gate policy (current trust_tree_v1 rules).

Delegates directly to ``route_with_trust_trees`` — the 6-rule decision tree
already in production:

1. both weak                        → operator_review
2. rank_near (top1 match or ≥2 top3 overlap) → combined (bypass LLM)
3. topo strong alone                → invoke LLM
4. temporal strong alone            → temporal (bypass LLM)
5. both strong (disagree)           → invoke LLM
6. else (uncertain)                 → invoke LLM
"""

from __future__ import annotations

from typing import Any, Dict

POLICY_NAME = "baseline"
POLICY_LABEL = "Baseline (trust_tree_v1 — rank_near → combined)"


def route(
    *,
    combined_ips,
    topo_ips,
    temporal_ips,
    topo_tree: Dict[str, Any],
    temporal_tree: Dict[str, Any],
) -> Dict[str, Any]:
    from Sys.RootCauseAnalyze.trust_trees.router import route_with_trust_trees

    return route_with_trust_trees(
        combined_ips=combined_ips,
        topo_ips=topo_ips,
        temporal_ips=temporal_ips,
        topo_tree=topo_tree,
        temporal_tree=temporal_tree,
    )
