from __future__ import annotations

import json
from typing import Any, Dict, List


def make_bypass_response(gate: Dict[str, Any]) -> str:
    """Build a Score_N-compatible JSON response for routed non-LLM cases."""
    decision = gate.get("decision")
    route = gate.get("route")
    ips: List[str] = [] if decision == "operator_review" else gate.get("recommended_ips", [])[:3]
    payload = {
        "reasoning": (
            "Trust-tree gate routed RCA without LLM final reranking. "
            f"decision={decision}; route={route}; reason={gate.get('reason')}"
        ),
        "ip": ips,
    }
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
