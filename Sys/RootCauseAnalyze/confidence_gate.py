"""Trust-tree gate for LLM RCA reranking.

The gate no longer computes a continuous confidence score. It evaluates two
ranker-specific trust trees (topology and temporal) and routes each case to a
deterministic ranker, LLM arbitration, or operator review.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from Sys.RootCauseAnalyze.trust_trees.common import normalize_entries, score_key_for, unique_ips
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

    topo_tree = assess_topo_tree(data.get("topo", {}))
    temporal_tree = assess_temporal_tree(data.get("temporal", {}))
    gate = route_with_trust_trees(
        combined_ips=combined_ips,
        topo_ips=topo_ips,
        temporal_ips=temporal_ips,
        topo_tree=topo_tree,
        temporal_tree=temporal_tree,
    )
    gate["legacy_thresholds_ignored"] = {
        "high_margin": high_margin,
        "agreement_margin": agreement_margin,
    }
    return gate


def make_bypass_response(gate: Dict[str, Any]) -> str:
    """Build a Score_N-compatible JSON response for routed non-LLM cases."""
    decision = gate.get("decision")
    route = gate.get("route")
    if decision == "operator_review":
        ips: List[str] = []
    else:
        ips = gate.get("recommended_ips", [])[:3]

    payload = {
        "reasoning": (
            "Trust-tree gate routed RCA without LLM final reranking. "
            f"decision={decision}; route={route}; reason={gate.get('reason')}"
        ),
        "ip": ips,
    }
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
