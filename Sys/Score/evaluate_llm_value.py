from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.Score.credence_artifact_utils import read_jsonl, safe_float, write_csv


def _region(row: Dict[str, Any]) -> str:
    confidence = safe_float(row.get("raw_confidence_score"))
    diagnosability = safe_float(row.get("diagnosability_score"))
    if confidence >= 0.75:
        return "high_confidence"
    if diagnosability < 0.55:
        return "low_diagnosability"
    return "ambiguous"


def _summarize(name: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    labeled = [row for row in rows if row.get("deterministic_hit_top1") is not None and row.get("llm_hit_top1") is not None]
    det_hits = sum(1 for row in labeled if row.get("deterministic_hit_top1"))
    llm_hits = sum(1 for row in labeled if row.get("llm_hit_top1"))
    rescue = sum(1 for row in labeled if not row.get("deterministic_hit_top1") and row.get("llm_hit_top1"))
    harm = sum(1 for row in labeled if row.get("deterministic_hit_top1") and not row.get("llm_hit_top1"))
    n = len(labeled)
    return {
        "region_or_bin": name,
        "n": n,
        "deterministic_hits": det_hits,
        "llm_hits": llm_hits,
        "rescue": rescue,
        "harm": harm,
        "rescue_rate": round(rescue / n, 6) if n else None,
        "harm_rate": round(harm / n, 6) if n else None,
        "net_utility": rescue - harm,
        "avg_latency_ms": None,
        "avg_tokens": None,
    }


def evaluate_llm_value(*, cases_path: str, out_path: str) -> List[Dict[str, Any]]:
    rows = read_jsonl(cases_path)
    by_region: Dict[str, List[Dict[str, Any]]] = {"all": rows}
    for row in rows:
        by_region.setdefault(_region(row), []).append(row)
    summaries = [_summarize(name, by_region[name]) for name in sorted(by_region)]
    summaries.sort(key=lambda row: (row["region_or_bin"] != "all", row["region_or_bin"]))
    write_csv(
        out_path,
        [
            "region_or_bin",
            "n",
            "deterministic_hits",
            "llm_hits",
            "rescue",
            "harm",
            "rescue_rate",
            "harm_rate",
            "net_utility",
            "avg_latency_ms",
            "avg_tokens",
        ],
        summaries,
    )
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate LLM rescue/harm by confidence region.")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--calibration", default=None, help="Accepted for runbook compatibility")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rows = evaluate_llm_value(cases_path=args.cases, out_path=args.out)
    print(f"llm value rows={len(rows)} -> {args.out}")


if __name__ == "__main__":
    main()
