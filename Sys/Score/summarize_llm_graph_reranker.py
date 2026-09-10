from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List, Mapping, Sequence

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.RootCauseAnalyze.stage1.llm_graph_reranker_pipeline import CONSENSUS_METHOD
from Sys.RootCauseAnalyze.stage1.neural_graph import load_training_label
from Sys.utils.io_utils import load_json, save_json


DEFAULT_METHODS = (
    "llm_evidence_only",
    "llm_evidence_graph",
    "llm_prior_evidence_graph",
    CONSENSUS_METHOD,
)


def _normalized_path(value: Any) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(value or ""))))


def _records(path: str) -> List[Dict[str, Any]]:
    rows = load_json(path, default=None)
    if not isinstance(rows, list):
        raise ValueError(f"result must contain a JSON list: {path}")
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _ranked_ips(record: Mapping[str, Any]) -> List[str]:
    direct = record.get("ranked_ips")
    if isinstance(direct, list) and direct:
        return list(dict.fromkeys(str(value) for value in direct if value))
    for key in ("final_root_rankings", "initial_root_rankings", "base_root_rankings"):
        raw = record.get(key)
        if isinstance(raw, list):
            values = [
                str(item.get("ip"))
                for item in raw
                if isinstance(item, Mapping) and item.get("ip")
            ]
            if values:
                return list(dict.fromkeys(values))
    stage1 = record.get("stage1", {})
    if isinstance(stage1, Mapping):
        raw = stage1.get("root_rankings")
        if isinstance(raw, list):
            return list(
                dict.fromkeys(
                    str(item.get("ip"))
                    for item in raw
                    if isinstance(item, Mapping) and item.get("ip")
                )
            )
    return []


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return float(ordered[index])


def _input_candidates(
    record: Mapping[str, Any], audit_rows: Sequence[Mapping[str, Any]]
) -> set[str] | None:
    """Use saved prompt inputs; output rankings cannot recover the input set."""
    audited_sets = []
    for row in audit_rows:
        aliases = row.get("candidate_aliases")
        if isinstance(aliases, Mapping) and all(
            isinstance(value, str) and value for value in aliases.values()
        ):
            audited_sets.append(set(aliases.values()))
    if audited_sets:
        if any(candidates != audited_sets[0] for candidates in audited_sets[1:]):
            raise ValueError(f"candidate sets differ across calls: {record.get('dir')}")
        return audited_sets[0]
    # _result_record saves the Top-K input rankings separately from final ranks.
    initial = record.get("initial_root_rankings")
    if isinstance(initial, list) and all(
        isinstance(row, Mapping)
        and isinstance(row.get("ip"), str)
        and row["ip"]
        for row in initial
    ):
        return {row["ip"] for row in initial}
    return None


