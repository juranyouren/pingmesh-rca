#!/usr/bin/env python3
# 用法：
#
#   # 只预览解析结果和变化数量，不修改现有文件
#   python scripts/reparse_evidence_tables.py \
#     --evidence-root data/evidence_Table
#
#   # 使用已有 raw_response 原地更新 summary 和 evidence_table
#   python scripts/reparse_evidence_tables.py \
#     --evidence-root data/evidence_Table \
#     --apply
#
# 该脚本不加载或调用任何模型，small_model_outputs.jsonl 中的 prompt 和
# raw_response 保持不变，只更新派生的 summary、parse_mode 和 parser_version。

"""Reparse cached small-model outputs and refresh evidence-table summaries."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_evidence_tables import SUMMARY_PARSER_VERSION, parse_summary


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            rows.append(value)
    return rows


def _atomic_write_json(data: Any, path: Path) -> None:
    temp_path = path.with_name(path.name + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def _atomic_write_jsonl(rows: Iterable[Dict[str, Any]], path: Path) -> None:
    temp_path = path.with_name(path.name + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temp_path, path)


def _increment(counter: Dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def reparse_case(case_dir: Path, *, apply: bool) -> Dict[str, Any]:
    outputs_path = case_dir / "small_model_outputs.jsonl"
    table_path = case_dir / "evidence_table.json"
    if not outputs_path.exists() or not table_path.exists():
        return {
            "case_id": case_dir.name,
            "status": "skipped_missing_files",
            "outputs_path": str(outputs_path),
            "table_path": str(table_path),
        }

    records = _read_jsonl(outputs_path)
    parse_mode_counts: Dict[str, int] = {}
    changed_records = 0
    empty_summaries = 0
    by_task: Dict[str, Dict[str, Any]] = {}
    by_ip: Dict[str, Dict[str, Any]] = {}

    for record in records:
        new_summary, parse_mode = parse_summary(str(record.get("raw_response", "")))
        if record.get("summary") != new_summary or record.get("parse_mode") != parse_mode:
            changed_records += 1
        if not new_summary:
            empty_summaries += 1
        record["summary"] = new_summary
        record["parse_mode"] = parse_mode
        record["parser_version"] = SUMMARY_PARSER_VERSION
        _increment(parse_mode_counts, parse_mode)
        if record.get("task_id"):
            by_task[str(record["task_id"])] = record
        if record.get("device_ip"):
            by_ip[str(record["device_ip"])] = record

    table = _load_json(table_path)
    table_rows = table.get("rows", []) if isinstance(table, dict) else []
    changed_table_rows = 0
    unmatched_table_rows: List[str] = []
    for row in table_rows:
        if not isinstance(row, dict):
            continue
        provenance = row.get("provenance") or {}
        task_id = provenance.get("summary_task_id")
        ip = row.get("candidate_ip")
        record = by_task.get(str(task_id)) if task_id else None
        if record is None and ip:
            record = by_ip.get(str(ip))
        if record is None:
            unmatched_table_rows.append(str(ip or task_id or "unknown"))
            continue
        summary_context = row.setdefault("summary_context", {})
        before = (
            row.get("semantic_summary"),
            summary_context.get("parse_mode"),
            summary_context.get("parser_version"),
        )
        row["semantic_summary"] = record["summary"]
        summary_context["parse_mode"] = record["parse_mode"]
        summary_context["parser_version"] = SUMMARY_PARSER_VERSION
        after = (
            row.get("semantic_summary"),
            summary_context.get("parse_mode"),
            summary_context.get("parser_version"),
        )
        if before != after:
            changed_table_rows += 1

    if isinstance(table, dict):
        table["summary_parser_version"] = SUMMARY_PARSER_VERSION
    if apply:
        _atomic_write_jsonl(records, outputs_path)
        _atomic_write_json(table, table_path)

    return {
        "case_id": table.get("case_id", case_dir.name) if isinstance(table, dict) else case_dir.name,
        "status": "updated" if apply else "preview",
        "record_count": len(records),
        "changed_records": changed_records,
        "changed_table_rows": changed_table_rows,
        "empty_summaries": empty_summaries,
        "unmatched_table_rows": unmatched_table_rows,
        "parse_mode_counts": parse_mode_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reparse existing small-model raw outputs without model inference."
    )
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="atomically update small_model_outputs.jsonl and evidence_table.json",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="report path; defaults to <evidence-root>/reparse_report.json",
    )
    args = parser.parse_args()

    evidence_root = Path(args.evidence_root).resolve()
    cases_root = evidence_root / "cases"
    if not cases_root.exists():
        raise SystemExit(f"cases directory does not exist: {cases_root}")

    started = time.perf_counter()
    cases = [
        reparse_case(case_dir, apply=args.apply)
        for case_dir in sorted(cases_root.iterdir())
        if case_dir.is_dir()
    ]
    totals = {
        "case_count": len(cases),
        "record_count": sum(int(item.get("record_count", 0)) for item in cases),
        "changed_records": sum(int(item.get("changed_records", 0)) for item in cases),
        "changed_table_rows": sum(int(item.get("changed_table_rows", 0)) for item in cases),
        "empty_summaries": sum(int(item.get("empty_summaries", 0)) for item in cases),
        "unmatched_table_rows": sum(
            len(item.get("unmatched_table_rows", [])) for item in cases
        ),
    }
    parse_mode_counts: Dict[str, int] = {}
    for case in cases:
        for mode, count in (case.get("parse_mode_counts") or {}).items():
            parse_mode_counts[mode] = parse_mode_counts.get(mode, 0) + int(count)
    totals["parse_mode_counts"] = parse_mode_counts

    report = {
        "parser_version": SUMMARY_PARSER_VERSION,
        "mode": "apply" if args.apply else "preview",
        "evidence_root": str(evidence_root),
        "elapsed_seconds": time.perf_counter() - started,
        "totals": totals,
        "cases": cases,
    }
    report_path = (
        Path(args.report).resolve()
        if args.report
        else evidence_root / "reparse_report.json"
    )
    _atomic_write_json(report, report_path)

    if args.apply:
        manifest_path = evidence_root / "manifest.json"
        if manifest_path.exists():
            manifest = _load_json(manifest_path)
            if isinstance(manifest, dict):
                manifest["summary_parser_version"] = SUMMARY_PARSER_VERSION
                manifest["reparsed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                _atomic_write_json(manifest, manifest_path)

    print(
        f"[reparse] mode={report['mode']} cases={totals['case_count']} "
        f"records={totals['record_count']} changed={totals['changed_records']} "
        f"empty={totals['empty_summaries']} -> {report_path}"
    )


if __name__ == "__main__":
    main()
