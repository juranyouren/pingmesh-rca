from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys_v1.Score.Score_N import Scorer
from Sys_v1.Score.score_utils import (
    case_id_from_dir,
    dedupe,
    hit_at,
    load_json,
    write_json,
    write_jsonl,
)


_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _parse_response_payload(response: Any) -> Dict[str, Any]:
    if isinstance(response, dict):
        return response
    if not isinstance(response, str):
        return {}
    blocks = _JSON_BLOCK.findall(response)
    candidates = list(reversed(blocks)) if blocks else [response]
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _skill_details(record: Dict[str, Any]) -> Dict[str, Any]:
    details = record.get("skill_details")
    if isinstance(details, dict):
        return details
    payload = _parse_response_payload(record.get("response"))
    details = payload.get("skill_details", {})
    return details if isinstance(details, dict) else {}


def _normalize_top_entries(value: Any) -> List[Tuple[str, float]]:
    if not isinstance(value, list):
        return []
    out: List[Tuple[str, float]] = []
    for item in value:
        ip: Optional[str] = None
        score = 0.0
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            ip = item[0] if isinstance(item[0], str) else None
            try:
                score = float(item[1])
            except (TypeError, ValueError):
                score = 0.0
        elif isinstance(item, dict):
            raw_ip = item.get("ip")
            ip = raw_ip if isinstance(raw_ip, str) else None
            for key in ("combined_score", "pr_score", "score"):
                if key in item:
                    try:
                        score = float(item[key])
                    except (TypeError, ValueError):
                        score = 0.0
                    break
        if ip:
            out.append((ip, score))
    return out


def _method_entries(details: Dict[str, Any], method_id: str) -> List[Tuple[str, float]]:
    method = details.get(method_id, {})
    if not isinstance(method, dict):
        return []
    for key in ("topk", "top5", "top3"):
        entries = _normalize_top_entries(method.get(key, []))
        if entries:
            return sorted(entries, key=lambda item: (-item[1], item[0]))
    return []


def _method_summary(entries: Sequence[Tuple[str, float]]) -> Dict[str, Any]:
    if not entries:
        return {"top_ip": None, "top_score": 0.0, "runner_up_score": 0.0, "margin": 0.0}
    top_ip, top_score = entries[0]
    runner_up_score = entries[1][1] if len(entries) > 1 else 0.0
    return {
        "top_ip": top_ip,
        "top_score": round(top_score, 6),
        "runner_up_score": round(runner_up_score, 6),
        "margin": round(top_score - runner_up_score, 6),
    }


def _best_rank(pred_ips: Sequence[str], gt_ips: Sequence[str]) -> Optional[int]:
    best: Optional[int] = None
    for gt in gt_ips:
        if gt in pred_ips:
            rank = pred_ips.index(gt) + 1
            if best is None or rank < best:
                best = rank
    return best


def _rank_in_entries(entries: Sequence[Tuple[str, float]], gt_ips: Sequence[str]) -> Optional[int]:
    return _best_rank([ip for ip, _score in entries], gt_ips)


def _hit_in_entries(entries: Sequence[Tuple[str, float]], gt_ips: Sequence[str], k: int) -> bool | None:
    return hit_at([ip for ip, _score in entries], gt_ips, k)


def _method_failure_pattern(
    *,
    gt_ips: Sequence[str],
    topo_entries: Sequence[Tuple[str, float]],
    temporal_entries: Sequence[Tuple[str, float]],
) -> str:
    if not gt_ips:
        return "unlabeled"

    topo_has = bool(topo_entries)
    temporal_has = bool(temporal_entries)
    topo_top1 = _hit_in_entries(topo_entries, gt_ips, 1)
    temporal_top1 = _hit_in_entries(temporal_entries, gt_ips, 1)

    topo_label = "missing" if not topo_has else ("right" if topo_top1 else "wrong")
    temporal_label = "missing" if not temporal_has else ("right" if temporal_top1 else "wrong")
    return f"topo_{topo_label}_temporal_{temporal_label}"


