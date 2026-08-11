#!/usr/bin/env python3
"""Evaluate candidate recall for several Top-k values without running an LLM."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Sys.RootCauseAnalyze.skills.topo_ranker import score_topo, topo_details
from Sys.Score.Score_N import Scorer
from Sys.utils.case_utils import get_device_ip, load_case_info, load_case_nodes
from Sys.utils.ranking_utils import sorted_score_items
from scripts.build_evidence_tables import case_key, discover_cases
from scripts.run_ablation_study import (
    _load_case_evidence,
    _load_evidence_index,
    build_evidence_ranking,
)


DEFAULT_K_VALUES = (5, 7, 8, 9, 10)
STRATEGY_FIELDS = {
    "pagerank": "pagerank_ranking",
    "pagerank+temporal": "pagerank_temporal_ranking",
}


def _save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def _write_jsonl(rows: Iterable[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_csv(rows: Sequence[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        if not fieldnames:
            return
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _normalize_k_values(values: Sequence[int]) -> List[int]:
    normalized = sorted({int(value) for value in values if int(value) > 0})
    if not normalized:
        raise ValueError("at least one positive k value is required")
    return normalized


def _pagerank_scores(
    nodes: List[Dict[str, Any]],
    info: Dict[str, Any],
    all_ips: Sequence[str],
    *,
    weight_file: str | None,
    directed: bool,
) -> Dict[str, float]:
    raw_scores = score_topo(
        nodes,
        info,
        weight_path=weight_file,
        directed=directed,
    )
    if raw_scores:
        return {ip: float(raw_scores.get(ip, 0.0)) for ip in all_ips}

    detail = topo_details(
        nodes,
        info,
        {},
        weight_path=weight_file,
        directed=directed,
        top_k=len(all_ips),
    )
    fallback = {
        row.get("ip"): float(row.get("pr_score", 0.0))
        for row in detail.get("rankings", [])
        if isinstance(row, dict) and row.get("ip")
    }
    return {ip: fallback.get(ip, 0.0) for ip in all_ips}


def _combined_scores(
    pagerank_scores: Dict[str, float],
    temporal_scores: Dict[str, float],
    all_ips: Sequence[str],
) -> Dict[str, float]:
    return {
        ip: (
            float(pagerank_scores.get(ip, 0.0))
            + float(temporal_scores.get(ip, 0.0))
        )
        / 2.0
        for ip in all_ips
    }


def _best_rank(ground_truth_ips: Sequence[str], ranking: Sequence[str]) -> int | None:
    positions = {ip: index + 1 for index, ip in enumerate(ranking)}
    ranks = [positions[ip] for ip in ground_truth_ips if ip in positions]
    return min(ranks) if ranks else None


def _ranking_rows(
    ranking: Sequence[str],
    pagerank_scores: Dict[str, float],
    temporal_scores: Dict[str, float],
    combined_scores: Dict[str, float],
) -> List[Dict[str, Any]]:
    return [
        {
            "rank": rank,
            "ip": ip,
            "pagerank_score": round(float(pagerank_scores.get(ip, 0.0)), 8),
            "temporal_score": round(float(temporal_scores.get(ip, 0.0)), 8),
            "combined_score": round(float(combined_scores.get(ip, 0.0)), 8),
        }
        for rank, ip in enumerate(ranking, 1)
    ]


def evaluate_case(
    *,
    dirpath: str,
    data_root: str,
    evidence_root: Path,
    evidence_index: Dict[str, Dict[str, Any]],
    weight_file: str | None,
    directed: bool,
) -> Dict[str, Any] | None:
    ground_truth = Scorer._get_groundtruth(dirpath)
    if not ground_truth.ips:
        return None

    nodes = load_case_nodes(dirpath)
    info = load_case_info(dirpath)
    all_ips = sorted(
        {
            get_device_ip(node)
            for node in nodes
            if get_device_ip(node) not in ("", "unknown")
        }
    )
    if not all_ips:
        raise ValueError(f"no valid devices found under {dirpath}")

    evidence_table = _load_case_evidence(
        dirpath,
        evidence_root,
        evidence_index,
        data_root,
    )
    pagerank_scores = _pagerank_scores(
        nodes,
        info,
        all_ips,
        weight_file=weight_file,
        directed=directed,
    )
    temporal_scores, _temporal_detail = build_evidence_ranking(
        evidence_table,
        all_ips,
    )
    combined_scores = _combined_scores(
        pagerank_scores,
        temporal_scores,
        all_ips,
    )

    pagerank_ranking = [ip for ip, _score in sorted_score_items(pagerank_scores)]
    combined_ranking = [ip for ip, _score in sorted_score_items(combined_scores)]
    cid = evidence_table.get("case_id") or case_key(dirpath, data_root)
    return {
        "case_id": cid,
        "dir": os.path.abspath(dirpath),
        "ground_truth_ips": list(ground_truth.ips),
        "ground_truth_source": ground_truth.source,
        "device_count": len(all_ips),
        "pagerank_best_rank": _best_rank(ground_truth.ips, pagerank_ranking),
        "pagerank_temporal_best_rank": _best_rank(
            ground_truth.ips,
            combined_ranking,
        ),
        "pagerank_ranking": _ranking_rows(
            pagerank_ranking,
            pagerank_scores,
            temporal_scores,
            combined_scores,
        ),
        "pagerank_temporal_ranking": _ranking_rows(
            combined_ranking,
            pagerank_scores,
            temporal_scores,
            combined_scores,
        ),
    }


def summarize_recall(
    records: Sequence[Dict[str, Any]],
    k_values: Sequence[int],
) -> Dict[str, Any]:
    normalized_k = _normalize_k_values(k_values)
    strategies: Dict[str, Dict[str, Any]] = {}
    for strategy, ranking_field in STRATEGY_FIELDS.items():
        strategy_summary: Dict[str, Any] = {}
        for k in normalized_k:
            hits = 0
            for record in records:
                ranking_ips = [row["ip"] for row in record[ranking_field]]
                if any(ip in set(ranking_ips[:k]) for ip in record["ground_truth_ips"]):
                    hits += 1
            total = len(records)
            strategy_summary[str(k)] = {
                "evaluated_case_count": total,
                "hit_count": hits,
                "miss_count": total - hits,
                "recall": round(hits / total, 6) if total else 0.0,
            }
        strategies[strategy] = strategy_summary
    return {
        "k_values": normalized_k,
        "evaluated_case_count": len(records),
        "strategies": strategies,
    }


def _summary_csv_rows(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for strategy, by_k in summary["strategies"].items():
        for k in summary["k_values"]:
            metrics = by_k[str(k)]
            rows.append({"strategy": strategy, "k": k, **metrics})
    return rows


def _case_csv_rows(
    records: Sequence[Dict[str, Any]],
    k_values: Sequence[int],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in records:
        for strategy, ranking_field in STRATEGY_FIELDS.items():
            ranking_ips = [row["ip"] for row in record[ranking_field]]
            row: Dict[str, Any] = {
                "case_id": record["case_id"],
                "dir": record["dir"],
                "strategy": strategy,
                "ground_truth_ips": "|".join(record["ground_truth_ips"]),
                "ground_truth_source": record["ground_truth_source"],
                "device_count": record["device_count"],
                "best_rank": _best_rank(record["ground_truth_ips"], ranking_ips) or "",
                "top10_ips": "|".join(ranking_ips[:10]),
            }
            for k in k_values:
                row[f"hit_at_{k}"] = int(
                    any(ip in set(ranking_ips[:k]) for ip in record["ground_truth_ips"])
                )
            rows.append(row)
    return rows


def _miss_csv_rows(
    records: Sequence[Dict[str, Any]],
    k_values: Sequence[int],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in records:
        for strategy, ranking_field in STRATEGY_FIELDS.items():
            ranking_ips = [row["ip"] for row in record[ranking_field]]
            best_rank = _best_rank(record["ground_truth_ips"], ranking_ips)
            for k in k_values:
                if any(ip in set(ranking_ips[:k]) for ip in record["ground_truth_ips"]):
                    continue
                rows.append(
                    {
                        "strategy": strategy,
                        "k": k,
                        "case_id": record["case_id"],
                        "dir": record["dir"],
                        "ground_truth_ips": "|".join(record["ground_truth_ips"]),
                        "best_rank": best_rank or "not_ranked",
                        "device_count": record["device_count"],
                        "topk_ips": "|".join(ranking_ips[:k]),
                    }
                )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate candidate recall for PageRank and full-device "
            "PageRank+temporal rankings."
        )
    )
    parser.add_argument("--data-root", "-d", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--k-values",
        nargs="+",
        type=int,
        default=list(DEFAULT_K_VALUES),
    )
    parser.add_argument("--weight-file", default=None)
    parser.add_argument("--undirected", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--continue-on-error", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_root = os.path.abspath(args.data_root)
    evidence_root = Path(args.evidence_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    k_values = _normalize_k_values(args.k_values)
    evidence_index, _average_seconds = _load_evidence_index(evidence_root)
    dirpaths = discover_cases(data_root)
    if args.limit is not None:
        dirpaths = dirpaths[: max(args.limit, 0)]

    records: List[Dict[str, Any]] = []
    skipped_no_ground_truth: List[str] = []
    errors: List[Dict[str, str]] = []
    for index, dirpath in enumerate(dirpaths, 1):
        try:
            record = evaluate_case(
                dirpath=dirpath,
                data_root=data_root,
                evidence_root=evidence_root,
                evidence_index=evidence_index,
                weight_file=args.weight_file,
                directed=not args.undirected,
            )
        except Exception as exc:
            if not args.continue_on_error:
                raise RuntimeError(f"failed to evaluate {dirpath}") from exc
            errors.append({"dir": dirpath, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if record is None:
            skipped_no_ground_truth.append(dirpath)
        else:
            records.append(record)
        if index % 20 == 0 or index == len(dirpaths):
            print(f"[topk-recall] processed {index}/{len(dirpaths)} cases")

    summary = summarize_recall(records, k_values)
    summary.update(
        {
            "data_root": data_root,
            "evidence_root": str(evidence_root),
            "ranking_definitions": {
                "pagerank": "all devices sorted by normalized PageRank score",
                "pagerank+temporal": (
                    "all devices sorted by "
                    "(pagerank_score + normalized_raw_temporal_score) / 2"
                ),
            },
            "discovered_case_count": len(dirpaths),
            "skipped_no_ground_truth_count": len(skipped_no_ground_truth),
            "error_count": len(errors),
            "skipped_no_ground_truth": skipped_no_ground_truth,
            "errors": errors,
        }
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    _save_json(summary, output_dir / "topk_recall.json")
    _write_csv(_summary_csv_rows(summary), output_dir / "topk_recall.csv")
    _write_csv(_case_csv_rows(records, k_values), output_dir / "per_case.csv")
    _write_csv(_miss_csv_rows(records, k_values), output_dir / "misses.csv")
    _write_jsonl(records, output_dir / "case_rankings.jsonl")

    for row in _summary_csv_rows(summary):
        print(
            f"{row['strategy']:>20}  k={row['k']:>2}  "
            f"recall={row['recall']:.6f}  "
            f"hits={row['hit_count']}/{row['evaluated_case_count']}"
        )
    print(f"[topk-recall] outputs: {output_dir}")


if __name__ == "__main__":
    main()
