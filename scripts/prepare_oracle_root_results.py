"""Prepare label-assisted root-ranking files for controlled oracle evaluation.

This script does not run inference and must not be used for paper OOF metrics.
It only reorders an existing Stage-1 result file after reading the case root
label, producing two evaluation-only variants:

* candidate_oracle: promote the true root only when it is already in the
  supplied ranking; misses remain misses.
* direct_oracle: insert/promote the true root for every case; this isolates the
  graph-reconstruction ceiling when root selection is perfect.
"""

from __future__ import annotations

import argparse
import copy
import os
from typing import Any, Dict, List, Mapping

from Sys.RootCauseAnalyze.stage1.neural_graph import load_training_label
from Sys.utils.io_utils import load_json, save_json


def _rankings(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in ("initial_root_rankings", "reranked_root_rankings"):
        value = record.get(key)
        if isinstance(value, list):
            rows = [dict(item) for item in value if isinstance(item, Mapping)]
            if rows:
                return rows
    stage1 = record.get("stage1")
    if isinstance(stage1, Mapping) and isinstance(stage1.get("root_rankings"), list):
        return [dict(item) for item in stage1["root_rankings"] if isinstance(item, Mapping)]
    return []


def _ip(row: Mapping[str, Any]) -> str:
    return str(row.get("ip", row.get("device_id", "")) or "")


def _promote(rows: List[Dict[str, Any]], truth: str, *, insert: bool) -> tuple[List[Dict[str, Any]], bool]:
    matching = [row for row in rows if _ip(row) == truth]
    if not matching and not insert:
        return rows, False
    selected = matching[0] if matching else {"ip": truth, "combined_score": 1.0}
    ordered = [selected] + [row for row in rows if _ip(row) and _ip(row) != truth]
    for index, row in enumerate(ordered, 1):
        row["rank"] = index
    return ordered, bool(matching)


def build(input_path: str, output_path: str, *, insert_missing: bool) -> Dict[str, int]:
    records = load_json(input_path, default=None)
    if not isinstance(records, list):
        raise ValueError(f"root result must be a JSON list: {input_path}")
    output: List[Dict[str, Any]] = []
    labeled = 0
    in_candidates = 0
    promoted = 0
    missing_label = 0
    for raw in records:
        if not isinstance(raw, Mapping):
            continue
        record = copy.deepcopy(dict(raw))
        case_dir = str(record.get("dir", "") or "")
        truth = load_training_label(case_dir) if case_dir else ""
        rows = _rankings(record)
        if truth:
            labeled += 1
            reordered, was_in_candidates = _promote(rows, truth, insert=insert_missing)
            in_candidates += int(was_in_candidates)
            promoted += int(bool(reordered) and _ip(reordered[0]) == truth)
            record["initial_root_rankings"] = reordered
            record["ranked_ips"] = [_ip(row) for row in reordered if _ip(row)]
            record["root_ips"] = record["ranked_ips"]
            record["_oracle_evaluation_only"] = True
            record["_oracle_root_in_original_ranking"] = was_in_candidates
        else:
            missing_label += 1
        output.append(record)
    save_json(output, output_path, indent=2)
    return {
        "input_cases": len(records),
        "output_cases": len(output),
        "labeled_cases": labeled,
        "truth_in_original_ranking": in_candidates,
        "truth_promoted_to_rank1": promoted,
        "missing_labels": missing_label,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-results", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    for name, insert_missing in (("candidate_oracle", False), ("direct_oracle", True)):
        output = os.path.join(args.output_dir, f"{name}.json")
        stats = build(args.root_results, output, insert_missing=insert_missing)
        print(name, stats)


if __name__ == "__main__":
    main()
