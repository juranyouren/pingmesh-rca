from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Any, Dict, List, Mapping


if __package__ in (None, ""):
    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)


from Sys.RootCauseAnalyze.propagation.equivalence import build_structural_equivalence
from Sys.RootCauseAnalyze.propagation.episodes import build_evidence_episodes
from Sys.RootCauseAnalyze.propagation.topology_context import load_topology_context
from Sys.utils.case_utils import (
    find_full_link_file,
    load_case_info,
    load_case_nodes,
)
from Sys.utils.io_utils import save_json


OUTPUT_FILENAME = "topology_equivalence.json"
REPORT_SCHEMA_VERSION = "topology-structural-equivalence-report-v1"


def discover_case_dirs(cases_root: str) -> List[str]:
    result: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(cases_root):
        if "info.json" in filenames and find_full_link_file(dirpath, filenames):
            result.append(os.path.abspath(dirpath))
    return sorted(result)


def process_case(
    dirpath: str,
    *,
    write: bool,
    require_raw_topology: bool,
) -> Dict[str, Any]:
    nodes = load_case_nodes(dirpath)
    info = load_case_info(dirpath)
    if not nodes or not info:
        raise ValueError("missing nodes or info")
    episodes = build_evidence_episodes(nodes, info)
    topology = load_topology_context(dirpath, node_list=nodes, info=info)
    topology_source = str(
        topology.get("diagnostics", {}).get("source", "unknown") or "unknown"
    )
    if require_raw_topology and topology_source != "raw_task_topo":
        raise ValueError(f"raw task_topo is required, got {topology_source}")
    equivalence = build_structural_equivalence(topology, episodes)
    output_path = os.path.join(dirpath, OUTPUT_FILENAME)
    if write:
        save_json(equivalence, output_path, indent=2)
    diagnostics = equivalence.get("diagnostics", {})
    return {
        "case_id": os.path.basename(os.path.normpath(dirpath)),
        "dir": os.path.abspath(dirpath),
        "topology_source": topology_source,
        "output": os.path.abspath(output_path) if write else None,
        "cluster_count": int(diagnostics.get("cluster_count", 0) or 0),
        "aggregated_member_count": int(
            diagnostics.get("aggregated_member_count", 0) or 0
        ),
        "raw_node_count": int(diagnostics.get("raw_node_count", 0) or 0),
        "quotient_node_count": int(diagnostics.get("quotient_node_count", 0) or 0),
        "raw_edge_count": int(diagnostics.get("raw_edge_count", 0) or 0),
        "quotient_edge_count": int(diagnostics.get("quotient_edge_count", 0) or 0),
    }


def build_report(rows: List[Mapping[str, Any]], errors: List[Mapping[str, Any]]) -> Dict[str, Any]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts["processed_cases"] += 1
        if int(row.get("cluster_count", 0) or 0) > 0:
            counts["cases_with_aggregation"] += 1
        counts["cluster_count"] += int(row.get("cluster_count", 0) or 0)
        counts["aggregated_member_count"] += int(
            row.get("aggregated_member_count", 0) or 0
        )
        counts["raw_node_count"] += int(row.get("raw_node_count", 0) or 0)
        counts["quotient_node_count"] += int(
            row.get("quotient_node_count", 0) or 0
        )
        counts["raw_edge_count"] += int(row.get("raw_edge_count", 0) or 0)
        counts["quotient_edge_count"] += int(
            row.get("quotient_edge_count", 0) or 0
        )
    counts["failed_cases"] = len(errors)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "summary": dict(sorted(counts.items())),
        "cases": list(rows),
        "errors": list(errors),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build label-free structural-equivalence sidecars for evidence-free "
            "parallel topology nodes."
        )
    )
    parser.add_argument("--cases-root", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"Write {OUTPUT_FILENAME} into every successfully processed case.",
    )
    parser.add_argument(
        "--require-raw-topology",
        action="store_true",
        help="Reject processed-node fallback topology contexts.",
    )
    args = parser.parse_args()

    rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for dirpath in discover_case_dirs(args.cases_root):
        try:
            rows.append(
                process_case(
                    dirpath,
                    write=args.write,
                    require_raw_topology=args.require_raw_topology,
                )
            )
        except Exception as exc:
            errors.append(
                {
                    "case_id": os.path.basename(os.path.normpath(dirpath)),
                    "dir": os.path.abspath(dirpath),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    report = build_report(rows, errors)
    save_json(report, args.report, indent=2)
    print(report["summary"])
    print(f"Report: {os.path.abspath(args.report)}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
