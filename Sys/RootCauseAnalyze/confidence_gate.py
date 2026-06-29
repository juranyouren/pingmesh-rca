"""
Confidence gate for LLM RCA reranking.

The gate reads the structured evidence JSON already produced by
`evidence_fusion.build_fused_evidence` and decides whether the deterministic
topology/temporal ranking is confident enough to bypass LLM reranking.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


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
    entries.sort(key=lambda x: x["score"], reverse=True)

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
    """
    Decide whether to bypass LLM reranking for one case.

    Returns a JSON-serializable dict with:
      - decision: "bypass_llm" or "invoke_llm"
      - reason: compact machine-readable reason
      - methods: per-method top score and margin
      - agreement: method agreement with combined top-1
      - recommended_ips: deterministic top combined candidates
    """
    data = _safe_load_skill_ret(skill_ret)
    if not data:
        return {
            "enabled": True,
            "decision": "invoke_llm",
            "reason": "invalid_or_missing_rankings",
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
            "methods": methods,
            "agreement": {"top1_votes_for_combined": 0, "method_top_ips": {}},
            "recommended_ips": [],
        }

    method_top_ips = {name: info["top_ip"] for name, info in methods.items()}
    votes = sum(1 for ip in method_top_ips.values() if ip == combined_top)
    recommended_ips = _combined_ips(data)

    decision = "invoke_llm"
    reason = "low_confidence_or_disagreement"
    if methods["combined"]["margin"] >= high_margin:
        decision = "bypass_llm"
        reason = "combined_high_margin"
    elif votes >= 2 and methods["combined"]["margin"] >= agreement_margin:
        decision = "bypass_llm"
        reason = "method_agreement"

    return {
        "enabled": True,
        "decision": decision,
        "reason": reason,
        "thresholds": {
            "high_margin": high_margin,
            "agreement_margin": agreement_margin,
        },
        "methods": methods,
        "agreement": {
            "top1_votes_for_combined": votes,
            "method_top_ips": method_top_ips,
        },
        "recommended_ips": recommended_ips,
    }


def make_bypass_response(gate: Dict[str, Any]) -> str:
    """Build a Score_N-compatible JSON response for bypassed cases."""
    payload = {
        "reasoning": (
            "置信度门控判定算法排名足够可靠，跳过 LLM 重排。"
            f" reason={gate.get('reason')}; "
            f"combined_margin={gate.get('methods', {}).get('combined', {}).get('margin', 0)}"
        ),
        "ip": gate.get("recommended_ips", [])[:3],
    }
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
