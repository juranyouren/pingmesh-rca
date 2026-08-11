"""Evaluate whether the gate catches unsafe deterministic predictions.

The positive class is a deterministic combined-ranking miss.  A positive case
is recalled when the gate does not bypass the LLM.  This intentionally measures
gate routing safety rather than final LLM accuracy.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Sequence

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.Score.evaluate_trust_gate import (
    _case_id,
    _case_row,
    _dedupe,
    _detail_ips,
    _gt_ips,
    _load_json,
    _skill_details,
    _write_csv,
    _write_json,
    _write_jsonl,
)


def _hit_at(pred_ips: Sequence[str], gt_ips: Sequence[str], k: int) -> bool:
    return bool(gt_ips) and any(ip in set(pred_ips[:k]) for ip in gt_ips)


def _case_metrics(record: Dict[str, Any], index: int) -> Dict[str, Any]:
    details = _skill_details(record)
    combined_ips = _detail_ips(details, "combined") or _dedupe(record.get("skill_ips", []))
    routed = _case_row(record, index)
    gate = routed["gate"]
    gt_ips = _gt_ips(record)
    bypassed = gate.get("decision") == "bypass_llm"
    bypass_ips = list(gate.get("recommended_ips", [])) if bypassed else []

    row: Dict[str, Any] = {
        "case_id": _case_id(record.get("dir", ""), index),
        "case_dir": record.get("dir", ""),
        "gt_ips": gt_ips,
        "combined_ips": combined_ips,
        "decision": gate.get("decision"),
        "route": gate.get("route"),
        "reason": gate.get("reason"),
        "policy_version": gate.get("policy_version"),
        "bypass_ips": bypass_ips,
        "bypassed": bypassed,
        "safety_certificate": gate.get("safety_certificate", {}),
    }
    for k in (1, 3, 5):
        baseline_hit = _hit_at(combined_ips, gt_ips, k)
        bypass_hit = _hit_at(bypass_ips, gt_ips, k) if bypassed else None
        row[f"baseline_hit_at_{k}"] = baseline_hit
        row[f"needs_reinference_at_{k}"] = not baseline_hit
        row[f"caught_error_at_{k}"] = (not baseline_hit) and (not bypassed)
        row[f"unsafe_bypass_at_{k}"] = bypassed and not bool(bypass_hit)
        row[f"safe_bypass_at_{k}"] = bypassed and bool(bypass_hit)
    return row


def _metric_at(rows: Sequence[Dict[str, Any]], k: int) -> Dict[str, Any]:
    wrong = [row for row in rows if row[f"needs_reinference_at_{k}"]]
    caught = [row for row in wrong if row[f"caught_error_at_{k}"]]
    bypassed = [row for row in rows if row["bypassed"]]
    safe = [row for row in bypassed if row[f"safe_bypass_at_{k}"]]
    unsafe = [row for row in bypassed if row[f"unsafe_bypass_at_{k}"]]
    return {
        "k": k,
        "labeled_cases": len(rows),
        "deterministic_error_cases": len(wrong),
        "caught_error_cases": len(caught),
        "unsafe_bypass_count": len(unsafe),
        "error_recall": round(len(caught) / len(wrong), 6) if wrong else 1.0,
        "bypass_count": len(bypassed),
        "safe_bypass_count": len(safe),
        "bypass_precision": round(len(safe) / len(bypassed), 6) if bypassed else 1.0,
        "bypass_coverage": round(len(bypassed) / len(rows), 6) if rows else 0.0,
        "reinference_count": len(rows) - len(bypassed),
        "reinference_coverage": round((len(rows) - len(bypassed)) / len(rows), 6) if rows else 0.0,
    }


def evaluate_gate_recall(
    records: Sequence[Dict[str, Any]],
    *,
    out_dir: str,
    target_k: int = 1,
) -> Dict[str, Any]:
    if target_k not in {1, 3, 5}:
        raise ValueError("target_k must be one of 1, 3, or 5")

    all_rows = [_case_metrics(record, index) for index, record in enumerate(records)]
    rows = [row for row in all_rows if row["gt_ips"]]
    metrics = {str(k): _metric_at(rows, k) for k in (1, 3, 5)}
    target = metrics[str(target_k)]

    by_reason: Dict[str, Dict[str, int]] = defaultdict(lambda: {
        "cases": 0,
        "bypassed": 0,
        "caught_errors": 0,
        "unsafe_bypasses": 0,
    })
    for row in rows:
        reason = str(row.get("reason") or "unknown")
        bucket = by_reason[reason]
        bucket["cases"] += 1
        bucket["bypassed"] += int(row["bypassed"])
        bucket["caught_errors"] += int(row[f"caught_error_at_{target_k}"])
        bucket["unsafe_bypasses"] += int(row[f"unsafe_bypass_at_{target_k}"])

    reason_rows = [{"reason": reason, **counts} for reason, counts in sorted(by_reason.items())]
    summary = {
        "policy_version": next(
            (row.get("policy_version") for row in rows if row.get("policy_version")),
            "strict_fail_closed_v2",
        ),
        "input_cases": len(records),
        "labeled_cases": len(rows),
        "skipped_unlabeled_cases": len(all_rows) - len(rows),
        "target_k": target_k,
        "target": target,
        "metrics_at_k": metrics,
        "decision_counts": dict(Counter(row["decision"] for row in rows)),
        "reason_counts": dict(Counter(row["reason"] for row in rows)),
        "safety_target_passed": (
            target["unsafe_bypass_count"] == 0 and target["error_recall"] == 1.0
        ),
    }

    os.makedirs(out_dir, exist_ok=True)
    _write_jsonl(os.path.join(out_dir, "gate_recall_cases.jsonl"), rows)
    _write_json(os.path.join(out_dir, "gate_recall_summary.json"), summary)
    _write_csv(
        os.path.join(out_dir, "gate_recall_by_reason.csv"),
        reason_rows,
        ["reason", "cases", "bypassed", "caught_errors", "unsafe_bypasses"],
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure gate error recall and unsafe bypasses on labeled skillpipe results."
    )
    parser.add_argument("--res", required=True, help="Path to deterministic skillpipe res.json")
    parser.add_argument("--out-dir", required=True, help="Directory for gate recall reports")
    parser.add_argument("--target-k", type=int, choices=[1, 3, 5], default=1)
    parser.add_argument(
        "--assert-safe",
        action="store_true",
        help="Exit with status 2 unless error recall is 100%% and unsafe bypass count is zero.",
    )
    args = parser.parse_args()

    records = _load_json(args.res)
    if not isinstance(records, list):
        raise ValueError(f"{args.res} must contain a JSON list")
    summary = evaluate_gate_recall(records, out_dir=args.out_dir, target_k=args.target_k)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.assert_safe and not summary["safety_target_passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
