from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Sequence

from Sys_v1.RootCauseAnalyze.gate.response import make_bypass_response
from Sys_v1.Score.evaluate_trust_gate import _case_row, _load_json


def _empty_llm_response(gate: Dict[str, Any]) -> str:
    payload = {
        "reasoning": (
            "Trust-tree gate selected LLM arbitration, but this is the offline gate+pipe "
            f"experiment with no LLM call. route={gate.get('route')}; reason={gate.get('reason')}"
        ),
        "ip": [],
    }
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"


def _response_for_gate(gate: Dict[str, Any]) -> str:
    if gate.get("decision") in {"bypass_llm", "operator_review"}:
        return make_bypass_response(gate)
    return _empty_llm_response(gate)


def _evaluated_ips(gate: Dict[str, Any]) -> List[str]:
    if gate.get("decision") == "bypass_llm":
        return list(gate.get("recommended_ips", [])[:5])
    return []


def apply_trust_gate_records(
    records: Sequence[Dict[str, Any]],
    *,
    output_path: str | None = None,
) -> List[Dict[str, Any]]:
    converted: List[Dict[str, Any]] = []
    for index, record in enumerate(records):
        row = _case_row(record, index)
        gate = row["gate"]
        new_record = dict(record)
        new_record["confidence_gate"] = gate
        new_record["gate_route"] = gate.get("route")
        new_record["gate_decision"] = gate.get("decision")
        new_record["skill_ips"] = _evaluated_ips(gate)
        new_record["response"] = _response_for_gate(gate)
        converted.append(new_record)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(converted, f, ensure_ascii=False, indent=2)
    return converted


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply trust-tree gate to skillpipe res.json without calling LLM.")
    parser.add_argument("--res", required=True, help="Input skillpipe res.json")
    parser.add_argument("--out", required=True, help="Output gated res.json")
    args = parser.parse_args()

    records = _load_json(args.res)
    if not isinstance(records, list):
        raise ValueError(f"{args.res} must contain a JSON list")
    converted = apply_trust_gate_records(records, output_path=args.out)
    route_counts: Dict[str, int] = {}
    for record in converted:
        route = record.get("gate_route", "unknown")
        route_counts[route] = route_counts.get(route, 0) + 1
    print(json.dumps({"total_cases": len(converted), "route_counts": route_counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
