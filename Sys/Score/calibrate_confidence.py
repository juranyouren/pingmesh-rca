from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.Score.credence_artifact_utils import (
    brier_score,
    bootstrap_ci,
    clopper_pearson_upper,
    mean,
    read_jsonl,
    safe_float,
    write_csv,
    write_json,
)


def _eligible(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if row.get("label_available") and row.get("deterministic_hit_top1") is not None]


def _thresholds(rows: List[Dict[str, Any]]) -> List[float]:
    vals = sorted({safe_float(row.get("raw_confidence_score")) for row in rows}, reverse=True)
    return vals or [1.0]


def _risk_rows(rows: List[Dict[str, Any]], risk_budget: float, delta: float) -> List[Dict[str, Any]]:
    thresholds = _thresholds(rows)
    adjusted_delta = delta / max(1, len(thresholds))
    out = []
    n_total = len(rows)
    for threshold in thresholds:
        selected = [row for row in rows if safe_float(row.get("raw_confidence_score")) >= threshold]
        n_selected = len(selected)
        wrong = sum(1 for row in selected if row.get("deterministic_hit_top1") is False)
        upper = clopper_pearson_upper(wrong, n_selected, adjusted_delta) if n_selected else 1.0
        out.append(
            {
                "threshold": threshold,
                "n_selected": n_selected,
                "n_total": n_total,
                "coverage": round(n_selected / n_total, 6) if n_total else 0.0,
                "wrong_bypass_count": wrong,
                "wrong_bypass_rate": round(wrong / n_selected, 6) if n_selected else None,
                "wrong_bypass_upper": upper,
                "alpha": risk_budget,
                "selected": False,
            }
        )
    valid = [row for row in out if row["n_selected"] > 0 and row["wrong_bypass_upper"] <= risk_budget]
    if valid:
        chosen = max(valid, key=lambda row: (row["coverage"], -row["wrong_bypass_upper"]))
        chosen["selected"] = True
    return out


def _calibration_bins(rows: List[Dict[str, Any]], bins: int) -> List[Dict[str, Any]]:
    sorted_rows = sorted(rows, key=lambda row: safe_float(row.get("raw_confidence_score")))
    if not sorted_rows:
        return []
    bins = max(1, min(bins, len(sorted_rows)))
    out = []
    for idx in range(bins):
        start = round(idx * len(sorted_rows) / bins)
        end = round((idx + 1) * len(sorted_rows) / bins)
        group = sorted_rows[start:end]
        confs = [safe_float(row.get("raw_confidence_score")) for row in group]
        hits = [1.0 if row.get("deterministic_hit_top1") else 0.0 for row in group]
        mean_conf = mean(confs)
        empirical = mean(hits)
        out.append(
            {
                "bin_id": idx,
                "n": len(group),
                "confidence_min": min(confs) if confs else None,
                "confidence_max": max(confs) if confs else None,
                "mean_confidence": mean_conf,
                "empirical_accuracy": empirical,
                "brier": brier_score(group),
                "ece_component": round(abs((mean_conf or 0.0) - (empirical or 0.0)) * len(group) / len(sorted_rows), 6),
            }
        )
    return out