def _gt_ips_from_record(record: Dict[str, Any]) -> List[str]:
    gt_ips = dedupe(record.get("gt_ips", []))
    if gt_ips:
        return gt_ips
    case_dir = record.get("dir", "")
    if not case_dir:
        return []
    try:
        return Scorer._get_groundtruth(case_dir).ips
    except Exception:
        return []


def _failure_type(gt_ips: Sequence[str], top1_hit: Any, top3_hit: Any, top5_hit: Any, skill_ips: Sequence[str]) -> str:
    if not gt_ips:
        return "unlabeled"
    if top1_hit:
        return "top1_hit"
    if top3_hit:
        return "top1_miss_gt_in_top3"
    if top5_hit:
        return "top1_miss_gt_in_top5"
    if skill_ips:
        return "miss_top5"
    return "no_prediction"


def _suggest_action(failure_type: str, method_disagreement: bool, low_margin: bool) -> str:
    if failure_type == "unlabeled":
        return "unlabeled"
    if failure_type in ("miss_top5", "no_prediction"):
        return "low_diagnosability_candidate"
    if failure_type.startswith("top1_miss"):
        return "defer_to_llm_candidate"
    if method_disagreement or low_margin:
        return "defer_audit_candidate"
    return "bypass_candidate"


def _case_row(record: Dict[str, Any], index: int, margin_threshold: float) -> Dict[str, Any]:
    case_dir = record.get("dir", "")
    case_id = case_id_from_dir(case_dir, f"case_{index:05d}")
    skill_ips = dedupe(record.get("skill_ips", []))
    gt_ips = _gt_ips_from_record(record)

    details = _skill_details(record)
    topo_entries = _method_entries(details, "1")
    temporal_entries = _method_entries(details, "2")
    topo = _method_summary(topo_entries)
    temporal = _method_summary(temporal_entries)
    topo_ips = [ip for ip, _score in topo_entries]
    temporal_ips = [ip for ip, _score in temporal_entries]
    topo_gt_rank = _rank_in_entries(topo_entries, gt_ips)
    temporal_gt_rank = _rank_in_entries(temporal_entries, gt_ips)

    combined_top1 = skill_ips[0] if skill_ips else None
    method_top_ips = {
        "combined": combined_top1,
        "topo": topo["top_ip"],
        "temporal": temporal["top_ip"],
    }
    present_method_tops = [ip for ip in method_top_ips.values() if ip]
    top1_votes_for_combined = sum(1 for ip in present_method_tops if ip == combined_top1) if combined_top1 else 0
    method_disagreement = len(set(present_method_tops)) > 1

    margins = [info["margin"] for info in (topo, temporal) if info["top_ip"]]
    min_method_margin = min(margins) if margins else 0.0
    low_margin = min_method_margin < margin_threshold

    top1_hit = hit_at(skill_ips, gt_ips, 1)
    top3_hit = hit_at(skill_ips, gt_ips, 3)
    top5_hit = hit_at(skill_ips, gt_ips, 5)
    best_rank = _best_rank(skill_ips, gt_ips)
    ftype = _failure_type(gt_ips, top1_hit, top3_hit, top5_hit, skill_ips)

    return {
        "case_id": case_id,
        "case_dir": case_dir,
        "label_available": bool(gt_ips),
        "gt_ips": gt_ips,
        "skill_ips": skill_ips,
        "combined_top1": combined_top1,
        "combined_top2": skill_ips[1] if len(skill_ips) > 1 else None,
        "combined_top3": skill_ips[2] if len(skill_ips) > 2 else None,
        "topo_top1": topo["top_ip"],
        "topo_ips": topo_ips,
        "topo_rank_scope": len(topo_ips),
        "topo_margin": topo["margin"],
        "topo_gt_rank": topo_gt_rank,
        "topo_hit_top1": _hit_in_entries(topo_entries, gt_ips, 1),
        "topo_hit_top3": _hit_in_entries(topo_entries, gt_ips, 3),
        "temporal_top1": temporal["top_ip"],
        "temporal_ips": temporal_ips,
        "temporal_rank_scope": len(temporal_ips),
        "temporal_margin": temporal["margin"],
        "temporal_gt_rank": temporal_gt_rank,
        "temporal_hit_top1": _hit_in_entries(temporal_entries, gt_ips, 1),
        "temporal_hit_top3": _hit_in_entries(temporal_entries, gt_ips, 3),
        "min_method_margin": round(min_method_margin, 6),
        "top1_votes_for_combined": top1_votes_for_combined,
        "method_disagreement": method_disagreement,
        "low_margin": low_margin,
        "gt_rank_in_skill": best_rank,
        "gt_rank_in_topo_top3": _best_rank(topo_ips[:3], gt_ips),
        "gt_rank_in_temporal_top3": _best_rank(temporal_ips[:3], gt_ips),
        "top1_hit": top1_hit,
        "top3_hit": top3_hit,
        "top5_hit": top5_hit,
        "best_rank": best_rank,
        "failure_type": ftype,
        "method_failure_pattern": _method_failure_pattern(
            gt_ips=gt_ips,
            topo_entries=topo_entries,
            temporal_entries=temporal_entries,
        ),
        "suggested_gate_action": _suggest_action(ftype, method_disagreement, low_margin),
    }


