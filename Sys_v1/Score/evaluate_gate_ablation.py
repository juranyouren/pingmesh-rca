"""
Gate Policy Ablation
====================
Runs multiple gate routing policies against gate_pipe_llm/res.json,
simulates routing decisions, and compares Top-K metrics across policies.

用法:
    python Sys_v1/Score/evaluate_gate_ablation.py \
        --res <gate_pipe_llm/res.json> \
        --out-dir <dir> \
        --policies baseline,strict_combined,conservative
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys_v1.RootCauseAnalyze.gate_policies import list_policies
from Sys_v1.RootCauseAnalyze.trust_trees.common import unique_ips
from Sys_v1.Score.Score_N import GroundTruth, MetricsEvaluator, Prediction, ResponseParser, Scorer
from Sys_v1.Score.evaluate_gate_selection import _extract_method_ips, _extract_skill_ret_from_prompt
from Sys_v1.utils.io_utils import case_id_from_dir, load_json, write_csv, write_json, write_jsonl

# ── helpers ──────────────────────────────────────────────────────────


def _extract_combined_ips(skill_ret: Dict[str, Any]) -> List[str]:
    """Extract combined_score IPs sorted by combined_score descending."""
    rankings = skill_ret.get("combined_score_rankings", [])
    if not isinstance(rankings, list):
        return []
    scored: List[Tuple[str, float]] = []
    for item in rankings:
        if not isinstance(item, dict):
            continue
        ip = item.get("ip")
        if not isinstance(ip, str) or not ip:
            continue
        try:
            s = float(item.get("combined_score", 0.0))
        except (TypeError, ValueError):
            s = 0.0
        scored.append((ip, s))
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return unique_ips(ip for ip, _score in scored)


def _extract_llm_ips(response: str) -> List[str]:
    parser = ResponseParser()
    return parser.parse(response or "").ips


def _compute_metrics(gt_ips: List[str], pred_ips: List[str]) -> Dict[str, Any]:
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
        "best_rank": result.get("best_rank"),
        "is_failed": bool(result.get("is_failed")),
        "pred_ips": result.get("pred_ips", pred_ips),
    }


def _build_ablation_entry(
    record: Dict[str, Any],
    idx: int,
    policies: Dict[str, Any],
    gt_ips: List[str],
    combined_ips: List[str],
    topo_ips: List[str],
    temporal_ips: List[str],
    topo_tree: Dict[str, Any],
    temporal_tree: Dict[str, Any],
) -> Dict[str, Any]:
    """Run all policies against one case, return a row dict."""
    case_dir = record.get("dir", "")
    case_id = case_id_from_dir(case_dir, f"case_{idx:05d}")
    original_gate = record.get("confidence_gate", {})

    entry: Dict[str, Any] = {
        "case_id": case_id,
        "case_dir": case_dir,
        "gt_ips": gt_ips,
        "original_gate_route": original_gate.get("route", "unknown"),
        "original_gate_decision": original_gate.get("decision", "unknown"),
        "original_gate_reason": original_gate.get("reason", "unknown"),
        "topo_state": topo_tree.get("state", "uncertain"),
        "temporal_state": temporal_tree.get("state", "uncertain"),
        "combined_ips": combined_ips[:10],
        "topo_ips": topo_ips[:10],
        "temporal_ips": temporal_ips[:10],
    }

    for pol_name, route_fn in policies.items():
        try:
            gate = route_fn(
                combined_ips=combined_ips,
                topo_ips=topo_ips,
                temporal_ips=temporal_ips,
                topo_tree=topo_tree,
                temporal_tree=temporal_tree,
            )
        except Exception:
            gate = {"decision": "error", "route": "unknown", "reason": "policy_call_failed"}

        decision = gate.get("decision", "unknown")
        route = gate.get("route", "unknown")
        reason = gate.get("reason", "unknown")

        # Determine evaluated IPs
        eval_ips: Optional[List[str]] = None
        eval_source = route  # default
        if route in ("combined",):
            eval_ips = combined_ips
        elif route in ("temporal",):
            eval_ips = temporal_ips
        elif route in ("topo",):
            eval_ips = topo_ips
        elif route in ("operator",):
            eval_ips = []  # no prediction
            eval_source = "operator_empty"
        elif route in ("llm",):
            # Only evaluate if the original experiment actually ran LLM for this case
            if original_gate.get("decision") == "invoke_llm":
                eval_ips = _extract_llm_ips(record.get("response", ""))
                eval_source = "llm"
            else:
                # LLM was not run for this case — can't evaluate
                eval_ips = None
                eval_source = "llm_unavailable"

        metrics = _compute_metrics(gt_ips, eval_ips) if eval_ips is not None else {}

        entry[f"{pol_name}_decision"] = decision
        entry[f"{pol_name}_route"] = route
        entry[f"{pol_name}_reason"] = reason
        entry[f"{pol_name}_eval_source"] = eval_source
        entry[f"{pol_name}_top1_hit"] = metrics.get("top1_hit")
        entry[f"{pol_name}_top3_hit"] = metrics.get("top3_hit")
        entry[f"{pol_name}_top5_hit"] = metrics.get("top5_hit")
        entry[f"{pol_name}_best_rank"] = metrics.get("best_rank")

        # route_changed flag vs baseline
        if pol_name != "baseline":
            baseline_route = entry.get("baseline_route", original_gate.get("route", "unknown"))
            entry[f"{pol_name}_route_changed"] = (route != baseline_route)

    return entry


def _aggregate(
    rows: List[Dict[str, Any]],
    policy_names: List[str],
) -> Dict[str, Any]:
    """Aggregate per-policy Top-K and routing stats."""
    per_policy: Dict[str, Dict[str, Any]] = {}
    for pol in policy_names:
        evaluated_rows = [r for r in rows if r.get(f"{pol}_top1_hit") is not None]
        n = len(evaluated_rows)
        per_policy[pol] = {
            "evaluated": n,
            "total": len(rows),
            "top1": round(sum(1 for r in evaluated_rows if r[f"{pol}_top1_hit"]) / n, 4) if n else 0,
            "top3": round(sum(1 for r in evaluated_rows if r[f"{pol}_top3_hit"]) / n, 4) if n else 0,
            "top5": round(sum(1 for r in evaluated_rows if r[f"{pol}_top5_hit"]) / n, 4) if n else 0,
        }

    # route distribution
    route_dist: Dict[str, Dict[str, int]] = {}
    for pol in policy_names:
        dist: Dict[str, int] = defaultdict(int)
        for r in rows:
            route = r.get(f"{pol}_route", "unknown")
            dist[route] += 1
        route_dist[pol] = dict(dist)

    # llm_unavailable counts
    llm_unavailable: Dict[str, int] = {}
    for pol in policy_names:
        llm_unavailable[pol] = sum(
            1 for r in rows if r.get(f"{pol}_eval_source") == "llm_unavailable"
        )

    # route changes vs baseline
    route_changes: Dict[str, Dict[str, Any]] = {}
    for pol in policy_names:
        if pol == "baseline":
            continue
        changes: Dict[str, int] = defaultdict(int)
        for r in rows:
            if r.get(f"{pol}_route_changed"):
                bl = r.get("baseline_route", "?")
                pl = r.get(f"{pol}_route", "?")
                changes[f"{bl}_to_{pl}"] += 1
        route_changes[pol] = dict(changes)

    return {
        "per_policy": per_policy,
        "route_distribution": route_dist,
        "llm_unavailable": llm_unavailable,
        "route_changes_vs_baseline": route_changes,
    }


# ── main ─────────────────────────────────────────────────────────────


def evaluate_gate_ablation(
    res_path: str,
    out_dir: str,
    policy_names: Sequence[str],
) -> Dict[str, Any]:
    records = load_json(res_path)
    if not isinstance(records, list):
        raise ValueError(f"{res_path} must contain a JSON list")

    # ── load policies ────────────────────────────────────────────────
    all_policies = list_policies()
    policies: Dict[str, Any] = {}
    for name in policy_names:
        if name in all_policies:
            policies[name] = all_policies[name]
        else:
            print(f"Warning: policy {name!r} not found; available: {sorted(all_policies)}")

    if not policies:
        raise ValueError("No valid policies selected.")

    # ── per-case evaluation ─────────────────────────────────────────
    case_rows: List[Dict[str, Any]] = []
    skipped_no_gt = 0
    skipped_no_skill_ret = 0

    for idx, record in enumerate(records):
        case_dir = record.get("dir", "")

        # GT
        try:
            gt = Scorer._get_groundtruth(case_dir)
        except Exception:
            gt = GroundTruth(ips=[])
        gt_ips = gt.ips
        if not gt_ips:
            skipped_no_gt += 1
            continue

        # skill_ret
        prompt = record.get("prompt", "")
        skill_ret = _extract_skill_ret_from_prompt(prompt)
        if skill_ret is None:
            skipped_no_skill_ret += 1
            continue

        combined_ips = _extract_combined_ips(skill_ret)
        topo_ips = _extract_method_ips(skill_ret, "topo")
        temporal_ips = _extract_method_ips(skill_ret, "temporal")

        topo_block = skill_ret.get("topo", {})
        temporal_block = skill_ret.get("temporal", {})
        topo_tree = topo_block.get("trust_tree", {}) if isinstance(topo_block, dict) else {}
        temporal_tree = temporal_block.get("trust_tree", {}) if isinstance(temporal_block, dict) else {}

        row = _build_ablation_entry(
            record, idx, policies, gt_ips,
            combined_ips, topo_ips, temporal_ips,
            topo_tree, temporal_tree,
        )
        case_rows.append(row)

    # ── aggregate ────────────────────────────────────────────────────
    aggregate = _aggregate(case_rows, list(policies.keys()))

    summary: Dict[str, Any] = {
        "total_cases_in_file": len(records),
        "evaluated_cases": len(case_rows),
        "skipped": {
            "no_gt": skipped_no_gt,
            "no_skill_ret": skipped_no_skill_ret,
        },
        "policies_tested": sorted(policies.keys()),
        **aggregate,
    }

    # ── output ───────────────────────────────────────────────────────
    os.makedirs(out_dir, exist_ok=True)

    write_jsonl(os.path.join(out_dir, "ablation_cases.jsonl"), case_rows)
    write_json(os.path.join(out_dir, "ablation_summary.json"), summary)

    # CSV: one row per policy
    csv_fields = ["policy", "evaluated", "top1", "top3", "top5",
                  "route_combined", "route_temporal", "route_topo", "route_llm", "route_operator",
                  "llm_unavailable"]
    csv_rows = []
    for pol in policies:
        pp = aggregate["per_policy"].get(pol, {})
        rd = aggregate["route_distribution"].get(pol, {})
        csv_rows.append({
            "policy": pol,
            "evaluated": pp.get("evaluated", 0),
            "top1": pp.get("top1", 0),
            "top3": pp.get("top3", 0),
            "top5": pp.get("top5", 0),
            "route_combined": rd.get("combined", 0),
            "route_temporal": rd.get("temporal", 0),
            "route_topo": rd.get("topo", 0),
            "route_llm": rd.get("llm", 0),
            "route_operator": rd.get("operator", 0),
            "llm_unavailable": aggregate["llm_unavailable"].get(pol, 0),
        })
    write_csv(os.path.join(out_dir, "ablation_summary.csv"), csv_rows, csv_fields)

    return summary


# ── CLI ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ablate gate routing policies on gate_pipe_llm results."
    )
    parser.add_argument("--res", required=True, help="Path to gate_pipe_llm/res.json")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument(
        "--policies",
        default="baseline,strict_combined,conservative",
        help="Comma-separated policy names to test (default: baseline,strict_combined,conservative)",
    )
    args = parser.parse_args()

    policy_names = [n.strip() for n in args.policies.split(",") if n.strip()]
    summary = evaluate_gate_ablation(args.res, args.out_dir, policy_names)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
