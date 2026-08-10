#!/usr/bin/env python3
"""Extract cases where Gate bypassed the LLM but missed the true root cause.

The current ``run_ablation_study.py`` writes Gate information and the initial
ranking to ``res.json``, but it deliberately reads labels only during the
evaluation stage.  Therefore this script uses the ``dir`` field in each result
row to load ``label_v2.json`` (or the legacy ``label.json``) when needed.

Example:
    python scripts/extract_gate_badcases.py \
        /path/to/all_llm_prompt_compare/res.json

The default output is written beside ``res.json`` as:
    gate_badcases.jsonl
    gate_badcases.csv
    gate_badcases_summary.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


PASS_DECISIONS = {
    "bypass_llm",
    "pass",
    "passed",
    "gate_accept",
    "accept",
    "skip_llm",
    "no_llm",
    "bypass",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def load_result_rows(path: Path) -> List[Dict[str, Any]]:
    data = load_json(path)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("results", "records", "cases", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    raise ValueError(f"Unsupported res.json structure: {path}")


def extract_ips(value: Any) -> List[str]:
    """Match the flexible label_v2 IP extraction used by Score_N.py."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, dict):
        for key in ("ip", "mgmt_ip", "device_ip"):
            ip = value.get(key)
            if ip:
                return [str(ip)]
        return []
    if isinstance(value, list):
        result: List[str] = []
        for item in value:
            for ip in extract_ips(item):
                if ip not in result:
                    result.append(ip)
        return result
    return []


def ground_truth_from_label(case_dir: Path) -> Tuple[List[str], str]:
    label_v2 = case_dir / "label_v2.json"
    if label_v2.exists():
        labels = load_json(label_v2)
        if isinstance(labels, dict):
            ips: List[str] = []
            for key in (
                "primary_root_cause",
                "primary_root_causes",
                "secondary_root_causes",
                "root_causes",
            ):
                for ip in extract_ips(labels.get(key)):
                    if ip not in ips:
                        ips.append(ip)
            if ips:
                return ips, "label_v2.json"

    legacy = case_dir / "label.json"
    if legacy.exists():
        labels = load_json(legacy)
        if isinstance(labels, list):
            ips: List[str] = []
            for item in sorted(labels, key=lambda value: value.get("ranking", 999))[:3]:
                if not isinstance(item, dict):
                    continue
                for abnormal_node in item.get("abnormal_node", []) or []:
                    if isinstance(abnormal_node, dict):
                        ip = abnormal_node.get("ip")
                        if ip and ip not in ips:
                            ips.append(str(ip))
            if ips:
                return ips, "label.json:top3_ranking"

    return [], ""


def ground_truth_for_row(
    row: Dict[str, Any], res_path: Path, data_root: Path | None
) -> Tuple[List[str], str]:
    # This also supports a future res.json that already embeds evaluation data.
    evaluation = row.get("evaluation")
    if isinstance(evaluation, dict):
        embedded = extract_ips(evaluation.get("ground_truth_ips"))
        if embedded:
            return embedded, str(evaluation.get("ground_truth_source", "embedded"))
    embedded = extract_ips(row.get("ground_truth_ips"))
    if embedded:
        return embedded, "res.json"

    raw_dir = row.get("dir") or row.get("source_dir")
    if not raw_dir:
        return [], ""
    case_dir = Path(str(raw_dir))
    if not case_dir.is_absolute():
        case_dir = (data_root or res_path.parent) / case_dir
    return ground_truth_from_label(case_dir)


