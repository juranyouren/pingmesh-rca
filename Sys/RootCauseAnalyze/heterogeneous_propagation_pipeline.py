from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Dict, List, Mapping, Sequence

if __package__ in (None, ""):
    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

from Sys.RootCauseAnalyze.propagation import PropagationConfig
from Sys.RootCauseAnalyze.propagation.heterogeneous import (
    HeterogeneousConfig,
    reconstruct_heterogeneous_propagation,
)
from Sys.RootCauseAnalyze.propagation.topology_context import load_topology_context
from Sys.utils.case_utils import find_full_link_file, load_case_info, load_case_nodes
from Sys.utils.io_utils import save_json


RESULT_FILENAME = "res.json"
GRAPH_FILENAME = "heterogeneous_graphs.json"


def _discover_case_dirs(data_root: str) -> List[str]:
    result = []
    for dirpath, _dirnames, filenames in os.walk(data_root):
        if "info.json" in filenames and find_full_link_file(dirpath, filenames):
            result.append(dirpath)
    return sorted(result)


def _compact_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    reconstruction = result.get("m3_reconstruction", {})
    return {
        "schema_version": result.get("schema_version"),
        "method": result.get("method"),
        "selected_root": result.get("selected_root"),
        "root_input_required": result.get("root_input_required", False),
        "summary": dict(result.get("summary", {})),
        "identifiability": (
            dict(reconstruction.get("identifiability", {}))
            if isinstance(reconstruction, Mapping)
            else {}
        ),
        "limitations": list(result.get("limitations", [])),
        "heterogeneous_config_version": result.get(
            "heterogeneous_config_version"
        ),
        "propagation_config_version": result.get("propagation_config_version"),
    }


def run_heterogeneous_propagation_pipeline(
    case_dirs: Sequence[str],
    output_dir: str,
    *,
    propagation_config: PropagationConfig | None = None,
    heterogeneous_config: HeterogeneousConfig | None = None,
) -> str:
    """Run V0 without reading root results or label files."""

    pcfg = propagation_config or PropagationConfig()
    hcfg = heterogeneous_config or HeterogeneousConfig()
    normalized_dirs = sorted(
        {os.path.abspath(os.path.normpath(path)) for path in case_dirs if path}
    )
    case_ids = [os.path.basename(path) for path in normalized_dirs]
    duplicate_ids = sorted(
        {case_id for case_id in case_ids if case_ids.count(case_id) > 1}
    )
    if duplicate_ids:
        raise ValueError("duplicate case directory names: " + ", ".join(duplicate_ids))

    records: List[Dict[str, Any]] = []
    graphs: List[Dict[str, Any]] = []
    started = time.time()
    for dirpath in normalized_dirs:
        case_id = os.path.basename(dirpath)
        try:
            nodes = load_case_nodes(dirpath)
            info = load_case_info(dirpath)
            if not nodes or not info:
                raise ValueError("missing nodes or info")
            topology_context = load_topology_context(
                dirpath,
                node_list=nodes,
                info=info,
            )
            result = reconstruct_heterogeneous_propagation(
                nodes=nodes,
                info=info,
                topology_context=topology_context,
                propagation_config=pcfg,
                heterogeneous_config=hcfg,
            )
            graph_record = {
                "case_id": case_id,
                "dir": dirpath,
                "result": result,
            }
            graphs.append(graph_record)
            records.append(
                {
                    "case_id": case_id,
                    "dir": dirpath,
                    **_compact_result(result),
                    "graph_ref": {
                        "artifact": GRAPH_FILENAME,
                        "case_id": case_id,
                    },
                }
            )
        except Exception as exc:
            records.append(
                {
                    "case_id": case_id,
                    "dir": dirpath,
                    "selected_root": None,
                    "error": str(exc),
                }
            )

    os.makedirs(output_dir, exist_ok=True)
    result_path = os.path.join(output_dir, RESULT_FILENAME)
    graph_path = os.path.join(output_dir, GRAPH_FILENAME)
    save_json(records, result_path, indent=2)
    save_json(graphs, graph_path, indent=2)
    successes = sum(1 for item in records if "error" not in item)
    print(
        f"Heterogeneous propagation V0: {successes}/{len(records)} cases "
        f"in {time.time() - started:.2f}s; result={result_path}; graphs={graph_path}"
    )
    return result_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the label-free heterogeneous root and fault-propagation V0 baseline."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--case-dir", action="append", default=None)
    source.add_argument("--data-root", default=None)
    parser.add_argument("--output-dir", "-o", required=True)
    parser.add_argument("--max-candidate-nodes", type=int, default=80)
    parser.add_argument("--max-root-candidates", type=int, default=12)
    parser.add_argument("--max-events-per-device", type=int, default=8)
    parser.add_argument("--max-event-pairs", type=int, default=500)
    parser.add_argument(
        "--edge-probability-method",
        choices=(
            "deterministic_evidence_v1",
            "logit_softmax_v1",
        ),
        default="deterministic_evidence_v1",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    case_dirs = args.case_dir or _discover_case_dirs(args.data_root)
    if not case_dirs:
        raise SystemExit("no case directories found")
    pcfg = PropagationConfig(
        root_top_k=args.max_root_candidates,
        max_candidate_nodes=args.max_candidate_nodes,
        edge_probability_method=args.edge_probability_method,
    )
    hcfg = HeterogeneousConfig(
        max_root_candidates=args.max_root_candidates,
        max_events_per_device=args.max_events_per_device,
        max_event_pairs=args.max_event_pairs,
    )
    run_heterogeneous_propagation_pipeline(
        case_dirs,
        args.output_dir,
        propagation_config=pcfg,
        heterogeneous_config=hcfg,
    )


if __name__ == "__main__":
    main()
