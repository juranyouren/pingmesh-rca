from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from Sys_v1.RootCauseAnalyze.trust_trees.common import normalize_entries, score_key_for, unique_ips
from Sys_v1.RootCauseAnalyze.trust_trees.router import POLICY_VERSION, route_with_trust_trees
from Sys_v1.RootCauseAnalyze.trust_trees.temporal_tree import assess_temporal_tree
from Sys_v1.RootCauseAnalyze.trust_trees.topo_tree import assess_topo_tree


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
        "trust_trees": {"topo": empty_tree, "temporal": empty_tree},
    }


def assess_gate(
    skill_ret: str,
    *,
    high_margin: float = 15.0,
    agreement_margin: float = 8.0,
) -> Dict[str, Any]:
    """Assess trust-tree route for one case.

    The margin arguments are accepted for backward CLI compatibility. They are
    intentionally not used by the trust-tree policy.
    """
    data = _safe_load_skill_ret(skill_ret)
    if not data:
        return _invalid_gate("invalid_or_missing_rankings")

    combined_ips = _method_ips(data, "combined")
    topo_ips = _method_ips(data, "topo")
    temporal_ips = _method_ips(data, "temporal")
    if not combined_ips and not topo_ips and not temporal_ips:
        return _invalid_gate("invalid_or_missing_rankings")

    has_topo = isinstance(data.get("topo"), dict) and bool(topo_ips)
    has_temporal = isinstance(data.get("temporal"), dict) and bool(temporal_ips)
    if has_topo != has_temporal:
        method = "topo" if has_topo else "temporal"
        method_ips = topo_ips if has_topo else temporal_ips
        tree = (
            assess_topo_tree(data.get("topo", {}))
            if has_topo
            else assess_temporal_tree(data.get("temporal", {}))
        )
        strong = tree.get("state") == "strong"
        return {
            "enabled": True,
            "decision": "bypass_llm" if strong else "invoke_llm",
            "route": method if strong else "llm",
            "reason": (
                f"single_{method}_strong_accept"
                if strong
                else f"single_{method}_not_strong_invoke_llm"
            ),
            "policy_version": f"{POLICY_VERSION}_single_source",
            "recommended_ips": (method_ips or combined_ips)[:5],
            "agreement": {
                "rank_near": False,
                "top3_overlap": 0,
                "top3_overlap_ips": [],
                "method_top_ips": {
                    "topo": topo_ips[0] if topo_ips else None,
                    "temporal": temporal_ips[0] if temporal_ips else None,
                    "combined": combined_ips[0] if combined_ips else None,
                },
            },
            "trust_trees": {method: tree},
            "legacy_thresholds_ignored": {
                "high_margin": high_margin,
                "agreement_margin": agreement_margin,
            },
        }

    gate = route_with_trust_trees(
        combined_ips=combined_ips,
        topo_ips=topo_ips,
        temporal_ips=temporal_ips,
        topo_tree=assess_topo_tree(data.get("topo", {})),
        temporal_tree=assess_temporal_tree(data.get("temporal", {})),
    )
    gate["legacy_thresholds_ignored"] = {
        "high_margin": high_margin,
        "agreement_margin": agreement_margin,
    }
    return gate
