from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Mapping, Sequence

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.RootCauseAnalyze.propagation.m1 import reconstruct_hypothesis_graph
from Sys.RootCauseAnalyze.propagation.m2 import infer_root_paths
from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig
from Sys.RootCauseAnalyze.propagation.topology_context import load_topology_context
from Sys.RootCauseAnalyze.stage1.neural_graph import (
    RawCase,
    grouped_kfold_indices,
    load_raw_cases,
)
from Sys.RootCauseAnalyze.stage1.neural_model import resolve_device
from Sys.RootCauseAnalyze.stage1.propagation_reranker import (
    RerankerExample,
    RerankerModelConfig,
    RerankerTrainingConfig,
    evaluate_reranker,
    extract_candidate_rows,
    load_checkpoint,
    predict_example,
    save_checkpoint,
    serialize_examples,
    train_reranker,
)
from Sys.utils.io_utils import load_json, save_json


MODEL_NAME = "PC-STGR-PGR"
MODEL_VERSION = "propagation-statistical-listwise-reranker-v1"
_HYPOTHESIS_GRAPH_CACHE: Dict[tuple[str, str], Dict[str, Any]] = {}


def _normalized_path(value: Any) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(value or ""))))


def _root_result_map(path: str) -> Dict[str, Dict[str, Any]]:
    records = load_json(path, default=None)
    if not isinstance(records, list):
        raise ValueError("root result file must contain a JSON list")
    result: Dict[str, Dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, Mapping) or not raw.get("dir"):
            continue
        key = _normalized_path(raw.get("dir"))
        if key in result:
            raise ValueError(f"duplicate root result path: {raw.get('dir')}")
        result[key] = dict(raw)
    return result


def _stage1_fold_training_result(root_results_path: str, fold_number: int) -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(root_results_path)),
        "folds",
        f"fold_{fold_number}_train_res.json",
    )


def _stage1_final_training_result(root_results_path: str) -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(root_results_path)),
        "final_train_res.json",
    )


