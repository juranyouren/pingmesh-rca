from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import replace
from typing import Any, Dict, List, Mapping, Sequence

if __package__ in (None, ""):
    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

from Sys.RootCauseAnalyze.propagation import PropagationConfig, reconstruct_propagation
from Sys.RootCauseAnalyze.propagation.artifacts import (
    SELECTED_PATHS_FILENAME,
    build_selected_path_record,
    build_selected_path_ref,
    compact_propagation,
)
from Sys.RootCauseAnalyze.propagation.topology_context import load_topology_context
from Sys.RootCauseAnalyze.stage1.fusion import rank_root_causes
from Sys.utils.case_utils import find_full_link_file, load_case_info, load_case_nodes
from Sys.utils.io_utils import load_json, save_json


def _discover_case_dirs(data_root: str) -> List[str]:
    result = []
    for dirpath, _dirnames, filenames in os.walk(data_root):
        if "info.json" in filenames and find_full_link_file(dirpath, filenames):
            result.append(dirpath)
    return sorted(result)


def _existing_result_map(path: str | None) -> Dict[str, Dict[str, Any]]:
    if not path:
        return {}
    raw = load_json(path, default=[])
    if not isinstance(raw, list):
        raise ValueError("root result file must contain a JSON list")
    return {
        os.path.normpath(str(item.get("dir"))): dict(item)
        for item in raw
        if isinstance(item, Mapping) and item.get("dir")
    }


def _edge_model_manifest(path: str | None) -> Dict[str, Any]:
    if not path:
        return {}
    payload = load_json(path, default=None)
    if not isinstance(payload, Mapping):
        raise ValueError("edge probability OOF manifest must contain a JSON object")
    if payload.get("schema_version") != "stage2-edge-classifier-oof-manifest-v1":
        raise ValueError("unsupported edge probability OOF manifest schema")
    return dict(payload)


def _edge_model_for_case(manifest: Mapping[str, Any], dirpath: str) -> str | None:
    case_models = manifest.get("case_models", {})
    if isinstance(case_models, Mapping):
        normalized = os.path.normcase(os.path.normpath(os.path.abspath(dirpath)))
        for raw_path, model_path in case_models.items():
            candidate = os.path.normcase(os.path.normpath(os.path.abspath(str(raw_path))))
            if candidate == normalized and model_path:
                return str(model_path)
    case_id_models = manifest.get("case_id_models", {})
    case_id = os.path.basename(os.path.normpath(dirpath))
    if isinstance(case_id_models, Mapping) and case_id_models.get(case_id):
        return str(case_id_models[case_id])
    return None


def _rankings_from_record(record: Mapping[str, Any] | None) -> List[Dict[str, Any]]:
    if not record:
        return []
    initial = record.get("initial_root_rankings")
    if isinstance(initial, list):
        canonical = [dict(item) for item in initial if isinstance(item, Mapping)]
        if canonical:
            return canonical
    stage1 = record.get("stage1")
    if isinstance(stage1, Mapping) and isinstance(stage1.get("root_rankings"), list):
        canonical = [
            dict(item) for item in stage1["root_rankings"] if isinstance(item, Mapping)
        ]
        if canonical:
            return canonical
    response = record.get("response")
    if isinstance(response, str) and response.strip():
        blocks = re.findall(r"```json\s*(\{.*?\})\s*```", response, flags=re.I | re.S)
        for block in reversed(blocks):
            try:
                payload = json.loads(block)
            except (TypeError, ValueError):
                continue
            values = payload.get("ip", []) if isinstance(payload, Mapping) else []
            if isinstance(values, str):
                values = [values]
            if isinstance(values, list):
                final_ips = [value for value in values if isinstance(value, str) and value]
                if final_ips:
                    return [
                        {"rank": index, "ip": ip, "combined_score": 1.0 / index}
                        for index, ip in enumerate(dict.fromkeys(final_ips), 1)
                    ]
    return []


