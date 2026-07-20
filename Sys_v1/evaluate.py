from __future__ import annotations

import argparse
import json
import os
from typing import Any, Mapping, Sequence

from Sys.utils.case_utils import read_gt_ips

from .config import ABLATION_SPECS


def _load_results(path: str) -> list[dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _best_rank(predicted: Sequence[str], ground_truth: Sequence[str]) -> int | None:
    positions = [predicted.index(ip) + 1 for ip in ground_truth if ip in predicted]
    return min(positions) if positions else None


def evaluate_results(
    result_sets: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    indexed = {
        name: {str(row.get("dir")): row for row in rows if row.get("dir")}
        for name, rows in result_sets.items()
    }
    all_dirs = sorted(set().union(*(set(rows) for rows in indexed.values()))) if indexed else []
    labeled_dirs = [case_dir for case_dir in all_dirs if read_gt_ips(case_dir)]

    summary: dict[str, Any] = {
        "denominator_policy": "union_of_case_paths_missing_output_counted_as_miss",
        "total_labeled_cases": len(labeled_dirs),
        "variants": {},
        "comparisons_vs_m1": {},
    }
    top1_hits: dict[str, dict[str, bool]] = {}

    for name, rows in indexed.items():
        hits = {1: 0, 3: 0, 5: 0}
        reciprocal_rank = 0.0
        missing_outputs = 0
        llm_requested = 0
        llm_executed = 0
        route_counts: dict[str, int] = {}
        per_case: dict[str, bool] = {}
        for case_dir in labeled_dirs:
            row = rows.get(case_dir)
            predicted = list(row.get("skill_ips", [])) if row else []
            if row is None:
                missing_outputs += 1
            gt = read_gt_ips(case_dir)
            rank = _best_rank(predicted, gt)
            for k in hits:
                hits[k] += int(rank is not None and rank <= k)
            reciprocal_rank += (1.0 / rank) if rank else 0.0
            per_case[case_dir] = rank == 1
            if row:
                llm = row.get("llm", {}) if isinstance(row.get("llm"), dict) else {}
                llm_requested += int(bool(llm.get("requested")))
                llm_executed += int(bool(llm.get("executed")))
                action = (row.get("confidence_gate", {}) or {}).get("action", "unknown")
                route_counts[action] = route_counts.get(action, 0) + 1

        total = len(labeled_dirs)
        summary["variants"][name] = {
            "correct_at_1": hits[1],
            "total": total,
            "top1_percent": round(hits[1] / total * 100, 2) if total else 0.0,
            "top3_percent": round(hits[3] / total * 100, 2) if total else 0.0,
            "top5_percent": round(hits[5] / total * 100, 2) if total else 0.0,
            "mrr": round(reciprocal_rank / total, 6) if total else 0.0,
            "llm_requested": llm_requested,
            "llm_executed": llm_executed,
            "missing_outputs": missing_outputs,
            "route_counts": route_counts,
        }
        top1_hits[name] = per_case

    baseline = top1_hits.get("m1", {})
    for name, values in top1_hits.items():
        if name == "m1" or not baseline:
            continue
        fix = sum(not baseline.get(case_dir, False) and values.get(case_dir, False) for case_dir in labeled_dirs)
        harm = sum(baseline.get(case_dir, False) and not values.get(case_dir, False) for case_dir in labeled_dirs)
        summary["comparisons_vs_m1"][name] = {
            "fix": fix,
            "harm": harm,
            "net_gain": fix - harm,
        }
    return summary


def _markdown_table(summary: Mapping[str, Any]) -> str:
    lines = [
        "| Experiment | Configuration | Correct@1 | Top-1 | Top-3 | Top-5 | MRR | Fix vs M1 | Harm vs M1 | Net Gain | LLM Calls |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name in ABLATION_SPECS:
        metrics = summary.get("variants", {}).get(name, {})
        comparison = summary.get("comparisons_vs_m1", {}).get(name, {})
        correct = f"{metrics.get('correct_at_1', 0)}/{metrics.get('total', 0)}"
        fix = "—" if name == "m1" else str(comparison.get("fix", 0))
        harm = "—" if name == "m1" else str(comparison.get("harm", 0))
        gain = "—" if name == "m1" else str(comparison.get("net_gain", 0))
        lines.append(
            "| {name} | {description} | {correct} | {top1:.2f}% | {top3:.2f}% | "
            "{top5:.2f}% | {mrr:.4f} | {fix} | {harm} | {gain} | {llm} |".format(
                name=name,
                description=ABLATION_SPECS[name].description,
                correct=correct,
                top1=float(metrics.get("top1_percent", 0.0)),
                top3=float(metrics.get("top3_percent", 0.0)),
                top5=float(metrics.get("top5_percent", 0.0)),
                mrr=float(metrics.get("mrr", 0.0)),
                fix=fix,
                harm=harm,
                gain=gain,
                llm=metrics.get("llm_executed", 0),
            )
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the four Sys_v1 ablations.")
    parser.add_argument("--results-root", required=True)
    args = parser.parse_args()

    result_sets = {
        name: _load_results(os.path.join(args.results_root, name, "res.json"))
        for name in ABLATION_SPECS
        if os.path.exists(os.path.join(args.results_root, name, "res.json"))
    }
    if not result_sets:
        parser.error("No <variant>/res.json files found under --results-root")

    summary = evaluate_results(result_sets)
    summary_path = os.path.join(args.results_root, "ablation_summary.json")
    table_path = os.path.join(args.results_root, "ablation_table.md")
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    with open(table_path, "w", encoding="utf-8") as handle:
        handle.write(_markdown_table(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Summary: {summary_path}")
    print(f"Table: {table_path}")


if __name__ == "__main__":
    main()
