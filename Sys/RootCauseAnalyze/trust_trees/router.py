from __future__ import annotations

from typing import Any, Dict, Sequence

from Sys.RootCauseAnalyze.gate_policies.configurable import (
    DEFAULT_POLICY_CONFIG,
    normalize_policy_config,
    route_with_policy,
)

POLICY_VERSION = "configurable_gate_v1"


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
    min_ranker_margin_percent: float = 8.0,
    min_evidence_votes: int = 3,
    policy_config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Route using the selected configurable policy.

    Margin arguments remain supported for existing callers. They override the
    default policy only when no explicit policy config is supplied.
    """
    if policy_config is None:
        config = normalize_policy_config(
            {
                **DEFAULT_POLICY_CONFIG,
                "combined_margin_percent": min_combined_margin_percent,
                "ranker_margin_percent": min_ranker_margin_percent,
                "min_evidence_votes": min_evidence_votes,
            }
        )
    else:
        config = normalize_policy_config(policy_config)
    return route_with_policy(
        combined_ips=combined_ips,
        topo_ips=topo_ips,
        temporal_ips=temporal_ips,
        topo_tree=topo_tree,
        temporal_tree=temporal_tree,
        combined_margin_percent=combined_margin_percent,
        topo_margin_percent=topo_margin_percent,
        temporal_margin_percent=temporal_margin_percent,
        policy_config=config,
    )