def analyze_skillpipe_records(
    records: Sequence[Dict[str, Any]],
    *,
    margin_threshold: float = 0.05,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows = [_case_row(record, idx, margin_threshold) for idx, record in enumerate(records)]
    labeled = [row for row in rows if row["label_available"]]
    failures = [row for row in labeled if row["top1_hit"] is False]

    failure_feature_counts = Counter()
    for row in failures:
        for key in ("method_disagreement", "low_margin"):
            if row.get(key):
                failure_feature_counts[key] += 1
        if row.get("gt_rank_in_topo_top3"):
            failure_feature_counts["gt_in_topo_top3"] += 1
        if row.get("gt_rank_in_temporal_top3"):
            failure_feature_counts["gt_in_temporal_top3"] += 1

    summary = {
        "total_cases": len(rows),
        "labeled_cases": len(labeled),
        "top1_hits": sum(1 for row in labeled if row["top1_hit"] is True),
        "top1_failures": len(failures),
        "top3_hits": sum(1 for row in labeled if row["top3_hit"] is True),
        "top5_hits": sum(1 for row in labeled if row["top5_hit"] is True),
        "margin_threshold": margin_threshold,
        "failure_type_counts": dict(Counter(row["failure_type"] for row in rows)),
        "method_failure_pattern_counts": dict(Counter(row["method_failure_pattern"] for row in rows)),
        "failure_feature_counts": dict(failure_feature_counts),
        "suggested_gate_action_counts": dict(Counter(row["suggested_gate_action"] for row in rows)),
    }
    summary["top1_accuracy"] = round(summary["top1_hits"] / len(labeled), 6) if labeled else None
    summary["top3_accuracy"] = round(summary["top3_hits"] / len(labeled), 6) if labeled else None
    summary["top5_accuracy"] = round(summary["top5_hits"] / len(labeled), 6) if labeled else None
    return rows, summary


def _write_csv(path: str, rows: Iterable[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _report_text(summary: Dict[str, Any]) -> str:
    failure_counts = summary.get("failure_type_counts", {})
    action_counts = summary.get("suggested_gate_action_counts", {})
    pattern_counts = summary.get("method_failure_pattern_counts", {})
    feature_counts = summary.get("failure_feature_counts", {})
    return "\n".join(
        [
            "# Skillpipe failure analysis",
            "",
            "The previous online confidence gate is disabled. Use this report to design the next gate from observed skillpipe failure features.",
            "",
            "## Overall",
            "",
            f"- Total cases: {summary.get('total_cases')}",
            f"- Labeled cases: {summary.get('labeled_cases')}",
            f"- Top-1 accuracy: {summary.get('top1_accuracy')}",
            f"- Top-3 accuracy: {summary.get('top3_accuracy')}",
            f"- Top-5 accuracy: {summary.get('top5_accuracy')}",
            "",
            "## Failure Types",
            "",
            *[f"- {key}: {value}" for key, value in sorted(failure_counts.items())],
            "",
            "## Failure Features",
            "",
            *[f"- {key}: {value}" for key, value in sorted(feature_counts.items())],
            "",
            "## Method Failure Patterns",
            "",
            *[f"- {key}: {value}" for key, value in sorted(pattern_counts.items())],
            "",
            "## Candidate Gate Actions",
            "",
            *[f"- {key}: {value}" for key, value in sorted(action_counts.items())],
            "",
            "## Redesign Notes",
            "",
            "- Treat top1_miss_gt_in_top3/top5 as candidates for LLM deferment analysis.",
            "- Treat miss_top5/no_prediction as low-diagnosability candidates.",
            "- Use method_disagreement and low_margin as candidate risk features; validate their precision before turning them into online rules.",
            "- Do not enable bypass until the selected rule is evaluated with risk-coverage calibration.",
            "",
        ]
    )


def write_analysis_outputs(rows: List[Dict[str, Any]], summary: Dict[str, Any], out_dir: str) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    case_features = os.path.join(out_dir, "skillpipe_case_features.jsonl")
    failures_csv = os.path.join(out_dir, "skillpipe_failures.csv")
    summary_json = os.path.join(out_dir, "skillpipe_failure_summary.json")
    report_md = os.path.join(out_dir, "gate_design_report.md")

    write_jsonl(case_features, rows)
    fields = [
        "case_id",
        "case_dir",
        "gt_ips",
        "skill_ips",
        "combined_top1",
        "topo_top1",
        "topo_ips",
        "topo_rank_scope",
        "topo_gt_rank",
        "topo_hit_top1",
        "topo_hit_top3",
        "temporal_top1",
        "temporal_ips",
        "temporal_rank_scope",
        "temporal_gt_rank",
        "temporal_hit_top1",
        "temporal_hit_top3",
        "topo_margin",
        "temporal_margin",
        "min_method_margin",
        "method_disagreement",
        "low_margin",
        "gt_rank_in_skill",
        "gt_rank_in_topo_top3",
        "gt_rank_in_temporal_top3",
        "failure_type",
        "method_failure_pattern",
        "suggested_gate_action",
    ]
    _write_csv(failures_csv, [row for row in rows if row["label_available"] and row["top1_hit"] is False], fields)
    write_json(summary_json, summary)
    with open(report_md, "w", encoding="utf-8") as f:
        f.write(_report_text(summary))

    return {
        "case_features_jsonl": case_features,
        "failures_csv": failures_csv,
        "summary_json": summary_json,
        "report_md": report_md,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze skillpipe failure features for future confidence gate design.")
    parser.add_argument("--res", required=True, help="Path to skillpipe res.json")
    parser.add_argument("--out-dir", required=True, help="Output directory for failure analysis artifacts")
    parser.add_argument("--margin-threshold", type=float, default=0.05, help="Low-margin threshold on normalized skill scores")
    args = parser.parse_args()

    records = load_json(args.res)
    if not isinstance(records, list):
        raise ValueError(f"{args.res} must contain a JSON list")
    rows, summary = analyze_skillpipe_records(records, margin_threshold=args.margin_threshold)
    outputs = write_analysis_outputs(rows, summary, args.out_dir)
    print(json.dumps({"summary": summary, "outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
