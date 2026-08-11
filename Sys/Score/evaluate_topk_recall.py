#!/usr/bin/env python3
"""Evaluate topology, temporal, and fused Top-K recall from skillpipe results."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Sequence

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.Score.evaluate_trust_gate import (
    _case_id,
    _dedupe,
    _detail_ips,
    _gt_ips,
    _load_json,
    _skill_details,
    _write_csv,
    _write_json,
    _write_jsonl,
)


DEFAULT_K_VALUES = (1, 3, 5, 7, 10)
METHOD_KEYS = {"combined": "combined", "topology": "1", "temporal": "2"}


def _normalize_k_values(values: Sequence[int]) -> List[int]:
    normalized = sorted({int(value) for value in values if int(value) > 0})
    if not normalized:
        raise ValueError("at least one positive k value is required")
    return normalized


def _best_rank(ground_truth_ips: Sequence[str], ranking: Sequence[str]) -> int | None:
    positions = {ip: index + 1 for index, ip in enumerate(ranking)}
    matches = [positions[ip] for ip in ground_truth_ips if ip in positions]
    return min(matches) if matches else None


def _method_rankings(record: Dict[str, Any]) -> Dict[str, List[str]]:
    details = _skill_details(record)
    return {
        method: (
            _detail_ips(details, key)
            or (_dedupe(record.get("skill_ips", [])) if method == "combined" else [])
        )
        for method, key in METHOD_KEYS.items()
    }


def build_case_rows(
    records: Sequence[Dict[str, Any]], k_values: Sequence[int]
) -> List[Dict[str, Any]]:
    normalized_k = _normalize_k_values(k_values)
    rows: List[Dict[str, Any]] = []
    for index, record in enumerate(records):
        gt_ips = _gt_ips(record)
        if not gt_ips:
            continue
        case_id = _case_id(str(record.get("dir") or ""), index)
        for method, ranking in _method_rankings(record).items():
            row: Dict[str, Any] = {
                "case_id": case_id,
                "case_dir": record.get("dir", ""),
                "method": method,
                "gt_ips": gt_ips,
                "ranking": ranking,
                "best_rank": _best_rank(gt_ips, ranking),
            }
            for k in normalized_k:
                row[f"hit_at_{k}"] = any(ip in set(ranking[:k]) for ip in gt_ips)
            rows.append(row)
    return rows


def summarize_recall(
    records: Sequence[Dict[str, Any]], k_values: Sequence[int]
) -> Dict[str, Any]:
    normalized_k = _normalize_k_values(k_values)
    rows = build_case_rows(records, normalized_k)
    methods: Dict[str, Dict[str, Any]] = {}
    for method in METHOD_KEYS:
        method_rows = [row for row in rows if row["method"] == method]
        by_k: Dict[str, Any] = {}
        for k in normalized_k:
            hits = sum(bool(row[f"hit_at_{k}"]) for row in method_rows)
            total = len(method_rows)
            by_k[str(k)] = {
                "evaluated_case_count": total,
                "hit_count": hits,
                "miss_count": total - hits,
                "recall": round(hits / total, 6) if total else 0.0,
            }
        methods[method] = by_k
    return {
        "k_values": normalized_k,
        "labeled_case_count": len(rows) // len(METHOD_KEYS),
        "methods": methods,
    }


def _summary_rows(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {"method": method, "k": k, **by_k[str(k)]}
        for method, by_k in summary["methods"].items()
        for k in summary["k_values"]
    ]


def _flat_case_rows(rows: Iterable[Dict[str, Any]], k_values: Sequence[int]) -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []
    for row in rows:
        flattened.append(
            {
                "case_id": row["case_id"],
                "case_dir": row["case_dir"],
                "method": row["method"],
                "gt_ips": "|".join(row["gt_ips"]),
                "best_rank": row["best_rank"] or "not_ranked",
                "top10_ips": "|".join(row["ranking"][:10]),
                **{f"hit_at_{k}": int(row[f"hit_at_{k}"]) for k in k_values},
            }
        )
    return flattened


def evaluate_topk_recall(
    records: Sequence[Dict[str, Any]], *, out_dir: str, k_values: Sequence[int]
) -> Dict[str, Any]:
    normalized_k = _normalize_k_values(k_values)
    case_rows = build_case_rows(records, normalized_k)
    summary = summarize_recall(records, normalized_k)
    summary.update(
        {
            "input_case_count": len(records),
            "skipped_unlabeled_case_count": len(records) - summary["labeled_case_count"],
        }
    )
    os.makedirs(out_dir, exist_ok=True)
    _write_json(os.path.join(out_dir, "topk_recall_summary.json"), summary)
    _write_jsonl(os.path.join(out_dir, "topk_recall_cases.jsonl"), case_rows)
    _write_csv(
        os.path.join(out_dir, "topk_recall.csv"),
        _summary_rows(summary),
        ("method", "k", "evaluated_case_count", "hit_count", "miss_count", "recall"),
    )
    flat_rows = _flat_case_rows(case_rows, normalized_k)
    case_fields = ["case_id", "case_dir", "method", "gt_ips", "best_rank", "top10_ips"]
    case_fields.extend(f"hit_at_{k}" for k in normalized_k)
    _write_csv(os.path.join(out_dir, "topk_recall_cases.csv"), flat_rows, case_fields)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Top-K recall from deterministic skillpipe res.json."
    )
    parser.add_argument("--res", required=True, help="Path to skillpipe res.json")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--k-values", nargs="+", type=int, default=list(DEFAULT_K_VALUES))
    args = parser.parse_args()

    records = _load_json(args.res)
    if not isinstance(records, list):
        raise ValueError(f"{args.res} must contain a JSON list")
    summary = evaluate_topk_recall(records, out_dir=args.out_dir, k_values=args.k_values)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
