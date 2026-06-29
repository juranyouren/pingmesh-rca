from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Any, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.Score.credence_artifact_utils import mean, read_jsonl, safe_float, write_csv


def _diag_bin(score: float) -> str:
    if score < 0.55:
        return "low"
    if score < 0.8:
        return "medium"
    return "high"


def _rate(rows: List[Dict[str, Any]], key: str) -> float | None:
    vals = [1.0 if row.get(key) else 0.0 for row in rows if row.get(key) is not None]
    return mean(vals)


def evaluate_diagnosability(*, cases_path: str, out_path: str) -> List[Dict[str, Any]]:
    rows = read_jsonl(cases_path)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_diag_bin(safe_float(row.get("diagnosability_score"))), []).append(row)

    output = []
    for bin_name in ["low", "medium", "high"]:
        group = grouped.get(bin_name, [])
        reasons = Counter()
        for row in group:
            for field in row.get("missing_fields") or []:
                reasons[field] += 1
        rescue_count = sum(1 for row in group if row.get("deterministic_hit_top1") is False and row.get("llm_hit_top1") is True)
        harm_count = sum(1 for row in group if row.get("deterministic_hit_top1") is True and row.get("llm_hit_top1") is False)
        n = len(group)
        output.append(
            {
                "diagnosability_bin": bin_name,
                "n": n,
                "top1": _rate(group, "deterministic_hit_top1"),
                "top3": _rate(group, "deterministic_hit_top3"),
                "top5": _rate(group, "deterministic_hit_top5"),
                "llm_rescue_rate": round(rescue_count / n, 6) if n else None,
                "llm_harm_rate": round(harm_count / n, 6) if n else None,
                "escalate_rate": 1.0 if bin_name == "low" and n else 0.0,
                "missing_evidence_top_reason": reasons.most_common(1)[0][0] if reasons else None,
            }
        )
    write_csv(
        out_path,
        [
            "diagnosability_bin",
            "n",
            "top1",
            "top3",
            "top5",
            "llm_rescue_rate",
            "llm_harm_rate",
            "escalate_rate",
            "missing_evidence_top_reason",
        ],
        output,
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CREDENCE diagnosability frontier.")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rows = evaluate_diagnosability(cases_path=args.cases, out_path=args.out)
    print(f"diagnosability rows={len(rows)} -> {args.out}")


if __name__ == "__main__":
    main()
