"""Search configurable gate policies under fail-closed safety constraints."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.RootCauseAnalyze.gate_policies.configurable import (
    grid_policy_configs,
    named_policy_configs,
)
from Sys.Score.evaluate_gate_recall import build_gate_recall_rows, _metric_at
from Sys.Score.evaluate_trust_gate import (
    _case_id,
    _gt_ips,
    _load_json,
    _write_csv,
    _write_json,
    _write_jsonl,
)


def _prepare_records(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Resolve labels once so a grid search does not repeatedly read case files."""
    prepared: List[Dict[str, Any]] = []
    for record in records:
        copy = dict(record)
        if not copy.get("gt_ips"):
            copy["gt_ips"] = _gt_ips(copy)
        prepared.append(copy)
    return prepared


def _fold_for(case_id: str, folds: int) -> int:
    digest = hashlib.sha256(case_id.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % folds


def _wilson_lower(successes: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = proportion + z * z / (2.0 * total)
    spread = z * math.sqrt(
        proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)
    )
    return round((center - spread) / denominator, 6)


def _case_aliases(row: Mapping[str, Any]) -> Set[str]:
    case_dir = str(row.get("case_dir") or "")
    aliases = {str(row.get("case_id") or ""), case_dir}
    if case_dir:
        aliases.add(os.path.basename(os.path.normpath(case_dir)))
    return {value for value in aliases if value}


def _badcase_bypass_count(rows: Sequence[Dict[str, Any]], badcase_ids: Set[str]) -> int:
    if not badcase_ids:
        return 0
    return sum(
        1
        for row in rows
        if row["bypassed"] and _case_aliases(row).intersection(badcase_ids)
    )


def _extract_badcase_ids(values: Iterable[Any]) -> Set[str]:
    ids: Set[str] = set()
    for value in values:
        if isinstance(value, str) and value.strip():
            ids.add(value.strip())
        elif isinstance(value, dict):
            for key in ("case_id", "case_dir", "dir", "path"):
                raw = value.get(key)
                if isinstance(raw, str) and raw.strip():
                    ids.add(raw.strip())
                    ids.add(os.path.basename(os.path.normpath(raw.strip())))
    return ids


def load_badcase_ids(path: str | None) -> Set[str]:
    if not path:
        return set()
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8-sig") as handle:
            return _extract_badcase_ids(csv.DictReader(handle))

    with open(path, encoding="utf-8") as handle:
        text = handle.read().strip()
    if not text:
        return set()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(payload, dict):
        for key in ("badcases", "cases", "records"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON list, JSONL rows, or CSV rows")
    return _extract_badcase_ids(payload)


def _candidate_configs(include_grid: bool) -> List[Dict[str, Any]]:
    configs = named_policy_configs()
    if include_grid:
        configs.extend(grid_policy_configs())
    unique: Dict[str, Dict[str, Any]] = {}
    for config in configs:
        unique[str(config["name"])] = config
    return list(unique.values())


def _strictness_key(config: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        int(config.get("min_evidence_votes", 0)),
        float(config.get("combined_margin_percent", 0.0)),
        float(config.get("ranker_margin_percent", 0.0)),
        int(config.get("top1_requirement") == "unanimous"),
        int(config.get("trust_requirement") == "both_strong"),
        int(config.get("topology_support") == "exact_top1"),
        int(config.get("temporal_support") == "exact_top1"),
        int(config.get("ranker_margin_requirement") == "both"),
    )


def search_gate_policy(
    records: Sequence[Dict[str, Any]],
    *,
    out_dir: str,
    target_k: int = 1,
    folds: int = 5,
    badcase_ids: Set[str] | None = None,
    min_error_recall: float = 1.0,
    max_unsafe_bypass: int = 0,
    include_grid: bool = True,
) -> Dict[str, Any]:
    if target_k not in {1, 3, 5}:
        raise ValueError("target_k must be one of 1, 3, or 5")
    if folds < 2:
        raise ValueError("folds must be at least 2")
    if not 0.0 <= min_error_recall <= 1.0:
        raise ValueError("min_error_recall must be between 0 and 1")
    if max_unsafe_bypass < 0:
        raise ValueError("max_unsafe_bypass must be non-negative")

    prepared = _prepare_records(records)
    known_badcases = badcase_ids or set()
    configs = _candidate_configs(include_grid)
    comparison_rows: List[Dict[str, Any]] = []
    fold_rows: List[Dict[str, Any]] = []
    configs_by_name: Dict[str, Dict[str, Any]] = {}

    for config in configs:
        name = str(config["name"])
        configs_by_name[name] = config
        all_rows = build_gate_recall_rows(
            prepared,
            policy_config=config,
            labeled_only=False,
        )
        rows = [row for row in all_rows if row["gt_ips"]]
        metrics = _metric_at(rows, target_k)
        badcase_bypasses = _badcase_bypass_count(all_rows, known_badcases)
        candidate_fold_rows: List[Dict[str, Any]] = []
        for fold in range(folds):
            fold_cases = [row for row in rows if _fold_for(row["case_id"], folds) == fold]
            if not fold_cases:
                continue
            fold_metrics = _metric_at(fold_cases, target_k)
            fold_safe = (
                fold_metrics["unsafe_bypass_count"] <= max_unsafe_bypass
                and fold_metrics["error_recall"] >= min_error_recall
            )
            candidate_fold_rows.append(
                {
                    "policy_name": name,
                    "fold": fold,
                    "fold_safe": fold_safe,
                    **fold_metrics,
                }
            )
        fold_rows.extend(candidate_fold_rows)
        fold_safe = all(row["fold_safe"] for row in candidate_fold_rows)
        has_error_cases = metrics["deterministic_error_cases"] > 0
        eligible = (
            has_error_cases
            and metrics["unsafe_bypass_count"] <= max_unsafe_bypass
            and metrics["error_recall"] >= min_error_recall
            and badcase_bypasses == 0
            and fold_safe
        )
        if config.get("always_llm"):
            eligible = (
                metrics["unsafe_bypass_count"] <= max_unsafe_bypass
                and badcase_bypasses == 0
            )
        comparison_rows.append(
            {
                "policy_name": name,
                "eligible": eligible,
                "fold_safe": fold_safe,
                "has_error_cases": has_error_cases,
                "known_badcase_bypass_count": badcase_bypasses,
                "precision_wilson_lower": _wilson_lower(
                    metrics["safe_bypass_count"], metrics["bypass_count"]
                ),
                **metrics,
                "always_llm": bool(config.get("always_llm")),
                "legacy_v1": bool(config.get("legacy_v1")),
                "top1_requirement": config.get("top1_requirement"),
                "require_temporal_data": bool(config.get("require_temporal_data")),
                "trust_requirement": config.get("trust_requirement"),
                "combined_margin_percent": config.get("combined_margin_percent"),
                "ranker_margin_percent": config.get("ranker_margin_percent"),
                "min_evidence_votes": config.get("min_evidence_votes"),
                "topology_support": config.get("topology_support"),
                "temporal_support": config.get("temporal_support"),
                "ranker_margin_requirement": config.get("ranker_margin_requirement"),
            }
        )

    productive = [
        row
        for row in comparison_rows
        if row["eligible"] and row["bypass_count"] > 0 and not row["always_llm"]
    ]
    fallback = not productive
    if productive:
        selected_row = max(
            productive,
            key=lambda row: (
                row["bypass_coverage"],
                row["precision_wilson_lower"],
                _strictness_key(configs_by_name[row["policy_name"]]),
            ),
        )
    else:
        selected_row = next(
            row for row in comparison_rows if row["policy_name"] == "always_llm"
        )

    selected_name = str(selected_row["policy_name"])
    selected_config = configs_by_name[selected_name]
    selected_all_rows = build_gate_recall_rows(
        prepared,
        policy_config=selected_config,
        labeled_only=False,
    )
    selected_rows = [row for row in selected_all_rows if row["gt_ips"]]
    unsafe_rows = [
        row
        for row in selected_all_rows
        if (row["gt_ips"] and row[f"unsafe_bypass_at_{target_k}"])
        or (row["bypassed"] and _case_aliases(row).intersection(known_badcases))
    ]
    selection = {
        "schema_version": 1,
        "selected_policy": selected_name,
        "selected_config": selected_config,
        "selection_metrics": {
            key: value
            for key, value in selected_row.items()
            if key
            in {
                "eligible",
                "fold_safe",
                "labeled_cases",
                "deterministic_error_cases",
                "caught_error_cases",
                "error_recall",
                "unsafe_bypass_count",
                "known_badcase_bypass_count",
                "bypass_count",
                "safe_bypass_count",
                "bypass_precision",
                "precision_wilson_lower",
                "bypass_coverage",
                "reinference_count",
                "reinference_coverage",
            }
        },
        "selection_rule": (
            "zero unsafe bypass and no known-badcase bypass; error recall at or above "
            "threshold globally and in every non-empty fold; then maximize bypass coverage"
        ),
        "fallback_to_always_llm": fallback,
        "target_k": target_k,
        "folds": folds,
        "min_error_recall": min_error_recall,
        "max_unsafe_bypass": max_unsafe_bypass,
        "known_badcase_count": len(known_badcases),
        "evaluated_policy_count": len(comparison_rows),
    }

    os.makedirs(out_dir, exist_ok=True)
    comparison_fields = [
        "policy_name", "eligible", "fold_safe", "has_error_cases",
        "labeled_cases", "deterministic_error_cases", "caught_error_cases",
        "error_recall", "unsafe_bypass_count", "known_badcase_bypass_count",
        "bypass_count", "safe_bypass_count", "bypass_precision",
        "precision_wilson_lower", "bypass_coverage", "reinference_count",
        "reinference_coverage", "always_llm", "legacy_v1", "top1_requirement",
        "require_temporal_data", "trust_requirement",
        "combined_margin_percent", "ranker_margin_percent", "min_evidence_votes",
        "topology_support", "temporal_support", "ranker_margin_requirement",
    ]
    fold_fields = [
        "policy_name", "fold", "fold_safe", "labeled_cases",
        "deterministic_error_cases", "caught_error_cases", "unsafe_bypass_count",
        "error_recall", "bypass_count", "safe_bypass_count", "bypass_precision",
        "bypass_coverage", "reinference_count", "reinference_coverage",
    ]
    _write_csv(os.path.join(out_dir, "policy_comparison.csv"), comparison_rows, comparison_fields)
    _write_csv(os.path.join(out_dir, "policy_folds.csv"), fold_rows, fold_fields)
    _write_json(os.path.join(out_dir, "selected_gate_policy.json"), selection)
    _write_json(os.path.join(out_dir, "search_summary.json"), selection)
    _write_jsonl(os.path.join(out_dir, "selected_policy_cases.jsonl"), selected_all_rows)
    _write_jsonl(os.path.join(out_dir, "unsafe_bypass_cases.jsonl"), unsafe_rows)
    return selection


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select the highest-coverage gate policy that satisfies recall safety constraints."
    )
    parser.add_argument("--res", required=True, help="Deterministic skillpipe res.json")
    parser.add_argument("--out-dir", required=True, help="Directory for policy search reports")
    parser.add_argument("--target-k", type=int, choices=[1, 3, 5], default=1)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--badcases", help="Optional known-bad case list in JSON, JSONL, or CSV")
    parser.add_argument("--min-error-recall", type=float, default=1.0)
    parser.add_argument("--max-unsafe-bypass", type=int, default=0)
    parser.add_argument(
        "--named-only",
        action="store_true",
        help="Evaluate only named policies; skip the parameter grid.",
    )
    args = parser.parse_args()

    records = _load_json(args.res)
    if not isinstance(records, list):
        raise ValueError(f"{args.res} must contain a JSON list")
    selection = search_gate_policy(
        records,
        out_dir=args.out_dir,
        target_k=args.target_k,
        folds=args.folds,
        badcase_ids=load_badcase_ids(args.badcases),
        min_error_recall=args.min_error_recall,
        max_unsafe_bypass=args.max_unsafe_bypass,
        include_grid=not args.named_only,
    )
    print(json.dumps(selection, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
