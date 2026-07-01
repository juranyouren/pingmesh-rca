"""
Gate Selection Evaluator
========================
对 SkilledAnalyzer (带 --confidence-gate) 产出的 res.json 中所有 invoke_llm 的 case,
对比 topo / temporal / LLM 三个候选结果, 判断 gate 选中的 LLM 结果是否是三者中最优的。

用法:
    python Sys/Score/evaluate_gate_selection.py --res <res.json> --out-dir <dir>
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.RootCauseAnalyze.trust_trees.common import unique_ips
from Sys.Score.Score_N import GroundTruth, MetricsEvaluator, Prediction, ResponseParser, Scorer
from Sys.Score.score_utils import case_id_from_dir, dedupe, load_json, write_json, write_jsonl

# ── regex ────────────────────────────────────────────────────────────
_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)

# ── helpers ──────────────────────────────────────────────────────────


def _extract_skill_ret_from_prompt(prompt: str) -> Optional[Dict[str, Any]]:
    """从 SkilledAnalyzer 的 prompt 中提取 skill_ret JSON 字典.

    遍历所有 ```json ... ``` 块, 返回同时含 "topo" 和 "temporal" key 的那个.
    """
    if not isinstance(prompt, str) or not prompt:
        return None

    candidates = _JSON_BLOCK.findall(prompt)
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and "topo" in data and "temporal" in data:
            return data
    return None


def _extract_method_ips(skill_ret: Dict[str, Any], method: str) -> List[str]:
    """从 skill_ret 中提取指定方法的排序 IP 列表.

    method="topo":   按 pr_score 降序
    method="temporal": 按 score 降序
    """
    if method not in ("topo", "temporal"):
        return []

    block = skill_ret.get(method, {})
    if not isinstance(block, dict):
        return []

    rankings = block.get("rankings", [])
    if not isinstance(rankings, list):
        return []

    score_key = "pr_score" if method == "topo" else "score"
    scored: List[Tuple[str, float]] = []
    for item in rankings:
        if not isinstance(item, dict):
            continue
        ip = item.get("ip")
        if not isinstance(ip, str) or not ip:
            continue
        try:
            score_val = float(item.get(score_key, item.get("score", 0.0)))
        except (TypeError, ValueError):
            score_val = 0.0
        scored.append((ip, score_val))

    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return unique_ips(ip for ip, _score in scored)


def _extract_llm_ips(response: str) -> List[str]:
    """从 LLM response 解析 IP 列表."""
    parser = ResponseParser()
    pred = parser.parse(response or "")
    return pred.ips


def _compute_metrics(gt_ips: List[str], pred_ips: List[str]) -> Dict[str, Any]:
    """对单个候选计算 Top-1~5 hit 和 best_rank."""
    evaluator = MetricsEvaluator()
    gt = GroundTruth(ips=gt_ips)
    pred = Prediction(ips=pred_ips)
    result = evaluator.evaluate(gt, pred)
    return {
        "top1_hit": bool(result.get("top1_hit")),
        "top2_hit": bool(result.get("top2_hit")),
        "top3_hit": bool(result.get("top3_hit")),
        "top4_hit": bool(result.get("top4_hit")),
        "top5_hit": bool(result.get("top5_hit")),
        "best_rank": result.get("best_rank"),  # int | None
        "is_failed": bool(result.get("is_failed")),
        "pred_ips": result.get("pred_ips", pred_ips),
    }


def _method_better(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Return True if candidate a is strictly better than candidate b."""
    # Top-1 hit wins
    if a["top1_hit"] and not b["top1_hit"]:
        return True
    if b["top1_hit"] and not a["top1_hit"]:
        return False

    # Both hit top-1 or both miss top-1: compare best_rank
    ar = a["best_rank"]
    br = b["best_rank"]
    if ar is not None and br is not None:
        if ar < br:
            return True
        if br < ar:
            return False
    elif ar is not None:
        return True
    elif br is not None:
        return False

    # Same best_rank or both None: compare top3
    if a["top3_hit"] and not b["top3_hit"]:
        return True
    if b["top3_hit"] and not a["top3_hit"]:
        return False

    # Compare top5
    if a["top5_hit"] and not b["top5_hit"]:
        return True
    if b["top5_hit"] and not a["top5_hit"]:
        return False

    return False  # tied


def _determine_best(
    topo_m: Dict[str, Any],
    temp_m: Dict[str, Any],
    llm_m: Dict[str, Any],
) -> str:
    """判定三个候选中哪个最优. 返回 "topo" | "temporal" | "llm" | "tie"."""
    candidates = [
        ("topo", topo_m),
        ("temporal", temp_m),
        ("llm", llm_m),
    ]

    # 找出所有 hits 中 best_rank 最小的
    best_rank = min(
        (m["best_rank"] for _, m in candidates if m["best_rank"] is not None),
        default=None,
    )

    if best_rank is None:
        # 三者全 miss
        return "tie"

    # 在 best_rank 的候选中比较
    at_best = [(name, m) for name, m in candidates if m["best_rank"] == best_rank]

    if len(at_best) == 1:
        return at_best[0][0]

    # 多个候选并列 best_rank, 用 top1 > top3 > top5 二次裁决
    for key in ("top1_hit", "top3_hit", "top5_hit"):
        hits = [name for name, m in at_best if m[key]]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            # 进一步缩小范围到 hit 的候选
            at_best = [(name, m) for name, m in at_best if m[key]]

    # 完全无法区分
    return "tie"