def _cost_metrics(
    records: Sequence[Mapping[str, Any]],
    audit_by_path: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Dict[str, Any]:
    # Cost belongs to all executed calls, including cases without a root label
    # and calls that have no result row. Each audit call is counted exactly once.
    calls = [row for rows in audit_by_path.values() for row in rows]
    token_counts = [float(row["input_tokens"]) for row in calls if row.get("input_tokens") is not None]
    missing_tokens = sum(row.get("input_tokens") is None for row in calls)
    llm_calls = len(calls)
    for record in records:
        if audit_by_path.get(_normalized_path(record.get("dir"))):
            continue
        details = record.get("llm_reranking", {})
        if isinstance(details, Mapping) and details.get("input_tokens") is not None:
            token_counts.append(float(details["input_tokens"]))
            llm_calls += 1
    return {
        "input_tokens_p50": _percentile(token_counts, 0.50),
        "input_tokens_p95": _percentile(token_counts, 0.95),
        "total_input_tokens": int(sum(token_counts)),
        "llm_calls": llm_calls,
        "calls_missing_input_tokens": missing_tokens,
        "input_token_total_status": "partial" if missing_tokens else "complete_for_counted_calls",
    }


def _evaluate(
    records: Sequence[Mapping[str, Any]],
    baseline_by_path: Mapping[str, Mapping[str, Any]],
    audit_by_path: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> Dict[str, Any]:
    hits = {1: 0, 3: 0, 5: 0}
    reciprocal = 0.0
    reciprocal_at_5 = 0.0
    input_candidate_hits = 0
    input_candidate_cases = 0
    corrections = 0
    corruptions = 0
    promotions = 0
    valid = 0
    abstained = 0
    invalid = 0
    unsupported_refs = 0
    unsupported_graph_edges = 0
    audit_by_path = audit_by_path or {}
    cost_metrics = _cost_metrics(records, audit_by_path)
    evaluated = 0
    for record in records:
        path = _normalized_path(record.get("dir"))
        baseline = baseline_by_path.get(path)
        if baseline is None:
            raise ValueError(f"baseline result is missing for case: {record.get('dir')}")
        gt = load_training_label(str(record.get("dir", "") or ""))
        if not gt:
            continue
        evaluated += 1
        ranking = _ranked_ips(record)
        baseline_ranking = _ranked_ips(baseline)
        audit_rows = audit_by_path.get(path, ())
        input_candidates = _input_candidates(record, audit_rows)
        if input_candidates is not None:
            input_candidate_cases += 1
            input_candidate_hits += int(gt in input_candidates)
        if gt in ranking:
            rank = ranking.index(gt) + 1
            reciprocal += 1.0 / rank
            if rank <= 5:
                reciprocal_at_5 += 1.0 / rank
            for cutoff in hits:
                hits[cutoff] += int(rank <= cutoff)
        before = baseline_ranking[0] if baseline_ranking else ""
        after = ranking[0] if ranking else ""
        before_correct = before == gt
        after_correct = after == gt
        promotions += int(bool(before and after and before != after))
        corrections += int(not before_correct and after_correct)
        corruptions += int(before_correct and not after_correct)
        details = record.get("llm_reranking", {})
        details = details if isinstance(details, Mapping) else {}
        if details:
            valid += int(bool(details.get("valid")))
            abstained += int(bool(details.get("abstained")))
            invalid += int(
                not details.get("valid") and not details.get("abstained")
            )
            unsupported_refs += len(details.get("unsupported_evidence_ids", []))
            unsupported_graph_edges += len(
                details.get("unsupported_graph_edges", [])
            )
    total = evaluated
    candidate_recall = round(input_candidate_hits / input_candidate_cases, 6) if input_candidate_cases else None
    return {
        "cases": total,
        "top1": round(hits[1] / total * 100.0, 2) if total else 0.0,
        "top3": round(hits[3] / total * 100.0, 2) if total else 0.0,
        "top5": round(hits[5] / total * 100.0, 2) if total else 0.0,
        "mrr": round(reciprocal / total, 6) if total else 0.0,
        "mrr_at_5": round(reciprocal_at_5 / total, 6) if total else 0.0,
        "candidate_recall": candidate_recall,
        "input_candidate_recall": candidate_recall,
        "input_candidate_recall_known_cases": input_candidate_cases,
        "input_candidate_recall_unknown_cases": total - input_candidate_cases,
        "input_candidate_recall_status": (
            "available" if input_candidate_cases and input_candidate_cases == total
            else "partial" if input_candidate_cases else "unavailable"
        ),
        "promotions": promotions,
        "corrections": corrections,
        "corruptions": corruptions,
        "net_corrections": corrections - corruptions,
        "valid_responses": valid,
        "abstentions": abstained,
        "invalid_responses": invalid,
        "unsupported_evidence_references": unsupported_refs,
        "unsupported_graph_edge_references": unsupported_graph_edges,
        **cost_metrics,
    }


def _baseline_metrics(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    by_path = {_normalized_path(row.get("dir")): row for row in records}
    return _evaluate(records, by_path)


def _load_audit(experiment_dir: str, method: str) -> Dict[str, List[Dict[str, Any]]]:
    """Load per-call audit rows, when available, for complete cost accounting."""
    path = os.path.join(experiment_dir, method, "llm_audit.json")
    if not os.path.isfile(path):
        return {}
    payload = load_json(path, default={})
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, Mapping):
        rows = payload.get("repeat_calls", [])
        # The consensus output stores only the additional calls.  Include the
        # first call from the direct prior+evidence+graph variant as well.
        if method == CONSENSUS_METHOD:
            direct_path = os.path.join(
                experiment_dir, "llm_prior_evidence_graph", "llm_audit.json"
            )
            direct_payload = load_json(direct_path, default=[])
            if isinstance(direct_payload, list):
                rows = [*direct_payload, *rows]
    else:
        rows = []
    result: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = _normalized_path(row.get("dir"))
        result.setdefault(key, []).append(dict(row))
    return result


def summarize(args: argparse.Namespace) -> str:
    baseline_records = _records(args.baseline_res)
    baseline_by_path = {
        _normalized_path(row.get("dir")): row for row in baseline_records
    }
    results = [
        {"experiment": "stage1", **_baseline_metrics(baseline_records)}
    ]
    for method in args.methods:
        path = os.path.join(args.experiment_dir, method, "res.json")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"missing LLM result: {path}")
        metrics = _evaluate(
            _records(path),
            baseline_by_path,
            _load_audit(args.experiment_dir, method),
        )
        results.append({"experiment": method, **metrics})
    by_name = {row["experiment"]: row for row in results}

    def effect(left: str, right: str) -> Dict[str, Any]:
        if left not in by_name or right not in by_name:
            return {}
        return {
            "top1": round(by_name[left]["top1"] - by_name[right]["top1"], 2),
            "mrr": round(by_name[left]["mrr"] - by_name[right]["mrr"], 6),
            "mrr_at_5": round(
                by_name[left]["mrr_at_5"] - by_name[right]["mrr_at_5"], 6
            ),
            "net_corrections": (
                by_name[left]["net_corrections"] - by_name[right]["net_corrections"]
            ),
        }

    summary = {
        "evaluation": "labels_joined_only_after_all_llm_outputs",
        "baseline_res": os.path.abspath(args.baseline_res),
        "experiment_dir": os.path.abspath(args.experiment_dir),
        "results": results,
        "effects": {
            "graph_increment_over_evidence_only": effect(
                "llm_evidence_graph", "llm_evidence_only"
            ),
            "stage1_prior_increment_over_graph": effect(
                "llm_prior_evidence_graph", "llm_evidence_graph"
            ),
            "final_consensus_over_stage1": effect(CONSENSUS_METHOD, "stage1"),
            "consensus_gate_over_direct_llm": effect(
                CONSENSUS_METHOD, "llm_prior_evidence_graph"
            ),
        },
    }
    summary_path = os.path.join(args.experiment_dir, "summary.json")
    save_json(summary, summary_path, indent=2)
    fields = [
        "experiment",
        "cases",
        "top1",
        "top3",
        "top5",
        "mrr",
        "mrr_at_5",
        "candidate_recall",
        "input_candidate_recall",
        "input_candidate_recall_known_cases",
        "input_candidate_recall_unknown_cases",
        "input_candidate_recall_status",
        "promotions",
        "corrections",
        "corruptions",
        "net_corrections",
        "valid_responses",
        "abstentions",
        "invalid_responses",
        "unsupported_evidence_references",
        "unsupported_graph_edge_references",
        "total_input_tokens",
        "llm_calls",
        "calls_missing_input_tokens",
        "input_token_total_status",
    ]
    with open(
        os.path.join(args.experiment_dir, "summary.csv"),
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key, "") for key in fields})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate the label-free local-LLM graph reranker ablation"
    )
    parser.add_argument("--baseline-res", required=True)
    parser.add_argument("--experiment-dir", required=True)
    parser.add_argument("--methods", nargs="+", default=list(DEFAULT_METHODS))
    return parser


def main() -> None:
    summarize(build_parser().parse_args())


if __name__ == "__main__":
    main()