def run_propagation_pipeline(
    data_root: str,
    output_dir: str,
    *,
    root_results_path: str | None = None,
    top_k: int = 3,
    weight_path: str | None = None,
    config: PropagationConfig | None = None,
    edge_probability_oof_manifest_path: str | None = None,
) -> str:
    """Run Stage 1 followed by Stage 2/M1 and Stage 2/M2 without labels."""

    cfg = config or PropagationConfig(root_top_k=top_k)
    edge_manifest = _edge_model_manifest(edge_probability_oof_manifest_path)
    previous = _existing_result_map(root_results_path)
    case_dirs = sorted(previous) if previous else _discover_case_dirs(data_root)
    case_ids = [os.path.basename(os.path.normpath(path)) for path in case_dirs]
    duplicate_case_ids = sorted(
        {case_id for case_id in case_ids if case_ids.count(case_id) > 1}
    )
    if duplicate_case_ids:
        raise ValueError(
            "duplicate case directory names are incompatible with propagation-labeler: "
            + ", ".join(duplicate_case_ids)
        )
    records = []
    selected_path_records = []
    started = time.time()

    for dirpath in case_dirs:
        try:
            nodes = load_case_nodes(dirpath)
            info = load_case_info(dirpath)
            if not nodes or not info:
                raise ValueError("missing nodes or info")
            previous_record = previous.get(os.path.normpath(dirpath))
            rankings = _rankings_from_record(previous_record)
            if not rankings and previous_record is None:
                predicted_ips, details = rank_root_causes(
                    nodes,
                    info,
                    dirpath=dirpath,
                    ranker_ids=(1, 2),
                    directed=True,
                    weight_dirpath=weight_path,
                    top_k=top_k,
                )
                rankings = details.get("combined", {}).get("topk", [])
                if not rankings:
                    rankings = [
                        {"rank": index, "ip": ip, "combined_score": 1.0 / index}
                        for index, ip in enumerate(predicted_ips, 1)
                    ]
            topology_context = load_topology_context(dirpath, node_list=nodes, info=info)
            case_config = cfg
            if edge_manifest:
                model_path = _edge_model_for_case(edge_manifest, dirpath)
                if not model_path:
                    raise ValueError(f"OOF edge classifier model missing for case: {dirpath}")
                case_config = replace(
                    cfg,
                    edge_probability_method="supervised_softmax_v1",
                    edge_probability_model_path=model_path,
                )
            propagation = reconstruct_propagation(
                nodes=nodes,
                info=info,
                topology_context=topology_context,
                root_rankings=rankings,
                config=case_config,
            )
            final_ips = [
                str(item.get("ip"))
                for item in propagation.get("final_root_rankings", [])
                if isinstance(item, Mapping) and item.get("ip")
            ]
            score_response = json.dumps(
                {
                    "reasoning": "Stage 2 propagation-constrained root reranking.",
                    "ip": final_ips,
                },
                ensure_ascii=False,
                indent=2,
            )
            selected_path_records.append(
                build_selected_path_record(dirpath, propagation)
            )
            records.append(
                {
                    "dir": dirpath,
                    "root_ips": [
                        str(item.get("ip"))
                        for item in rankings[:top_k]
                        if isinstance(item, Mapping) and item.get("ip")
                    ],
                    "initial_root_rankings": propagation["initial_root_rankings"],
                    "final_root_rankings": propagation["final_root_rankings"],
                    "selected_root": propagation["selected_root"],
                    "ranked_ips": final_ips,
                    "response": f"```json\n{score_response}\n```",
                    "selected_path_ref": build_selected_path_ref(dirpath),
                    "propagation": compact_propagation(propagation),
                }
            )
        except Exception as exc:
            records.append(
                {
                    "dir": dirpath,
                    "root_ips": [],
                    "propagation": None,
                    "selected_path_ref": None,
                    "error": str(exc),
                }
            )

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "res.json")
    selected_paths_path = os.path.join(output_dir, SELECTED_PATHS_FILENAME)
    save_json(selected_path_records, selected_paths_path, indent=2)
    save_json(records, output_path, indent=2)
    print(
        f"Propagation pipeline: {len(records)} cases in {time.time() - started:.2f}s; "
        f"result={output_path}; selected_paths={selected_paths_path}"
    )
    return output_path


