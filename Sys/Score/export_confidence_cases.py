from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.Score.credence_artifact_utils import (
    FEATURE_COLUMNS,
    LABEL_ONLY_COLUMNS,
    case_id_from_dir,
    dedupe,
    diagnosability_from_row_parts,
    ensure_parent,
    extract_llm_ips,
    hit_at,
    load_json,
    raw_confidence_from_gate,
    safe_float,
    write_json,
    write_jsonl,
)


def _llm_response_index(records: List[Dict[str, Any]]) -> Dict[str, str]:
    indexed = {}
    for idx, record in enumerate(records):
        case_id = case_id_from_dir(record.get("dir", ""), f"case_{idx:05d}")
        response = record.get("response", "")
        if isinstance(response, str):
            indexed[case_id] = response
    return indexed


def _row_from_result(
    record: Dict[str, Any],
    index: int,
    data_version: str,
    llm_response_by_case: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    case_dir = record.get("dir", "")
    case_id = case_id_from_dir(case_dir, f"case_{index:05d}")
    skill_ips = dedupe(record.get("skill_ips", []))
    gt_ips = dedupe(record.get("gt_ips", []))
    pipeline_response = record.get("response", "") if isinstance(record.get("response", ""), str) else ""
    if llm_response_by_case is not None and case_id in llm_response_by_case:
        llm_response = llm_response_by_case[case_id]
        llm_response_source = "always_llm_res"
    else:
        llm_response = pipeline_response
        llm_response_source = "primary_res"
    llm_ips = dedupe(extract_llm_ips(llm_response))
    routed_ips = dedupe(extract_llm_ips(pipeline_response))
    gate = record.get("confidence_gate", {})
    if not isinstance(gate, dict):
        gate = {"decision": "unknown", "reason": "missing_confidence_gate"}

    methods = gate.get("methods", {}) if isinstance(gate, dict) else {}
    combined = methods.get("combined", {}) if isinstance(methods, dict) else {}
    topo = methods.get("topo", {}) if isinstance(methods, dict) else {}
    temporal = methods.get("temporal", {}) if isinstance(methods, dict) else {}
    agreement = gate.get("agreement", {}) if isinstance(gate, dict) else {}

    deterministic_hit_top1 = hit_at(skill_ips, gt_ips, 1)
    deterministic_hit_top3 = hit_at(skill_ips, gt_ips, 3)
    deterministic_hit_top5 = hit_at(skill_ips, gt_ips, 5)
    llm_hit_top1 = hit_at(llm_ips, gt_ips, 1)
    llm_hit_top3 = hit_at(llm_ips, gt_ips, 3)
    llm_hit_top5 = hit_at(llm_ips, gt_ips, 5)

    raw_confidence = raw_confidence_from_gate(gate, skill_ips, llm_response)
    diagnosability = diagnosability_from_row_parts(skill_ips, gate, llm_response)

    missing_fields = []
    if not skill_ips:
        missing_fields.append("skill_ips")
    if not llm_response:
        missing_fields.append("response")
    if not gate:
        missing_fields.append("confidence_gate")

    return {
        "case_id": case_id,
        "case_dir": case_dir,
        "data_version": data_version,
        "extraction_status": "ok" if not missing_fields else "partial",
        "missing_fields": missing_fields,
        "label_available": bool(gt_ips),
        "gt_ips": gt_ips,
        "label_source": "res_json_gt_ips" if gt_ips else None,
        "skill_ips": skill_ips,
        "llm_ips": llm_ips,
        "final_ips": routed_ips or skill_ips,
        "llm_response_source": llm_response_source,
        "confidence_gate_decision": gate.get("decision", "unknown"),
        "confidence_gate_reason": gate.get("reason", "unknown"),
        "raw_confidence_score": raw_confidence,
        "combined_margin": round(safe_float(combined.get("margin")), 6),
        "combined_top_score": round(safe_float(combined.get("top_score")), 6),
        "topo_margin": round(safe_float(topo.get("margin")), 6),
        "temporal_margin": round(safe_float(temporal.get("margin")), 6),
        "top1_votes_for_combined": int(safe_float(agreement.get("top1_votes_for_combined"))),
        "n_skill_ips": len(skill_ips),
        "diagnosability_score": diagnosability,
        "llm_output_available": bool(llm_response),
        "deterministic_hit_top1": deterministic_hit_top1,
        "deterministic_hit_top3": deterministic_hit_top3,
        "deterministic_hit_top5": deterministic_hit_top5,
        "llm_hit_top1": llm_hit_top1,
        "llm_hit_top3": llm_hit_top3,
        "llm_hit_top5": llm_hit_top5,
        "final_hit_top1": hit_at(routed_ips or skill_ips, gt_ips, 1),
    }


def export_confidence_cases(
    *,
    res_path: str,
    llm_res_path: Optional[str] = None,
    out_path: str,
    summary_path: str,
    manifest_path: str,
    data_version: str,
) -> Dict[str, Any]:
    records = load_json(res_path)
    if not isinstance(records, list):
        raise ValueError(f"{res_path} must contain a JSON list")

    llm_response_by_case = None
    if llm_res_path:
        llm_records = load_json(llm_res_path)
        if not isinstance(llm_records, list):
            raise ValueError(f"{llm_res_path} must contain a JSON list")
        llm_response_by_case = _llm_response_index(llm_records)

    rows = [
        _row_from_result(record, idx, data_version, llm_response_by_case)
        for idx, record in enumerate(records)
    ]
    seen = set()
    duplicates = []
    for row in rows:
        cid = row["case_id"]
        if cid in seen:
            duplicates.append(cid)
        seen.add(cid)
    if duplicates:
        raise ValueError(f"duplicate case_id values: {duplicates[:5]}")

    ensure_parent(out_path)
    write_jsonl(out_path, rows)

    summary = {
        "source_res_path": res_path,
        "llm_res_path": llm_res_path,
        "output_path": out_path,
        "total_rows": len(rows),
        "labeled_rows": sum(1 for row in rows if row["label_available"]),
        "partial_rows": sum(1 for row in rows if row["extraction_status"] != "ok"),
        "missing_field_counts": {},
        "label_sources": {},
    }
    for row in rows:
        for field in row["missing_fields"]:
            summary["missing_field_counts"][field] = summary["missing_field_counts"].get(field, 0) + 1
        source = row.get("label_source") or "none"
        summary["label_sources"][source] = summary["label_sources"].get(source, 0) + 1
    write_json(summary_path, summary)

    manifest = {
        "run_id": os.path.basename(os.path.dirname(os.path.abspath(out_path))) or "credence",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_version": data_version,
        "case_count": len(rows),
        "label_count": summary["labeled_rows"],
        "feature_columns": FEATURE_COLUMNS,
        "label_only_columns": LABEL_ONLY_COLUMNS,
        "calibration_method": "target_only_threshold_frontier",
        "split_seed": None,
        "output_paths": {
            "confidence_cases": out_path,
            "confidence_extraction_summary": summary_path,
            "confidence_manifest": manifest_path,
            "llm_res": llm_res_path,
        },
    }
    if set(FEATURE_COLUMNS) & set(LABEL_ONLY_COLUMNS):
        raise ValueError("feature columns overlap label-only columns")
    write_json(manifest_path, manifest)
    return {"rows": rows, "summary": summary, "manifest": manifest}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export CREDENCE per-case confidence rows from res.json.")
    parser.add_argument("--res", required=True, help="Path to inference res.json")
    parser.add_argument("--llm-res", default=None, help="Optional always-LLM res.json used for LLM rescue/harm columns")
    parser.add_argument("--out", required=True, help="Output confidence_cases.jsonl")
    parser.add_argument("--summary", default=None, help="Output confidence_extraction_summary.json")
    parser.add_argument("--manifest", default=None, help="Output confidence_manifest.json")
    parser.add_argument("--data-version", default="unknown", help="Dataset/run version string")
    args = parser.parse_args()

    out_dir = os.path.dirname(args.out)
    summary = args.summary or os.path.join(out_dir, "confidence_extraction_summary.json")
    manifest = args.manifest or os.path.join(out_dir, "confidence_manifest.json")
    result = export_confidence_cases(
        res_path=args.res,
        llm_res_path=args.llm_res,
        out_path=args.out,
        summary_path=summary,
        manifest_path=manifest,
        data_version=args.data_version,
    )
    print(f"exported {len(result['rows'])} cases -> {args.out}")


if __name__ == "__main__":
    main()