def calibrate_confidence(
    *,
    cases_path: str,
    out_dir: str,
    risk_budget: float = 0.1,
    delta: float = 0.05,
    bins: int = 5,
    bootstrap_repeats: int = 1000,
    seed: int = 17,
) -> Dict[str, Any]:
    rows = _eligible(read_jsonl(cases_path))
    os.makedirs(out_dir, exist_ok=True)

    risk_rows = _risk_rows(rows, risk_budget, delta)
    bin_rows = _calibration_bins(rows, bins)
    selected = next((row for row in risk_rows if row["selected"]), None)

    write_csv(
        os.path.join(out_dir, "risk_coverage.csv"),
        [
            "threshold",
            "n_selected",
            "n_total",
            "coverage",
            "wrong_bypass_count",
            "wrong_bypass_rate",
            "wrong_bypass_upper",
            "alpha",
            "selected",
        ],
        risk_rows,
    )
    write_csv(
        os.path.join(out_dir, "calibration_bins.csv"),
        [
            "bin_id",
            "n",
            "confidence_min",
            "confidence_max",
            "mean_confidence",
            "empirical_accuracy",
            "brier",
            "ece_component",
        ],
        bin_rows,
    )

    paired_rows = [
        {
            "case_id": row.get("case_id"),
            "label_available": row.get("label_available"),
            "deterministic_top1": row.get("deterministic_hit_top1"),
            "llm_top1": row.get("llm_hit_top1"),
            "credence_top1": row.get("final_hit_top1"),
            "credence_action": "BYPASS" if selected and safe_float(row.get("raw_confidence_score")) >= selected["threshold"] else "ARBITRATE",
            "confidence": row.get("raw_confidence_score"),
            "diagnosability": row.get("diagnosability_score"),
        }
        for row in rows
    ]
    write_csv(
        os.path.join(out_dir, "paired_case_outcomes.csv"),
        [
            "case_id",
            "label_available",
            "deterministic_top1",
            "llm_top1",
            "credence_top1",
            "credence_action",
            "confidence",
            "diagnosability",
        ],
        paired_rows,
    )

    det_values = [1.0 if row.get("deterministic_hit_top1") else 0.0 for row in rows]
    llm_values = [1.0 if row.get("llm_hit_top1") else 0.0 for row in rows if row.get("llm_hit_top1") is not None]
    bootstrap_rows = []
    for metric, values in [("deterministic_top1", det_values), ("llm_top1", llm_values)]:
        ci = bootstrap_ci(values, bootstrap_repeats, seed)
        bootstrap_rows.append(
            {
                "metric": metric,
                **ci,
                "n_cases": len(values),
                "bootstrap_repeats": bootstrap_repeats,
                "seed": seed,
            }
        )
    write_csv(
        os.path.join(out_dir, "bootstrap_intervals.csv"),
        ["metric", "estimate", "ci_low", "ci_high", "n_cases", "bootstrap_repeats", "seed"],
        bootstrap_rows,
    )

    calibration = {
        "cases_path": cases_path,
        "calibration_method": "target_only_threshold_frontier",
        "risk_budget": risk_budget,
        "delta": delta,
        "threshold_count": len(risk_rows),
        "target_calibration_cases": len(rows),
        "selected_threshold": selected["threshold"] if selected else None,
        "no_safe_threshold": selected is None,
        "selected_calibration_cases": selected["n_selected"] if selected else 0,
        "wrong_bypass_count": selected["wrong_bypass_count"] if selected else None,
        "wrong_bypass_upper": selected["wrong_bypass_upper"] if selected else None,
        "brier": brier_score(rows),
        "ece": round(sum(row["ece_component"] for row in bin_rows), 6) if bin_rows else None,
        "feature_set": "raw_confidence_score_from_confidence_gate",
        "excluded_label_only_fields": [
            "gt_ips",
            "deterministic_hit_top1",
            "llm_hit_top1",
            "final_hit_top1",
        ],
    }
    write_json(os.path.join(out_dir, "confidence_calibration.json"), calibration)
    return calibration


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate CREDENCE confidence artifacts.")
    parser.add_argument("--cases", required=True, help="Path to confidence_cases.jsonl")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--risk-budget", type=float, default=0.1)
    parser.add_argument("--delta", type=float, default=0.05)
    parser.add_argument("--bins", type=int, default=5)
    parser.add_argument("--bootstrap-repeats", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    result = calibrate_confidence(
        cases_path=args.cases,
        out_dir=args.out_dir,
        risk_budget=args.risk_budget,
        delta=args.delta,
        bins=args.bins,
        bootstrap_repeats=args.bootstrap_repeats,
        seed=args.seed,
    )
    print(f"calibration written -> {os.path.join(args.out_dir, 'confidence_calibration.json')}")
    print(result)


if __name__ == "__main__":
    main()