def main() -> None:
    try:
        from Sys.config import config as project_config

        default_data_root = project_config.data.nodes_labeled
        default_result_root = project_config.data.results
        default_weight_path = project_config.data.alarm_weights
    except Exception:
        default_data_root = "data/node/nodes_max_labeled"
        default_result_root = "data/res"
        default_weight_path = None

    parser = argparse.ArgumentParser(description="Run deterministic Stage 1 -> Stage 2 pipeline.")
    parser.add_argument("--data-root", "-d", default=default_data_root)
    parser.add_argument("--output-dir", "-o", default=None)
    parser.add_argument("--root-results", default=None, help="Optional existing RCA res.json.")
    parser.add_argument("--top-k", "-k", type=int, default=3)
    parser.add_argument("--weight-file", "-w", default=default_weight_path)
    parser.add_argument("--max-candidate-nodes", type=int, default=80)
    parser.add_argument("--max-path-depth", type=int, default=8)
    parser.add_argument(
        "--stage1-weight",
        type=float,
        default=0.5,
        help="Weight of normalized Stage 1 evidence in final reranking.",
    )
    parser.add_argument(
        "--edge-probability-method",
        choices=(
            "deterministic_evidence_v1",
            "logit_softmax_v1",
            "supervised_softmax_v1",
        ),
        default="deterministic_evidence_v1",
    )
    parser.add_argument("--edge-probability-model", default=None)
    parser.add_argument("--edge-probability-oof-manifest", default=None)
    parser.add_argument("--edge-probability-temperature", type=float, default=1.0)
    parser.add_argument("--logit-direction-bias", type=float, default=-1.50)
    parser.add_argument("--logit-temporal-weight", type=float, default=1.50)
    parser.add_argument("--logit-semantic-weight", type=float, default=2.00)
    parser.add_argument("--logit-direct-weight", type=float, default=1.50)
    parser.add_argument("--logit-contradiction-weight", type=float, default=2.00)
    parser.add_argument("--logit-no-direct-bias", type=float, default=-0.25)
    parser.add_argument("--logit-inactive-weight", type=float, default=2.50)
    parser.add_argument("--logit-missing-relation-weight", type=float, default=0.50)
    parser.add_argument("--logit-routing-convergence-bias", type=float, default=0.25)
    parser.add_argument("--logit-physical-link-bias", type=float, default=0.00)
    parser.add_argument("--logit-inferred-impact-bias", type=float, default=-0.25)
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(default_result_root, f"propagation_{int(time.time())}")
    run_propagation_pipeline(
        args.data_root,
        output_dir,
        root_results_path=args.root_results,
        top_k=args.top_k,
        weight_path=args.weight_file,
        edge_probability_oof_manifest_path=args.edge_probability_oof_manifest,
        config=PropagationConfig(
            root_top_k=args.top_k,
            max_candidate_nodes=args.max_candidate_nodes,
            max_path_depth=args.max_path_depth,
            stage1_weight=args.stage1_weight,
            edge_probability_method=args.edge_probability_method,
            edge_probability_model_path=args.edge_probability_model,
            edge_probability_temperature=args.edge_probability_temperature,
            logit_direction_bias=args.logit_direction_bias,
            logit_temporal_weight=args.logit_temporal_weight,
            logit_semantic_weight=args.logit_semantic_weight,
            logit_direct_weight=args.logit_direct_weight,
            logit_contradiction_weight=args.logit_contradiction_weight,
            logit_no_direct_bias=args.logit_no_direct_bias,
            logit_inactive_weight=args.logit_inactive_weight,
            logit_missing_relation_weight=args.logit_missing_relation_weight,
            logit_routing_convergence_bias=args.logit_routing_convergence_bias,
            logit_physical_link_bias=args.logit_physical_link_bias,
            logit_inferred_impact_bias=args.logit_inferred_impact_bias,
        ),
    )


if __name__ == "__main__":
    main()
