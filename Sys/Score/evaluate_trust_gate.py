from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.RootCauseAnalyze.trust_trees.router import route_with_trust_trees
from Sys.Score.Score_N import Scorer


_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_csv(path: str, rows: Iterable[Dict[str, Any]], fields: Sequence[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def _parse_payload(response: Any) -> Dict[str, Any]:
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
    payload = _parse_payload(record.get("response"))
    details = payload.get("skill_details", {})
    return details if isinstance(details, dict) else {}


def _normalize_entries(value: Any) -> List[Tuple[str, float]]:
    if not isinstance(value, list):
        return []
    out: List[Tuple[str, float]] = []
    for item in value:
        ip = None
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
    return sorted(out, key=lambda pair: (-pair[1], pair[0]))


def _detail_ips(details: Dict[str, Any], key: str) -> List[str]:
    block = details.get(key, {})
    if not isinstance(block, dict):
        return []
    for field in ("topk", "top5", "top3", "rankings"):
        entries = _normalize_entries(block.get(field, []))
        if entries:
            return [ip for ip, _score in entries]
    return []


def _tree_from_detail(details: Dict[str, Any], key: str) -> Dict[str, Any]:
    block = details.get(key, {})
    if isinstance(block, dict) and isinstance(block.get("trust_tree"), dict):
        tree = block["trust_tree"]
        state = tree.get("state")
        if state in {"strong", "weak", "uncertain"}:
            return tree
    return {"state": "uncertain", "passed": [], "failed": ["missing_trust_tree"], "evidence": {}}


def _dedupe(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    out = []
    for value in values:
        if isinstance(value, str) and value and value not in out:
            out.append(value)
    return out


def _gt_ips(record: Dict[str, Any]) -> List[str]:
    gt = _dedupe(record.get("gt_ips", []))
    if gt:
        return gt
    case_dir = record.get("dir")
    if not case_dir:
        return []
    try:
        return Scorer._get_groundtruth(case_dir).ips
    except Exception:
        return []


def _hit_at(pred_ips: Sequence[str], gt_ips: Sequence[str], k: int) -> bool | None:
    if not gt_ips:
        return None
    return any(ip in set(pred_ips[:k]) for ip in gt_ips)


def _best_rank(pred_ips: Sequence[str], gt_ips: Sequence[str]) -> int | None:
    best = None
    for gt in gt_ips:
        if gt in pred_ips:
            rank = pred_ips.index(gt) + 1
            best = rank if best is None else min(best, rank)
    return best


def _failure_bucket(pred_ips: Sequence[str], gt_ips: Sequence[str]) -> str:
    if not gt_ips:
        return "unlabeled"
    if _hit_at(pred_ips, gt_ips, 1):
        return "top1_hit"
    if _hit_at(pred_ips, gt_ips, 3):
        return "top1_miss_gt_in_top3"
    if _hit_at(pred_ips, gt_ips, 5):
        return "top1_miss_gt_in_top5"
    return "miss_top5" if pred_ips else "no_prediction"


def _case_id(path: str, index: int) -> str:
    name = os.path.basename(os.path.normpath(path or ""))
    return name or f"case_{index:05d}"


def _case_row(record: Dict[str, Any], index: int) -> Dict[str, Any]:
    details = _skill_details(record)
    combined_ips = _detail_ips(details, "combined") or _dedupe(record.get("skill_ips", []))
    topo_ips = _detail_ips(details, "1")
    temporal_ips = _detail_ips(details, "2")
    gate = route_with_trust_trees(
        combined_ips=combined_ips,
        topo_ips=topo_ips,
        temporal_ips=temporal_ips,
        topo_tree=_tree_from_detail(details, "1"),
        temporal_tree=_tree_from_detail(details, "2"),
    )
    gt_ips = _gt_ips(record)
    pred_ips = gate.get("recommended_ips", []) if gate.get("decision") != "operator_review" else []
    original_skill_ips = _dedupe(record.get("skill_ips", [])) or combined_ips

    return {
        "case_id": _case_id(record.get("dir", ""), index),
        "case_dir": record.get("dir", ""),
        "gt_ips": gt_ips,
        "decision": gate["decision"],
        "route": gate["route"],
        "reason": gate["reason"],
        "recommended_ips": gate.get("recommended_ips", []),
        "evaluated_ips": pred_ips,
        "topo_state": gate["trust_trees"]["topo"].get("state"),
        "temporal_state": gate["trust_trees"]["temporal"].get("state"),
        "rank_near": gate["agreement"]["rank_near"],
        "top3_overlap": gate["agreement"]["top3_overlap"],
        "top1_hit": _hit_at(pred_ips, gt_ips, 1),
        "top3_hit": _hit_at(pred_ips, gt_ips, 3),
        "top5_hit": _hit_at(pred_ips, gt_ips, 5),
        "best_rank": _best_rank(pred_ips, gt_ips),
        "skill_failure_bucket": _failure_bucket(original_skill_ips, gt_ips),
        "gate": gate,
    }


def _route_summary(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_route: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_route[row["route"]].append(row)

    out = []
    for route, items in sorted(by_route.items()):
        labeled = [row for row in items if row["top1_hit"] is not None]
        n = len(labeled)
        out.append({
            "route": route,
            "n": len(items),
            "labeled_n": n,
            "coverage": round(len(items) / len(rows), 6) if rows else 0.0,
            "top1": round(sum(1 for row in labeled if row["top1_hit"]) / n, 6) if n else None,
            "top3": round(sum(1 for row in labeled if row["top3_hit"]) / n, 6) if n else None,
            "top5": round(sum(1 for row in labeled if row["top5_hit"]) / n, 6) if n else None,
        })
    return out


def evaluate_trust_gate(records: Sequence[Dict[str, Any]], *, out_dir: str) -> Dict[str, Any]:
    rows = [_case_row(record, idx) for idx, record in enumerate(records)]
    route_rows = _route_summary(rows)
    route_counts = dict(Counter(row["route"] for row in rows))

    summary = {
        "total_cases": len(rows),
        "route_counts": route_counts,
        "route_metrics": route_rows,
        "invoke_llm_top1_miss_gt_in_top3_cases": sum(
            1 for row in rows if row["route"] == "llm" and row["skill_failure_bucket"] == "top1_miss_gt_in_top3"
        ),
        "operator_review_miss_top5_cases": sum(
            1 for row in rows if row["route"] == "operator" and row["skill_failure_bucket"] in {"miss_top5", "no_prediction"}
        ),
    }

    os.makedirs(out_dir, exist_ok=True)
    _write_jsonl(os.path.join(out_dir, "trust_gate_cases.jsonl"), rows)
    _write_json(os.path.join(out_dir, "trust_gate_summary.json"), summary)
    _write_csv(
        os.path.join(out_dir, "trust_gate_by_route.csv"),
        route_rows,
        ["route", "n", "labeled_n", "coverage", "top1", "top3", "top5"],
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate trust-tree gate routing on skillpipe res.json.")
    parser.add_argument("--res", required=True, help="Path to skillpipe res.json")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    args = parser.parse_args()

    records = _load_json(args.res)
    if not isinstance(records, list):
        raise ValueError(f"{args.res} must contain a JSON list")
    summary = evaluate_trust_gate(records, out_dir=args.out_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
