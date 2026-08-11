from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from Sys.RootCauseAnalyze.trust_trees.common import (
    normalize_entries,
    score_key_for,
    top1_margin_percent,
    unique_ips,
)
from Sys.RootCauseAnalyze.gate_policies.configurable import resolve_policy_config
from Sys.RootCauseAnalyze.trust_trees.router import POLICY_VERSION, route_with_trust_trees
from Sys.RootCauseAnalyze.trust_trees.temporal_tree import assess_temporal_tree
from Sys.RootCauseAnalyze.trust_trees.topo_tree import assess_topo_tree


def _safe_load_skill_ret(skill_ret: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(skill_ret)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _extract_rankings(data: Dict[str, Any], method: str) -> List[Dict[str, Any]]:
    if method == "combined":
        raw = data.get("combined_score_rankings", [])
    else:
        raw = (data.get(method, {}) or {}).get("rankings", [])
    return raw if isinstance(raw, list) else []


def _method_ips(data: Dict[str, Any], method: str, limit: int = 5) -> List[str]:
    entries = normalize_entries(_extract_rankings(data, method), score_key_for(method))
    return unique_ips(row.get("ip") for row in entries[:limit])


def _method_margin_percent(data: Dict[str, Any], method: str) -> float | None:
    entries = normalize_entries(_extract_rankings(data, method), score_key_for(method))
    return top1_margin_percent(entries)


def _invalid_gate(reason: str) -> Dict[str, Any]:
    empty_tree = {"state": "weak", "passed": [], "failed": [reason], "evidence": {}}
    return {
        "enabled": True,
        "decision": "invoke_llm",
        "route": "llm",
        "reason": reason,
        "policy_version": POLICY_VERSION,
        "recommended_ips": [],
        "agreement": {
            "rank_near": False,
            "top3_overlap": 0,
            "top3_overlap_ips": [],
            "method_top_ips": {"topo": None, "temporal": None, "combined": None},
        },
        "safety_certificate": {
            "safe_to_bypass": False,
            "checks": {"rankings_complete": False},
            "passed": [],
            "failed": ["rankings_complete"],
            "margins_percent": {"combined": None, "topo": None, "temporal": None},
            "thresholds_percent": {"combined": None, "ranker": None},
            "evidence_votes": {"count": 0, "required": 3, "available": 4},
        },
        "trust_trees": {"topo": empty_tree, "temporal": empty_tree},
    }


def assess_gate(
    skill_ret: str,
    *,
    high_margin: float = 15.0,
    agreement_margin: float = 8.0,
    policy_config: Dict[str, Any] | str | None = None,
) -> Dict[str, Any]:
    """Assess the strict fail-closed route for one case.

    ``high_margin`` is the required combined Top-1/Top-2 relative gap and
    ``agreement_margin`` is the required gap for each independent ranker. Both
    are percentage-point values and now participate in the decision.
    """
    data = _safe_load_skill_ret(skill_ret)
    if not data:
        return _invalid_gate("invalid_or_missing_rankings")

    combined_ips = _method_ips(data, "combined")
    topo_ips = _method_ips(data, "topo")
    temporal_ips = _method_ips(data, "temporal")
    if not combined_ips and not topo_ips and not temporal_ips:
        return _invalid_gate("invalid_or_missing_rankings")

    resolved_policy = resolve_policy_config(policy_config)
    env_policy_path = os.environ.get("PINGMESH_GATE_POLICY_CONFIG", "").strip()
    if policy_config is None and not env_policy_path:
        resolved_policy = {
            **resolved_policy,
            "combined_margin_percent": high_margin,
            "ranker_margin_percent": agreement_margin,
        }
    gate = route_with_trust_trees(
        combined_ips=combined_ips,
        topo_ips=topo_ips,
        temporal_ips=temporal_ips,
        topo_tree=assess_topo_tree(data.get("topo", {})),
        temporal_tree=assess_temporal_tree(data.get("temporal", {})),
        combined_margin_percent=_method_margin_percent(data, "combined"),
        topo_margin_percent=_method_margin_percent(data, "topo"),
        temporal_margin_percent=_method_margin_percent(data, "temporal"),
        min_combined_margin_percent=high_margin,
        min_ranker_margin_percent=agreement_margin,
        policy_config=resolved_policy,
    )
    gate["thresholds"] = {
        "high_margin": high_margin,
        "agreement_margin": agreement_margin,
    }
    return gate