def get_gate(row: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("confidence_gate", "gate"):
        value = row.get(key)
        if isinstance(value, dict):
            return value
    return {}


def gate_decisions(gate: Dict[str, Any]) -> Tuple[str, str]:
    """Return (natural_decision, effective_decision).

    Full-LLM modes overwrite ``decision`` with ``invoke_llm`` while preserving
    the original Gate decision in ``natural_decision``.  The natural decision
    is therefore the one that must be used for Gate analysis.
    """
    natural = str(gate.get("natural_decision") or "").strip().lower()
    effective = str(gate.get("decision") or "").strip().lower()
    if not natural:
        natural = effective
    return natural, effective


def as_ips(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        if isinstance(item, str):
            ip = item
        elif isinstance(item, dict):
            ip = item.get("ip") or item.get("candidate_ip")
        else:
            ip = None
        if ip and str(ip) not in result:
            result.append(str(ip))
    return result


def initial_ranking(row: Dict[str, Any]) -> List[str]:
    for key in ("skill_ips", "initial_ranking", "baseline_ranking"):
        ranking = as_ips(row.get(key))
        if ranking:
            return ranking
    ranking_evidence = row.get("ranking_evidence")
    if isinstance(ranking_evidence, dict):
        for key in ("initial_ranking", "baseline_ranking", "ranking"):
            ranking = as_ips(ranking_evidence.get(key))
            if ranking:
                return ranking
    return []


def extract_badcases(
    rows: Sequence[Dict[str, Any]],
    res_path: Path,
    top_k: int,
    data_root: Path | None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    selected: List[Dict[str, Any]] = []
    counters = {
        "input_rows": len(rows),
        "gate_pass_rows": 0,
        "selected_rows": 0,
        "skipped_no_ground_truth": 0,
        "skipped_no_ranking": 0,
    }

    for row in rows:
        gate = get_gate(row)
        natural_decision, effective_decision = gate_decisions(gate)
        if natural_decision not in PASS_DECISIONS:
            continue
        counters["gate_pass_rows"] += 1

        ranking = initial_ranking(row)
        if not ranking:
            counters["skipped_no_ranking"] += 1
            continue
        ground_truth, ground_truth_source = ground_truth_for_row(
            row, res_path, data_root
        )
        if not ground_truth:
            counters["skipped_no_ground_truth"] += 1
            continue

        top = ranking[:top_k]
        missing = [ip for ip in ground_truth if ip not in top]
        if not missing:
            continue

        counters["selected_rows"] += 1
        selected.append(
            {
                "case_id": row.get("case_id", ""),
                "dir": row.get("dir", row.get("source_dir", "")),
                "ablation": row.get("ablation", ""),
                "prompt_variant": row.get("prompt_variant", ""),
                "gate_confidence": gate.get("confidence", ""),
                "gate_natural_decision": natural_decision,
                "gate_effective_decision": effective_decision,
                "gate_route": gate.get("route", ""),
                "gate_reason": gate.get("reason", ""),
                "forced_llm": bool(gate.get("forced_llm", False)),
                "reran_with_llm": bool(row.get("reran_with_llm", False)),
                "baseline_top_k": top,
                "ground_truth_ips": ground_truth,
                "missing_ground_truth_ips": missing,
                "ground_truth_source": ground_truth_source,
            }
        )

    return selected, counters


def write_jsonl(rows: Iterable[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(rows: Sequence[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id",
        "dir",
        "ablation",
        "prompt_variant",
        "gate_confidence",
        "gate_natural_decision",
        "gate_effective_decision",
        "gate_route",
        "gate_reason",
        "forced_llm",
        "reran_with_llm",
        "baseline_top_k",
        "ground_truth_ips",
        "missing_ground_truth_ips",
        "ground_truth_source",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(row[key], ensure_ascii=False)
                    if isinstance(row.get(key), list)
                    else row.get(key, "")
                    for key in fields
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Gate-pass cases whose true root cause is outside baseline Top-K."
    )
    parser.add_argument("res_json", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSONL output path; defaults to <res-dir>/gate_badcases.jsonl",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Optional root for relative case dirs stored in res.json",
    )
    args = parser.parse_args()

    if args.top_k <= 0:
        parser.error("--top-k must be positive")
    res_path = args.res_json.resolve()
    rows = load_result_rows(res_path)
    selected, counters = extract_badcases(
        rows,
        res_path=res_path,
        top_k=args.top_k,
        data_root=args.data_root.resolve() if args.data_root else None,
    )

    jsonl_path = (
        args.output.resolve()
        if args.output
        else res_path.parent / "gate_badcases.jsonl"
    )
    csv_path = jsonl_path.with_suffix(".csv")
    summary_path = jsonl_path.with_name("gate_badcases_summary.json")
    write_jsonl(selected, jsonl_path)
    write_csv(selected, csv_path)
    save_json(
        {
            "source": str(res_path),
            "top_k": args.top_k,
            **counters,
            "output_jsonl": str(jsonl_path),
            "output_csv": str(csv_path),
        },
        summary_path,
    )
    print(
        f"[gate-badcases] input={counters['input_rows']} "
        f"gate_pass={counters['gate_pass_rows']} "
        f"selected={counters['selected_rows']} "
        f"no_gt={counters['skipped_no_ground_truth']} "
        f"-> {jsonl_path}"
    )


if __name__ == "__main__":
    main()