def _count_bool(items: Iterable[bool]) -> int:
    return sum(1 for v in items if v)


# ── core ─────────────────────────────────────────────────────────────


def evaluate_gate_selection(res_path: str, out_dir: str) -> Dict[str, Any]:
    """主测评逻辑."""
    records = load_json(res_path)
    if not isinstance(records, list):
        raise ValueError(f"{res_path} must contain a JSON list")

    # ── 过滤 invoke_llm ──────────────────────────────────────────────
    invoke_llm_records = []
    skipped_no_gate = 0
    skipped_not_invoke = 0
    for r in records:
        gate = r.get("confidence_gate")
        if not isinstance(gate, dict):
            skipped_no_gate += 1
            continue
        if gate.get("decision") != "invoke_llm":
            skipped_not_invoke += 1
            continue
        invoke_llm_records.append(r)

    # ── 逐 case 测评 ────────────────────────────────────────────────
    case_rows: List[Dict[str, Any]] = []
    skipped_no_gt = 0
    skipped_skill_ret_error = 0

    for idx, record in enumerate(invoke_llm_records):
        case_dir = record.get("dir", "")
        case_id = case_id_from_dir(case_dir, f"case_{idx:05d}")
        gate = record.get("confidence_gate", {})

        # Ground truth
        try:
            gt = Scorer._get_groundtruth(case_dir)
        except Exception:
            gt = GroundTruth(ips=[])
        gt_ips = gt.ips
        if not gt_ips:
            skipped_no_gt += 1
            continue

        # 提取 skill_ret
        prompt = record.get("prompt", "")
        skill_ret = _extract_skill_ret_from_prompt(prompt)
        if skill_ret is None:
            skipped_skill_ret_error += 1
            continue

        # 提取三个候选的 IPs
        topo_ips = _extract_method_ips(skill_ret, "topo")
        temporal_ips = _extract_method_ips(skill_ret, "temporal")
        llm_ips = _extract_llm_ips(record.get("response", ""))

        # 计算三个候选的 metrics
        topo_m = _compute_metrics(gt_ips, topo_ips)
        temp_m = _compute_metrics(gt_ips, temporal_ips)
        llm_m = _compute_metrics(gt_ips, llm_ips)

        # 判定最优
        best = _determine_best(topo_m, temp_m, llm_m)

        # LLM vs best 判定
        if best == "llm":
            llm_vs_best = "llm_best"
        elif best == "tie":
            # 检查 LLM 是否在并列最优中
            llm_r = llm_m["best_rank"]
            best_r = min(
                m["best_rank"] for m in [topo_m, temp_m, llm_m] if m["best_rank"] is not None
            )
            if llm_r == best_r:
                llm_vs_best = "llm_tied_for_best"
            else:
                llm_vs_best = "llm_worse"
        else:
            llm_vs_best = "llm_worse"

        row = {
            "case_id": case_id,
            "case_dir": case_dir,
            "gt_ips": gt_ips,
            "gt_source": gt.source,
            "gate_reason": gate.get("reason", "unknown"),
            "gate_route": gate.get("route", "unknown"),
            "topo_ips": topo_ips[:10],
            "temporal_ips": temporal_ips[:10],
            "llm_ips": llm_ips[:10],
            "topo_top1_hit": topo_m["top1_hit"],
            "topo_top3_hit": topo_m["top3_hit"],
            "topo_top5_hit": topo_m["top5_hit"],
            "topo_best_rank": topo_m["best_rank"],
            "temporal_top1_hit": temp_m["top1_hit"],
            "temporal_top3_hit": temp_m["top3_hit"],
            "temporal_top5_hit": temp_m["top5_hit"],
            "temporal_best_rank": temp_m["best_rank"],
            "llm_top1_hit": llm_m["top1_hit"],
            "llm_top3_hit": llm_m["top3_hit"],
            "llm_top5_hit": llm_m["top5_hit"],
            "llm_best_rank": llm_m["best_rank"],
            "best_candidate": best,
            "llm_vs_best": llm_vs_best,
        }
        case_rows.append(row)

    # ── 汇总统计 ─────────────────────────────────────────────────────
    evaluated = len(case_rows)
    llm_best = _count_bool(r["llm_vs_best"] == "llm_best" for r in case_rows)
    llm_tied = _count_bool(r["llm_vs_best"] == "llm_tied_for_best" for r in case_rows)
    llm_worse = _count_bool(r["llm_vs_best"] == "llm_worse" for r in case_rows)

    # LLM worse 时, 统计谁更好
    better_is_topo = 0
    better_is_temporal = 0
    better_is_tie_of_topo_temporal = 0
    for r in case_rows:
        if r["llm_vs_best"] != "llm_worse":
            continue
        if r["best_candidate"] == "topo":
            better_is_topo += 1
        elif r["best_candidate"] == "temporal":
            better_is_temporal += 1
        elif r["best_candidate"] == "tie":
            better_is_tie_of_topo_temporal += 1

    # 按 reason 分组
    by_reason: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "llm_best": 0, "llm_tied": 0, "llm_worse": 0,
                 "topo_top1": 0, "temporal_top1": 0, "llm_top1": 0}
    )
    for r in case_rows:
        reason = r["gate_reason"]
        by_reason[reason]["n"] += 1
        if r["llm_vs_best"] == "llm_best":
            by_reason[reason]["llm_best"] += 1
        elif r["llm_vs_best"] == "llm_tied_for_best":
            by_reason[reason]["llm_tied"] += 1
        else:
            by_reason[reason]["llm_worse"] += 1
        if r["topo_top1_hit"]:
            by_reason[reason]["topo_top1"] += 1
        if r["temporal_top1_hit"]:
            by_reason[reason]["temporal_top1"] += 1
        if r["llm_top1_hit"]:
            by_reason[reason]["llm_top1"] += 1

    # 每个方法的整体 Top-K
    def _topk_rate(rows: List[Dict[str, Any]], prefix: str) -> Dict[str, float]:
        n = len(rows)
        if n == 0:
            return {"top1": 0.0, "top3": 0.0, "top5": 0.0}
        return {
            "top1": round(sum(1 for r in rows if r[f"{prefix}_top1_hit"]) / n, 4),
            "top3": round(sum(1 for r in rows if r[f"{prefix}_top3_hit"]) / n, 4),
            "top5": round(sum(1 for r in rows if r[f"{prefix}_top5_hit"]) / n, 4),
        }

    per_method_topk = {
        "topo": _topk_rate(case_rows, "topo"),
        "temporal": _topk_rate(case_rows, "temporal"),
        "llm": _topk_rate(case_rows, "llm"),
    }

    # 按 reason 补充 win_rate 和 topk
    by_reason_out = {}
    for reason, stats in sorted(by_reason.items()):
        n = stats["n"]
        entry = dict(stats)
        entry["llm_win_rate"] = round((stats["llm_best"] + stats["llm_tied"]) / n, 4) if n else 0.0
        entry["topo_top1"] = round(stats["topo_top1"] / n, 4) if n else 0.0
        entry["temporal_top1"] = round(stats["temporal_top1"] / n, 4) if n else 0.0
        entry["llm_top1"] = round(stats["llm_top1"] / n, 4) if n else 0.0
        by_reason_out[reason] = entry

    summary = {
        "total_invoke_llm_cases": len(invoke_llm_records),
        "evaluated": evaluated,
        "skipped": {
            "no_gate_field": skipped_no_gate,
            "not_invoke_llm": skipped_not_invoke,
            "no_gt": skipped_no_gt,
            "skill_ret_error": skipped_skill_ret_error,
        },
        "llm_best": llm_best,
        "llm_tied_for_best": llm_tied,
        "llm_worse": llm_worse,
        "llm_win_rate": round((llm_best + llm_tied) / evaluated, 4) if evaluated else 0.0,
        "when_llm_worse": {
            "better_is_topo": better_is_topo,
            "better_is_temporal": better_is_temporal,
            "better_is_tie_of_topo_temporal": better_is_tie_of_topo_temporal,
        },
        "by_reason": by_reason_out,
        "per_method_topk": per_method_topk,
    }

    # ── 写输出文件 ───────────────────────────────────────────────────
    os.makedirs(out_dir, exist_ok=True)

    write_jsonl(os.path.join(out_dir, "gate_selection_cases.jsonl"), case_rows)
    write_json(os.path.join(out_dir, "gate_selection_summary.json"), summary)

    csv_fields = [
        "reason", "n", "llm_best", "llm_tied", "llm_worse",
        "llm_win_rate", "topo_top1", "temporal_top1", "llm_top1",
    ]
    csv_path = os.path.join(out_dir, "gate_selection_summary.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for reason, stats in sorted(by_reason_out.items()):
            row_out = {"reason": reason, **stats}
            writer.writerow(row_out)

    return summary


# ── CLI ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate whether LLM (gate's chosen output) is the best "
                    "among topo/temporal/LLM for invoke_llm cases."
    )
    parser.add_argument("--res", required=True, help="Path to res.json from SkilledAnalyzer (with confidence_gate)")
    parser.add_argument("--out-dir", required=True, help="Output directory for summary, JSONL, and CSV")
    args = parser.parse_args()

    summary = evaluate_gate_selection(args.res, args.out_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
