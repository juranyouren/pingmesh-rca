"""Confidence evidence extractor for LLM RCA reranking.

The previous margin/agreement bypass policy is intentionally disabled. This
module now records ranking evidence only; every valid case is still sent to LLM
until a new gate is designed from skillpipe failure statistics.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


POLICY_VERSION = "analysis_only_no_bypass"


def _safe_load_skill_ret(skill_ret: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(skill_ret)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _score_key(method: str) -> str:
    if method == "topo":
        return "pr_score"
    if method == "temporal":
        return "score"
    return "combined_score"


def _extract_rankings(data: Dict[str, Any], method: str) -> List[Dict[str, Any]]:
    if method == "combined":
        raw = data.get("combined_score_rankings", [])
    else:
        raw = (data.get(method, {}) or {}).get("rankings", [])
    return raw if isinstance(raw, list) else []


def _method_confidence(data: Dict[str, Any], method: str) -> Dict[str, Any]:
    rankings = _extract_rankings(data, method)
    score_key = _score_key(method)
    entries = [
        {
            "ip": item.get("ip"),
            "score": float(item.get(score_key, 0) or 0),
        }
        for item in rankings
        if isinstance(item, dict) and item.get("ip")
    ]
    entries.sort(key=lambda x: (-x["score"], x["ip"]))

    if not entries:
        return {"top_ip": None, "top_score": 0.0, "runner_up_score": 0.0, "margin": 0.0}

    top_score = entries[0]["score"]
    runner_up = entries[1]["score"] if len(entries) > 1 else 0.0
    return {
        "top_ip": entries[0]["ip"],
        "top_score": round(top_score, 4),
        "runner_up_score": round(runner_up, 4),
        "margin": round(top_score - runner_up, 4),
    }


def _combined_ips(data: Dict[str, Any], limit: int = 3) -> List[str]:
    ips = []
    for item in _extract_rankings(data, "combined")[:limit]:
        if isinstance(item, dict):
            ip = item.get("ip")
            if ip and ip not in ips:
                ips.append(ip)
    return ips


def assess_gate(
    skill_ret: str,
    *,
    high_margin: float = 15.0,
    agreement_margin: float = 8.0,
) -> Dict[str, Any]:
    """Extract confidence evidence for one case without bypassing LLM."""
    data = _safe_load_skill_ret(skill_ret)
    if not data:
        return {
            "enabled": True,
            "decision": "invoke_llm",
            "reason": "invalid_or_missing_rankings",
            "policy_version": POLICY_VERSION,
            "methods": {},
            "agreement": {"top1_votes_for_combined": 0, "method_top_ips": {}},
            "recommended_ips": [],
        }

    methods = {
        name: _method_confidence(data, name)
        for name in ("combined", "topo", "temporal")
    }
    combined_top = methods["combined"]["top_ip"]
    if not combined_top:
        return {
            "enabled": True,
            "decision": "invoke_llm",
            "reason": "invalid_or_missing_rankings",
            "policy_version": POLICY_VERSION,
            "methods": methods,
            "agreement": {"top1_votes_for_combined": 0, "method_top_ips": {}},
            "recommended_ips": [],
        }

    method_top_ips = {name: info["top_ip"] for name, info in methods.items()}
    votes = sum(1 for ip in method_top_ips.values() if ip == combined_top)

    return {
        "enabled": True,
        "decision": "invoke_llm",
        "reason": "gate_design_pending_failure_analysis",
        "policy_version": POLICY_VERSION,
        "legacy_thresholds_ignored": {
            "high_margin": high_margin,
            "agreement_margin": agreement_margin,
        },
        "methods": methods,
        "agreement": {
            "top1_votes_for_combined": votes,
            "method_top_ips": method_top_ips,
        },
        "recommended_ips": _combined_ips(data),
    }


def make_bypass_response(gate: Dict[str, Any]) -> str:
    """Build a Score_N-compatible JSON response for future bypassed cases."""
    payload = {
        "reasoning": (
            "Confidence gate bypassed LLM reranking. "
            f"reason={gate.get('reason')}; "
            f"combined_margin={gate.get('methods', {}).get('combined', {}).get('margin', 0)}"
        ),
        "ip": gate.get("recommended_ips", [])[:3],
    }
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