def _root_rankings(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for raw in (
        record.get("reranked_root_rankings"),
        record.get("initial_root_rankings"),
        record.get("stage1", {}).get("root_rankings", {})
        if isinstance(record.get("stage1", {}), Mapping)
        else None,
    ):
        if isinstance(raw, list):
            rankings = [dict(item) for item in raw if isinstance(item, Mapping)]
            if rankings:
                return rankings
    return []


def _propagation_config(args: argparse.Namespace) -> PropagationConfig:
    return PropagationConfig(
        root_top_k=max(1, int(args.top_k)),
        max_candidate_nodes=max(1, int(args.max_candidate_nodes)),
        max_path_depth=max(1, int(args.max_path_depth)),
        stage1_weight=1.0,
        edge_probability_method=args.edge_probability_method,
    )


def build_reranker_examples(
    cases: Sequence[RawCase],
    root_records: Mapping[str, Mapping[str, Any]],
    *,
    propagation_config: PropagationConfig,
    require_all_records: bool = True,
) -> List[RerankerExample]:
    """Generate candidate DAG statistics; propagation code never receives labels."""

    examples: List[RerankerExample] = []
    for index, case in enumerate(cases, 1):
        record = root_records.get(_normalized_path(case.dirpath))
        if record is None:
            if require_all_records:
                raise ValueError(f"root result is missing for case: {case.dirpath}")
            continue
        rankings = _root_rankings(record)[: propagation_config.root_top_k]
        if not rankings:
            raise ValueError(f"root rankings are empty for case: {case.dirpath}")
        graph_cache_key = (
            _normalized_path(case.dirpath),
            json.dumps(
                propagation_config.to_dict(), ensure_ascii=False, sort_keys=True
            ),
        )
        hypothesis_graph = _HYPOTHESIS_GRAPH_CACHE.get(graph_cache_key)
        if hypothesis_graph is None:
            topology_context = load_topology_context(
                case.dirpath, node_list=case.nodes, info=case.info
            )
            hypothesis_graph = reconstruct_hypothesis_graph(
                nodes=case.nodes,
                info=case.info,
                topology_context=topology_context,
                config=propagation_config,
            )
            _HYPOTHESIS_GRAPH_CACHE[graph_cache_key] = hypothesis_graph
        inference = infer_root_paths(
            hypothesis_graph=hypothesis_graph,
            initial_root_rankings=rankings,
            config=propagation_config,
        )
        candidates = extract_candidate_rows(
            hypothesis_graph=hypothesis_graph,
            root_conditioned_graphs=inference.get(
                "root_conditioned_propagation_graphs", []
            ),
            initial_root_rankings=rankings,
        )
        examples.append(
            RerankerExample(
                dirpath=case.dirpath,
                gt_ip=case.gt_ip,
                candidates=candidates,
                diagnostics={
                    "candidate_count": len(candidates),
                    "candidate_recall": bool(
                        case.gt_ip
                        and any(row.get("ip") == case.gt_ip for row in candidates)
                    ),
                    "edge_probability_method": propagation_config.edge_probability_method,
                    "hypothesis_summary": dict(
                        hypothesis_graph.get("summary", {})
                    ),
                },
            )
        )
        if index % 20 == 0:
            print(f"Propagation feature extraction: {index}/{len(cases)}")
    return examples


def _response(rankings: Sequence[Mapping[str, Any]], reason: str) -> str:
    payload = {
        "reasoning": reason,
        "ip": [str(item.get("ip")) for item in rankings if item.get("ip")],
    }
    return f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"


def _result_record(
    base_record: Mapping[str, Any],
    rankings: Sequence[Mapping[str, Any]],
    *,
    evaluation_mode: str,
    fold: int | None = None,
) -> Dict[str, Any]:
    final_rankings = [dict(item) for item in rankings]
    original = _root_rankings(base_record)
    reason = f"{MODEL_NAME} ({MODEL_VERSION}); evaluation_mode={evaluation_mode}."
    metadata: Dict[str, Any] = {
        "method": MODEL_VERSION,
        "model_name": MODEL_NAME,
        "evaluation_mode": evaluation_mode,
        "candidate_count": len(final_rankings),
    }
    if fold is not None:
        metadata["fold"] = int(fold)
    stage1 = (
        dict(base_record.get("stage1", {}))
        if isinstance(base_record.get("stage1", {}), Mapping)
        else {}
    )
    stage1["base_root_rankings"] = original
    stage1["root_rankings"] = final_rankings
    stage1["propagation_reranker"] = metadata
    response = _response(final_rankings, reason)
    return {
        **dict(base_record),
        "prompt": "PC_STGR_PROPAGATION_STATISTICAL_LISTWISE_RERANKER",
        "draft_response": response,
        "response": response,
        "ranked_ips": [str(item["ip"]) for item in final_rankings if item.get("ip")],
        "base_root_rankings": original,
        "initial_root_rankings": original,
        "reranked_root_rankings": final_rankings,
        "final_root_rankings": final_rankings,
        "stage1": stage1,
        "root_reranker": metadata,
        "gt_ips": [],
    }


def _ranking_audit(
    examples: Sequence[RerankerExample],
    rankings_by_path: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Dict[str, Any]:
    labeled = [example for example in examples if example.gt_ip]
    if not labeled:
        return {"case_count": 0}
    candidate_hits = 0
    initial_top1 = 0
    final_hits = {1: 0, 3: 0, 5: 0}
    mrr = 0.0
    corrections = 0
    corruptions = 0
    nll = 0.0
    brier = 0.0
    probability_cases = 0
    for example in labeled:
        gt = str(example.gt_ip)
        initial_ips = [str(row.get("ip", "")) for row in example.candidates]
        rankings = rankings_by_path.get(_normalized_path(example.dirpath), [])
        final_ips = [str(row.get("ip", "")) for row in rankings]
        initial_correct = bool(initial_ips and initial_ips[0] == gt)
        final_correct = bool(final_ips and final_ips[0] == gt)
        initial_top1 += int(initial_correct)
        candidate_hits += int(gt in initial_ips)
        corrections += int(not initial_correct and final_correct)
        corruptions += int(initial_correct and not final_correct)
        if gt in final_ips:
            rank = final_ips.index(gt) + 1
            mrr += 1.0 / rank
            for k in final_hits:
                final_hits[k] += int(rank <= k)
            probabilities = [
                max(0.0, float(row.get("combined_score", 0.0) or 0.0))
                for row in rankings
            ]
            total_probability = sum(probabilities)
            if total_probability > 0.0:
                probabilities = [value / total_probability for value in probabilities]
                gt_probability = probabilities[rank - 1]
                nll += -math.log(max(gt_probability, 1e-12))
                brier += sum(
                    (value - float(index == rank - 1)) ** 2
                    for index, value in enumerate(probabilities)
                ) / len(probabilities)
                probability_cases += 1
    total = len(labeled)
    return {
        "case_count": total,
        "candidate_recall": round(candidate_hits / total, 6),
        "initial_top1": round(initial_top1 / total, 6),
        "final_top1": round(final_hits[1] / total, 6),
        "final_top3": round(final_hits[3] / total, 6),
        "final_top5": round(final_hits[5] / total, 6),
        "mrr": round(mrr / total, 6),
        "conditional_top1": (
            round(final_hits[1] / candidate_hits, 6) if candidate_hits else 0.0
        ),
        "corrections": corrections,
        "corruptions": corruptions,
        "net_corrections": corrections - corruptions,
        "conditional_nll": (
            round(nll / probability_cases, 6) if probability_cases else 0.0
        ),
        "conditional_brier": (
            round(brier / probability_cases, 6) if probability_cases else 0.0
        ),
    }


def _model_config(args: argparse.Namespace) -> RerankerModelConfig:
    return RerankerModelConfig(
        hidden_dim=args.hidden_dim,
        dropout=args.dropout,
        correction_scale=args.correction_scale,
        feature_set=args.feature_set,
    )


def _training_config(
    args: argparse.Namespace, *, seed: int | None = None
) -> RerankerTrainingConfig:
    return RerankerTrainingConfig(
        epochs=args.epochs,
        patience=args.patience,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        gradient_clip=args.gradient_clip,
        seed=args.seed if seed is None else seed,
    )


def _inner_train_dev(
    cases: Sequence[RawCase],
    examples: Sequence[RerankerExample],
    *,
    seed: int,
) -> tuple[List[RerankerExample], List[RerankerExample]]:
    if len(cases) < 3:
        return list(examples), []
    try:
        dev_indices = set(grouped_kfold_indices(cases, 5, seed)[0])
    except ValueError:
        return list(examples), []
    training = [example for index, example in enumerate(examples) if index not in dev_indices]
    validation = [example for index, example in enumerate(examples) if index in dev_indices]
    if not any(example.target_position is not None for example in validation):
        return list(examples), []
    return training, validation


def run_cross_validation(args: argparse.Namespace) -> str:
    started = time.time()
    device = resolve_device(args.device)
    cases = load_raw_cases(args.data_root, require_labels=True)
    if len(cases) < 2:
        raise ValueError("reranker cross-validation needs at least two labeled cases")
    root_records = _root_result_map(args.root_results)
    propagation_config = _propagation_config(args)
    examples = build_reranker_examples(
        cases, root_records, propagation_config=propagation_config
    )
    folds = grouped_kfold_indices(cases, args.folds, args.seed)
    model_config = _model_config(args)
    os.makedirs(args.output_dir, exist_ok=True)
    fold_dir = os.path.join(args.output_dir, "folds")
    os.makedirs(fold_dir, exist_ok=True)
    save_json(
        serialize_examples(examples),
        os.path.join(args.output_dir, "candidate_features.json"),
        indent=2,
    )

    all_indices = set(range(len(cases)))
    rankings_by_path: Dict[str, List[Dict[str, Any]]] = {}
    fold_summaries: List[Dict[str, Any]] = []
    histories: Dict[str, Any] = {}
    selected_epochs: List[int] = []
    fold_meta_feature_sources: List[str] = []

    for fold_number, validation_indices in enumerate(folds, 1):
        validation_set = set(validation_indices)
        training_indices = sorted(all_indices - validation_set)
        training_cases = [cases[index] for index in training_indices]
        validation_examples = [examples[index] for index in validation_indices]
        fold_training_result = _stage1_fold_training_result(
            args.root_results, fold_number
        )
        if os.path.isfile(fold_training_result):
            training_examples = build_reranker_examples(
                training_cases,
                _root_result_map(fold_training_result),
                propagation_config=propagation_config,
            )
            meta_feature_source = "outer_fold_stage1_training_predictions"
        else:
            training_examples = [examples[index] for index in training_indices]
            meta_feature_source = "global_oof_fallback"
            print(
                "[WARNING] fold-local Stage-1 training predictions are missing; "
                f"using global OOF meta-features for reranker fold {fold_number}: "
                f"{fold_training_result}"
            )
        fold_meta_feature_sources.append(meta_feature_source)
        inner_training, inner_validation = _inner_train_dev(
            training_cases,
            training_examples,
            seed=args.seed + fold_number,
        )
        training_config = _training_config(args, seed=args.seed + fold_number)
        if inner_validation:
            (
                _selection_model,
                _selection_mean,
                _selection_scale,
                best_epoch,
                selection_history,
            ) = train_reranker(
                inner_training,
                inner_validation,
                model_config=model_config,
                training_config=training_config,
                device=device,
            )
            del _selection_model
        else:
            best_epoch = max(1, int(args.epochs))
            selection_history = []
        model, feature_mean, feature_scale, _epoch, fit_history = train_reranker(
            training_examples,
            [],
            model_config=model_config,
            training_config=training_config,
            device=device,
            fixed_epochs=best_epoch,
        )
        selected_epochs.append(best_epoch)
        fold_metrics = evaluate_reranker(
            model,
            validation_examples,
            feature_mean,
            feature_scale,
            device,
        )
        checkpoint_path = os.path.join(fold_dir, f"fold_{fold_number}.pt")
        save_checkpoint(
            checkpoint_path,
            model=model,
            feature_mean=feature_mean,
            feature_scale=feature_scale,
            model_config=model_config,
            training_config=training_config,
            metadata={
                "model_name": MODEL_NAME,
                "model_version": MODEL_VERSION,
                "evaluation_mode": "out_of_fold",
                "fold": fold_number,
                "selected_epoch": best_epoch,
                "outer_train_case_count": len(training_examples),
                "outer_validation_case_count": len(validation_examples),
                "meta_feature_source": meta_feature_source,
                "metrics": fold_metrics,
            },
        )
        for example in validation_examples:
            rankings_by_path[_normalized_path(example.dirpath)] = predict_example(
                model, example, feature_mean, feature_scale, device
            )
        fold_summaries.append(
            {
                "fold": fold_number,
                "train_cases": len(training_examples),
                "validation_cases": len(validation_examples),
                "selected_epoch": best_epoch,
                "metrics": fold_metrics,
                "checkpoint": checkpoint_path,
                "meta_feature_source": meta_feature_source,
                "stage1_training_predictions": (
                    fold_training_result
                    if os.path.isfile(fold_training_result)
                    else None
                ),
            }
        )
        histories[str(fold_number)] = {
            "epoch_selection": selection_history,
            "outer_training": fit_history,
        }
        print(
            f"Reranker fold {fold_number}/{len(folds)}: "
            f"{json.dumps(fold_summaries[-1], ensure_ascii=False)}"
        )

    if len(rankings_by_path) != len(examples):
        raise RuntimeError("OOF reranker predictions are incomplete")
    fold_by_index = {
        case_index: fold_number
        for fold_number, indices in enumerate(folds, 1)
        for case_index in indices
    }
    output_records = []
    for case_index, case in enumerate(cases):
        key = _normalized_path(case.dirpath)
        output_records.append(
            _result_record(
                root_records[key],
                rankings_by_path[key],
                evaluation_mode="out_of_fold",
                fold=fold_by_index[case_index],
            )
        )
    result_path = os.path.join(args.output_dir, "res.json")
    save_json(output_records, result_path, indent=2)
    save_json(histories, os.path.join(args.output_dir, "training_history.json"), indent=2)

    final_epoch = max(1, int(statistics.median(selected_epochs)))
    final_training_config = _training_config(args, seed=args.seed + 10_000)
    final_stage1_training_result = _stage1_final_training_result(args.root_results)
    if os.path.isfile(final_stage1_training_result):
        final_training_examples = build_reranker_examples(
            cases,
            _root_result_map(final_stage1_training_result),
            propagation_config=propagation_config,
        )
        final_meta_feature_source = "full_stage1_training_predictions"
    else:
        final_training_examples = examples
        final_meta_feature_source = "global_oof_fallback"
        print(
            "[WARNING] final Stage-1 training predictions are missing; using "
            f"global OOF meta-features: {final_stage1_training_result}"
        )
    (
        final_model,
        final_mean,
        final_scale,
        _final_epoch,
        final_history,
    ) = train_reranker(
        final_training_examples,
        [],
        model_config=model_config,
        training_config=final_training_config,
        device=device,
        fixed_epochs=final_epoch,
    )
    final_checkpoint = os.path.join(args.output_dir, "final_model.pt")
    save_checkpoint(
        final_checkpoint,
        model=final_model,
        feature_mean=final_mean,
        feature_scale=final_scale,
        model_config=model_config,
        training_config=final_training_config,
        metadata={
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "evaluation_mode": "trained_on_full_stage1_meta_features",
            "train_case_count": len(final_training_examples),
            "epochs": final_epoch,
            "root_results": os.path.abspath(args.root_results),
            "meta_feature_source": final_meta_feature_source,
        },
    )
    oof_metrics = _ranking_audit(examples, rankings_by_path)
    summary = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "evaluation_mode": "out_of_fold",
        "case_count": len(examples),
        "fold_count": len(folds),
        "device": str(device),
        "elapsed_seconds": round(time.time() - started, 3),
        "root_results": os.path.abspath(args.root_results),
        "propagation_config": propagation_config.to_dict(),
        "model_config": model_config.to_dict(),
        "training_config": _training_config(args).to_dict(),
        "oof_metrics": oof_metrics,
        "meta_feature_protocol": (
            "fold_local_stage1_training_predictions"
            if set(fold_meta_feature_sources)
            == {"outer_fold_stage1_training_predictions"}
            else "contains_global_oof_fallback"
        ),
        "final_meta_feature_source": final_meta_feature_source,
        "folds": fold_summaries,
        "final_training_epochs": final_epoch,
        "final_training_history": final_history,
        "final_checkpoint": final_checkpoint,
        "oof_result": result_path,
        "candidate_features": os.path.join(
            args.output_dir, "candidate_features.json"
        ),
    }
    save_json(summary, os.path.join(args.output_dir, "training_summary.json"), indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return result_path


def run_inference(args: argparse.Namespace) -> str:
    device = resolve_device(args.device)
    model, payload = load_checkpoint(args.checkpoint, device)
    feature_mean = payload["feature_mean"]
    feature_scale = payload["feature_scale"]
    root_records = _root_result_map(args.root_results)
    discovered_cases = load_raw_cases(args.data_root, require_labels=False)
    cases = [
        case
        for case in discovered_cases
        if _normalized_path(case.dirpath) in root_records
    ]
    if len(cases) != len(root_records):
        discovered = {_normalized_path(case.dirpath) for case in discovered_cases}
        missing = sorted(set(root_records) - discovered)
        raise ValueError(
            "some root-result cases are absent from the data root: "
            + ", ".join(missing[:5])
        )
    examples = build_reranker_examples(
        cases,
        root_records,
        propagation_config=_propagation_config(args),
        require_all_records=True,
    )
    records = []
    for example in examples:
        key = _normalized_path(example.dirpath)
        rankings = predict_example(
            model, example, feature_mean, feature_scale, device
        )
        records.append(
            _result_record(
                root_records[key],
                rankings,
                evaluation_mode="checkpoint_inference",
            )
        )
    os.makedirs(args.output_dir, exist_ok=True)
    result_path = os.path.join(args.output_dir, "res.json")
    save_json(records, result_path, indent=2)
    save_json(
        {
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "evaluation_mode": "checkpoint_inference",
            "checkpoint": os.path.abspath(args.checkpoint),
            "root_results": os.path.abspath(args.root_results),
            "case_count": len(records),
            "result": result_path,
        },
        os.path.join(args.output_dir, "inference_summary.json"),
        indent=2,
    )
    return result_path


def _add_shared_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--root-results", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-candidate-nodes", type=int, default=80)
    parser.add_argument("--max-path-depth", type=int, default=8)
    parser.add_argument(
        "--edge-probability-method",
        choices=("deterministic_evidence_v1", "logit_softmax_v1"),
        default="deterministic_evidence_v1",
    )
    parser.add_argument("--device", default="auto")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Train or run the propagation-statistics listwise root reranker."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    crossval = subparsers.add_parser(
        "crossval", help="Generate grouped-OOF reranked root predictions."
    )
    _add_shared_args(crossval)
    crossval.add_argument("--folds", type=int, default=5)
    crossval.add_argument("--hidden-dim", type=int, default=16)
    crossval.add_argument("--dropout", type=float, default=0.20)
    crossval.add_argument("--correction-scale", type=float, default=1.0)
    crossval.add_argument(
        "--feature-set",
        choices=("all", "stage1_only", "graph_only"),
        default="all",
        help="Feature ablation for the residual correction MLP.",
    )
    crossval.add_argument("--epochs", type=int, default=100)
    crossval.add_argument("--patience", type=int, default=15)
    crossval.add_argument("--learning-rate", type=float, default=1e-3)
    crossval.add_argument("--weight-decay", type=float, default=1e-4)
    crossval.add_argument("--gradient-clip", type=float, default=2.0)
    crossval.add_argument("--seed", type=int, default=42)

    inference = subparsers.add_parser(
        "infer", help="Rerank label-free Stage-1 predictions with a checkpoint."
    )
    _add_shared_args(inference)
    inference.add_argument("--checkpoint", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "crossval":
        run_cross_validation(args)
    elif args.command == "infer":
        run_inference(args)
    else:  # pragma: no cover
        raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
