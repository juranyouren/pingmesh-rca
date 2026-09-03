from __future__ import annotations

import argparse
import gc
import json
import math
import os
import statistics
import sys
import time
from dataclasses import replace
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
from Sys.RootCauseAnalyze.stage1.candidate_graph_verifier import (
    CandidateGraphExample,
    CandidateGraphView,
    VerifierModelConfig,
    VerifierTrainingConfig,
    evaluate_verifier,
    load_checkpoint,
    load_torch_payload,
    predict_example,
    save_checkpoint,
    train_verifier,
)
from Sys.RootCauseAnalyze.stage1.neural_graph import (
    EventVocabulary,
    GraphBuildConfig,
    PathConditionedGraphBuilder,
    RawCase,
    condition_graph_on_propagation_dag,
    grouped_kfold_indices,
    load_raw_cases,
)
from Sys.RootCauseAnalyze.stage1.neural_model import NeuralModelConfig, resolve_device
from Sys.utils.io_utils import load_json, save_json


MODEL_NAME = "PC-STGR-CGV"
MODEL_VERSION = "candidate-conditioned-graph-verifier-v1"
_HYPOTHESIS_GRAPH_CACHE: Dict[tuple[str, str], Dict[str, Any]] = {}


def _normalized_path(value: Any) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(value or ""))))


def _root_result_map(path: str) -> Dict[str, Dict[str, Any]]:
    records = load_json(path, default=None)
    if not isinstance(records, list):
        raise ValueError("Stage-1 root result file must contain a JSON list")
    result: Dict[str, Dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, Mapping) or not raw.get("dir"):
            continue
        key = _normalized_path(raw["dir"])
        if key in result:
            raise ValueError(f"duplicate Stage-1 result path: {raw['dir']}")
        result[key] = dict(raw)
    return result


def _root_rankings(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    stage1 = record.get("stage1", {})
    for raw in (
        record.get("initial_root_rankings"),
        stage1.get("root_rankings") if isinstance(stage1, Mapping) else None,
    ):
        if isinstance(raw, list):
            rows = [dict(item) for item in raw if isinstance(item, Mapping)]
            if rows:
                return rows
    return []


def _stage1_fold(record: Mapping[str, Any]) -> int | None:
    stage1 = record.get("stage1", {})
    raw = stage1.get("fold") if isinstance(stage1, Mapping) else None
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _stage1_model_dir(args: argparse.Namespace) -> str:
    return os.path.abspath(
        args.stage1_model_dir or os.path.dirname(os.path.abspath(args.root_results))
    )


def _fold_checkpoint(model_dir: str, fold_number: int) -> str:
    return os.path.join(model_dir, "folds", f"fold_{fold_number}.pt")


def _fold_training_results(model_dir: str, fold_number: int) -> str:
    return os.path.join(
        model_dir, "folds", f"fold_{fold_number}_train_res.json"
    )


def _final_checkpoint(model_dir: str) -> str:
    return os.path.join(model_dir, "final_model.pt")


def _final_training_results(model_dir: str) -> str:
    return os.path.join(model_dir, "final_train_res.json")


def _propagation_config(args: argparse.Namespace) -> PropagationConfig:
    return PropagationConfig(
        root_top_k=max(1, int(args.top_k)),
        max_candidate_nodes=max(1, int(args.max_candidate_nodes)),
        max_path_depth=max(1, int(args.max_path_depth)),
        stage1_weight=1.0,
        edge_probability_method=args.edge_probability_method,
    )


def _selected_edges(propagation_graph: Mapping[str, Any]) -> List[tuple[str, str]]:
    rows = []
    for edge in propagation_graph.get("edges", []):
        if not isinstance(edge, Mapping):
            continue
        source = str(edge.get("from", "") or "")
        target = str(edge.get("to", "") or "")
        if source and target and source != target:
            rows.append((source, target))
    return rows


def _candidate_root(item: Mapping[str, Any]) -> str:
    root = item.get("root_hypothesis", {})
    devices = root.get("root_devices", []) if isinstance(root, Mapping) else []
    return str(devices[0]) if isinstance(devices, list) and devices else ""


def _base_probability(row: Mapping[str, Any], rank: int) -> float:
    try:
        value = float(
            row.get("combined_score", row.get("neural_score", 1.0 / max(rank, 1)))
        )
    except (TypeError, ValueError):
        value = 1.0 / max(rank, 1)
    return max(0.0, min(1.0, value))


def _base_logit(row: Mapping[str, Any], probability: float) -> float:
    try:
        value = float(row.get("logit"))
        if math.isfinite(value):
            return value
    except (TypeError, ValueError):
        pass
    return math.log(max(probability, 1e-8))


def _graph_builder_from_stage1(
    stage1_payload: Mapping[str, Any], weight_file: str | None
) -> PathConditionedGraphBuilder:
    graph_config = GraphBuildConfig(**dict(stage1_payload.get("graph_config", {})))
    model_config = NeuralModelConfig(**dict(stage1_payload.get("model_config", {})))
    if not graph_config.include_propagation_edge_probabilities:
        raise ValueError(
            "Stage-1 graph checkpoint was not trained with propagation probabilities"
        )
    if not model_config.use_propagation_edge_probabilities:
        raise ValueError(
            "Stage-1 model checkpoint does not accept five-dimensional edge features"
        )
    # Candidate views replace the probability triplet completely, so avoid a
    # redundant M1 reconstruction while retaining every other Stage-1 setting.
    hard_view_config = replace(
        graph_config, include_propagation_edge_probabilities=False
    )
    vocabulary = EventVocabulary.from_dict(stage1_payload.get("vocabulary", {}))
    return PathConditionedGraphBuilder(
        vocabulary, config=hard_view_config, weight_path=weight_file
    )


def build_verifier_examples(
    cases: Sequence[RawCase],
    root_records: Mapping[str, Mapping[str, Any]],
    *,
    stage1_payload: Mapping[str, Any],
    propagation_config: PropagationConfig,
    weight_file: str | None,
) -> List[CandidateGraphExample]:
    """Build K hard-DAG PC-STGR views per incident without passing labels to P0."""

    builder = _graph_builder_from_stage1(stage1_payload, weight_file)
    examples: List[CandidateGraphExample] = []
    for index, case in enumerate(cases, 1):
        record = root_records.get(_normalized_path(case.dirpath))
        if record is None:
            raise ValueError(f"Stage-1 result is missing for case: {case.dirpath}")
        rankings = _root_rankings(record)[: propagation_config.root_top_k]
        if not rankings:
            raise ValueError(f"Stage-1 root rankings are empty: {case.dirpath}")
        cache_key = (
            _normalized_path(case.dirpath),
            json.dumps(
                propagation_config.to_dict(), ensure_ascii=False, sort_keys=True
            ),
        )
        hypothesis_graph = _HYPOTHESIS_GRAPH_CACHE.get(cache_key)
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
            _HYPOTHESIS_GRAPH_CACHE[cache_key] = hypothesis_graph
        inference = infer_root_paths(
            hypothesis_graph=hypothesis_graph,
            initial_root_rankings=rankings,
            config=propagation_config,
        )
        graph_by_root = {
            _candidate_root(item): item.get("propagation_graph", {})
            for item in inference.get("root_conditioned_propagation_graphs", [])
            if isinstance(item, Mapping) and _candidate_root(item)
        }
        base_graph = builder.build(case, include_labels=False)
        candidates: List[CandidateGraphView] = []
        for fallback_rank, ranking in enumerate(rankings, 1):
            ip = str(ranking.get("ip", ranking.get("device_id", "")) or "")
            if not ip:
                continue
            if ip not in base_graph.device_ips:
                raise ValueError(
                    f"candidate {ip} is outside the Stage-1 graph: {case.dirpath}"
                )
            propagation_graph = graph_by_root.get(ip, {})
            hard_graph = condition_graph_on_propagation_dag(
                base_graph,
                _selected_edges(propagation_graph),
                candidate_root=ip,
            )
            initial_rank = int(ranking.get("rank", fallback_rank) or fallback_rank)
            probability = _base_probability(ranking, initial_rank)
            candidates.append(
                CandidateGraphView(
                    ip=ip,
                    initial_rank=initial_rank,
                    base_probability=probability,
                    base_logit=_base_logit(ranking, probability),
                    graph=hard_graph,
                    candidate_device_position=hard_graph.device_ips.index(ip),
                )
            )
        candidates.sort(key=lambda candidate: (candidate.initial_rank, candidate.ip))
        examples.append(
            CandidateGraphExample(
                dirpath=case.dirpath,
                candidates=candidates,
                gt_ip=case.gt_ip,
                diagnostics={
                    "candidate_count": len(candidates),
                    "candidate_recall": bool(
                        case.gt_ip
                        and any(candidate.ip == case.gt_ip for candidate in candidates)
                    ),
                    "edge_probability_method": propagation_config.edge_probability_method,
                    "hard_selected_edge_counts": {
                        candidate.ip: candidate.graph.diagnostics.get(
                            "hard_selected_edge_count", 0
                        )
                        for candidate in candidates
                    },
                },
            )
        )
        if index % 20 == 0:
            print(f"Candidate graph construction: {index}/{len(cases)}")
    return examples


def _inner_train_dev(
    cases: Sequence[RawCase],
    examples: Sequence[CandidateGraphExample],
    *,
    seed: int,
) -> tuple[List[CandidateGraphExample], List[CandidateGraphExample]]:
    if len(cases) < 3:
        return list(examples), []
    try:
        validation_indices = set(grouped_kfold_indices(cases, 5, seed)[0])
    except ValueError:
        return list(examples), []
    training = [
        example
        for index, example in enumerate(examples)
        if index not in validation_indices
    ]
    validation = [
        example
        for index, example in enumerate(examples)
        if index in validation_indices
    ]
    if not any(example.target_position is not None for example in validation):
        return list(examples), []
    return training, validation


def _model_config(args: argparse.Namespace) -> VerifierModelConfig:
    return VerifierModelConfig(
        max_correction_scale=args.max_correction_scale,
        gate_init=args.gate_init,
        freeze_backbone=args.freeze_backbone,
    )


def _training_config(
    args: argparse.Namespace, *, seed: int | None = None
) -> VerifierTrainingConfig:
    return VerifierTrainingConfig(
        epochs=args.epochs,
        patience=args.patience,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        gradient_accumulation=args.gradient_accumulation,
        gradient_clip=args.gradient_clip,
        auxiliary_margin_loss_weight=args.auxiliary_margin_loss_weight,
        seed=args.seed if seed is None else seed,
    )


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
    metadata: Dict[str, Any] = {
        "method": MODEL_VERSION,
        "model_name": MODEL_NAME,
        "evaluation_mode": evaluation_mode,
        "candidate_count": len(final_rankings),
        "verification_mode": "K candidate-conditioned hard-DAG PC-STGR passes",
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
    stage1["candidate_graph_verifier"] = metadata
    response = _response(
        final_rankings,
        f"{MODEL_NAME} ({MODEL_VERSION}); evaluation_mode={evaluation_mode}.",
    )
    return {
        **dict(base_record),
        "prompt": "PC_STGR_CANDIDATE_CONDITIONED_GRAPH_VERIFIER",
        "draft_response": response,
        "response": response,
        "ranked_ips": [str(item["ip"]) for item in final_rankings if item.get("ip")],
        "base_root_rankings": original,
        "initial_root_rankings": original,
        "reranked_root_rankings": final_rankings,
        "final_root_rankings": final_rankings,
        "stage1": stage1,
        "candidate_graph_verifier": metadata,
        "gt_ips": [],
    }


def _ranking_audit(
    examples: Sequence[CandidateGraphExample],
    rankings_by_path: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Dict[str, Any]:
    labeled = [example for example in examples if example.gt_ip]
    if not labeled:
        return {"case_count": 0}
    candidate_hits = 0
    initial_top1 = 0
    final_hits = {1: 0, 3: 0, 5: 0}
    reciprocal_rank = 0.0
    corrections = 0
    corruptions = 0
    for example in labeled:
        gt = str(example.gt_ip)
        initial_ips = [candidate.ip for candidate in example.candidates]
        final = rankings_by_path.get(_normalized_path(example.dirpath), [])
        final_ips = [str(row.get("ip", "")) for row in final]
        initial_correct = bool(initial_ips and initial_ips[0] == gt)
        final_correct = bool(final_ips and final_ips[0] == gt)
        initial_top1 += int(initial_correct)
        candidate_hits += int(gt in initial_ips)
        corrections += int(not initial_correct and final_correct)
        corruptions += int(initial_correct and not final_correct)
        if gt in final_ips:
            rank = final_ips.index(gt) + 1
            reciprocal_rank += 1.0 / rank
            for cutoff in final_hits:
                final_hits[cutoff] += int(rank <= cutoff)
    total = len(labeled)
    return {
        "case_count": total,
        "candidate_recall": round(candidate_hits / total, 6),
        "initial_top1": round(initial_top1 / total, 6),
        "final_top1": round(final_hits[1] / total, 6),
        "final_top3": round(final_hits[3] / total, 6),
        "final_top5": round(final_hits[5] / total, 6),
        "mrr": round(reciprocal_rank / total, 6),
        "conditional_top1": (
            round(final_hits[1] / candidate_hits, 6) if candidate_hits else 0.0
        ),
        "corrections": corrections,
        "corruptions": corruptions,
        "net_corrections": corrections - corruptions,
    }


def _serialize_example(example: CandidateGraphExample) -> Dict[str, Any]:
    return {
        "dir": example.dirpath,
        "gt_ip": example.gt_ip,
        "target_position": example.target_position,
        "diagnostics": dict(example.diagnostics or {}),
        "candidates": [
            {
                "ip": candidate.ip,
                "initial_rank": candidate.initial_rank,
                "base_probability": candidate.base_probability,
                "base_logit": candidate.base_logit,
                "candidate_device_position": candidate.candidate_device_position,
                "hard_selected_edge_count": candidate.graph.diagnostics.get(
                    "hard_selected_edge_count", 0
                ),
                "hard_matched_edge_count": candidate.graph.diagnostics.get(
                    "hard_matched_edge_count", 0
                ),
            }
            for candidate in example.candidates
        ],
    }


def _release_accelerator() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        if hasattr(torch, "npu") and torch.npu.is_available():
            torch.npu.empty_cache()
    except Exception:
        pass


def run_cross_validation(args: argparse.Namespace) -> str:
    started = time.time()
    device = resolve_device(args.device)
    cases = load_raw_cases(args.data_root, require_labels=True)
    if len(cases) < 2:
        raise ValueError("candidate verifier cross-validation needs two labeled cases")
    root_records = _root_result_map(args.root_results)
    folds = grouped_kfold_indices(cases, args.folds, args.seed)
    propagation_config = _propagation_config(args)
    model_config = _model_config(args)
    model_dir = _stage1_model_dir(args)
    os.makedirs(args.output_dir, exist_ok=True)
    fold_output_dir = os.path.join(args.output_dir, "folds")
    os.makedirs(fold_output_dir, exist_ok=True)

    all_indices = set(range(len(cases)))
    rankings_by_path: Dict[str, List[Dict[str, Any]]] = {}
    examples_by_path: Dict[str, CandidateGraphExample] = {}
    fold_summaries: List[Dict[str, Any]] = []
    histories: Dict[str, Any] = {}
    selected_epochs: List[int] = []

    for fold_number, validation_indices in enumerate(folds, 1):
        validation_set = set(validation_indices)
        training_indices = sorted(all_indices - validation_set)
        training_cases = [cases[index] for index in training_indices]
        validation_cases = [cases[index] for index in validation_indices]
        for case in validation_cases:
            record = root_records.get(_normalized_path(case.dirpath), {})
            record_fold = _stage1_fold(record)
            if record_fold is not None and record_fold != fold_number:
                raise ValueError(
                    "Stage-1 and verifier folds differ for "
                    f"{case.dirpath}: stage1={record_fold}, verifier={fold_number}"
                )

        checkpoint_path = _fold_checkpoint(model_dir, fold_number)
        training_result_path = _fold_training_results(model_dir, fold_number)
        if not os.path.isfile(checkpoint_path):
            raise FileNotFoundError(f"missing Stage-1 fold checkpoint: {checkpoint_path}")
        if not os.path.isfile(training_result_path):
            raise FileNotFoundError(
                f"missing Stage-1 fold training predictions: {training_result_path}"
            )
        stage1_payload = load_torch_payload(checkpoint_path, device)
        training_examples = build_verifier_examples(
            training_cases,
            _root_result_map(training_result_path),
            stage1_payload=stage1_payload,
            propagation_config=propagation_config,
            weight_file=args.weight_file,
        )
        validation_examples = build_verifier_examples(
            validation_cases,
            root_records,
            stage1_payload=stage1_payload,
            propagation_config=propagation_config,
            weight_file=args.weight_file,
        )
        for example in validation_examples:
            examples_by_path[_normalized_path(example.dirpath)] = example

        inner_training, inner_validation = _inner_train_dev(
            training_cases,
            training_examples,
            seed=args.seed + fold_number,
        )
        selection_config = _training_config(args, seed=args.seed + fold_number)
        if inner_validation:
            selection_model, best_epoch, selection_history = train_verifier(
                stage1_payload,
                inner_training,
                inner_validation,
                model_config=model_config,
                training_config=selection_config,
                device=device,
            )
            del selection_model
            _release_accelerator()
        else:
            best_epoch = max(1, int(args.epochs))
            selection_history = []
        fit_config = _training_config(args, seed=args.seed + 1_000 + fold_number)
        model, _fit_epoch, fit_history = train_verifier(
            stage1_payload,
            training_examples,
            [],
            model_config=model_config,
            training_config=fit_config,
            device=device,
            fixed_epochs=best_epoch,
        )
        selected_epochs.append(best_epoch)
        fold_metrics = evaluate_verifier(model, validation_examples, device)
        verifier_checkpoint = os.path.join(
            fold_output_dir, f"fold_{fold_number}.pt"
        )
        save_checkpoint(
            verifier_checkpoint,
            model=model,
            stage1_payload=stage1_payload,
            model_config=model_config,
            training_config=fit_config,
            propagation_config=propagation_config.to_dict(),
            metadata={
                "model_name": MODEL_NAME,
                "model_version": MODEL_VERSION,
                "evaluation_mode": "out_of_fold",
                "fold": fold_number,
                "selected_epoch": best_epoch,
                "stage1_checkpoint": checkpoint_path,
                "metrics": fold_metrics,
            },
        )
        for example in validation_examples:
            rankings_by_path[_normalized_path(example.dirpath)] = predict_example(
                model, example, device
            )
        fold_summaries.append(
            {
                "fold": fold_number,
                "train_cases": len(training_examples),
                "validation_cases": len(validation_examples),
                "selected_epoch": best_epoch,
                "metrics": fold_metrics,
                "stage1_checkpoint": checkpoint_path,
                "stage1_training_predictions": training_result_path,
                "checkpoint": verifier_checkpoint,
            }
        )
        histories[str(fold_number)] = {
            "epoch_selection": selection_history,
            "outer_training": fit_history,
        }
        print(
            f"Verifier fold {fold_number}/{len(folds)}: "
            f"{json.dumps(fold_summaries[-1], ensure_ascii=False)}"
        )
        del model, stage1_payload, training_examples, validation_examples
        _release_accelerator()

    if len(rankings_by_path) != len(cases):
        raise RuntimeError("candidate verifier OOF predictions are incomplete")
    fold_by_index = {
        case_index: fold_number
        for fold_number, fold_indices in enumerate(folds, 1)
        for case_index in fold_indices
    }
    output_records = []
    ordered_examples = []
    for case_index, case in enumerate(cases):
        key = _normalized_path(case.dirpath)
        ordered_examples.append(examples_by_path[key])
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
    save_json(
        [_serialize_example(example) for example in ordered_examples],
        os.path.join(args.output_dir, "candidate_graph_audit.json"),
        indent=2,
    )
    save_json(
        histories, os.path.join(args.output_dir, "training_history.json"), indent=2
    )

    final_stage1_checkpoint = _final_checkpoint(model_dir)
    final_training_result = _final_training_results(model_dir)
    if not os.path.isfile(final_stage1_checkpoint):
        raise FileNotFoundError(
            f"missing final Stage-1 checkpoint: {final_stage1_checkpoint}"
        )
    if not os.path.isfile(final_training_result):
        raise FileNotFoundError(
            f"missing final Stage-1 training predictions: {final_training_result}"
        )
    final_stage1_payload = load_torch_payload(final_stage1_checkpoint, device)
    final_training_examples = build_verifier_examples(
        cases,
        _root_result_map(final_training_result),
        stage1_payload=final_stage1_payload,
        propagation_config=propagation_config,
        weight_file=args.weight_file,
    )
    final_epoch = max(1, int(statistics.median(selected_epochs)))
    final_training_config = _training_config(args, seed=args.seed + 10_000)
    final_model, _epoch, final_history = train_verifier(
        final_stage1_payload,
        final_training_examples,
        [],
        model_config=model_config,
        training_config=final_training_config,
        device=device,
        fixed_epochs=final_epoch,
    )
    final_verifier_checkpoint = os.path.join(args.output_dir, "final_model.pt")
    save_checkpoint(
        final_verifier_checkpoint,
        model=final_model,
        stage1_payload=final_stage1_payload,
        model_config=model_config,
        training_config=final_training_config,
        propagation_config=propagation_config.to_dict(),
        metadata={
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "evaluation_mode": "trained_on_all_labeled_cases",
            "stage1_checkpoint": final_stage1_checkpoint,
            "train_case_count": len(final_training_examples),
            "epochs": final_epoch,
        },
    )
    summary = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "evaluation_mode": "incident_grouped_out_of_fold",
        "case_count": len(cases),
        "fold_count": len(folds),
        "device": str(device),
        "elapsed_seconds": round(time.time() - started, 3),
        "root_results": os.path.abspath(args.root_results),
        "stage1_model_dir": model_dir,
        "model_config": model_config.to_dict(),
        "training_config": _training_config(args).to_dict(),
        "propagation_config": propagation_config.to_dict(),
        "oof_metrics": _ranking_audit(ordered_examples, rankings_by_path),
        "folds": fold_summaries,
        "final_training_epochs": final_epoch,
        "final_training_history": final_history,
        "final_checkpoint": final_verifier_checkpoint,
        "oof_result": result_path,
        "candidate_graph_audit": os.path.join(
            args.output_dir, "candidate_graph_audit.json"
        ),
    }
    save_json(summary, os.path.join(args.output_dir, "training_summary.json"), indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return result_path


def run_inference(args: argparse.Namespace) -> str:
    device = resolve_device(args.device)
    model, payload = load_checkpoint(args.checkpoint, device)
    root_records = _root_result_map(args.root_results)
    discovered = load_raw_cases(args.data_root, require_labels=False)
    cases = [
        case
        for case in discovered
        if _normalized_path(case.dirpath) in root_records
    ]
    if len(cases) != len(root_records):
        discovered_paths = {_normalized_path(case.dirpath) for case in discovered}
        missing = sorted(set(root_records) - discovered_paths)
        raise ValueError(
            "some Stage-1 result cases are absent from data-root: "
            + ", ".join(missing[:5])
        )
    stage1_payload = {
        "format_version": payload["stage1_format_version"],
        "vocabulary": payload["vocabulary"],
        "graph_config": payload["graph_config"],
        "model_config": payload["stage1_model_config"],
    }
    propagation_config = PropagationConfig(**payload["propagation_config"])
    examples = build_verifier_examples(
        cases,
        root_records,
        stage1_payload=stage1_payload,
        propagation_config=propagation_config,
        weight_file=args.weight_file,
    )
    records = []
    for example in examples:
        key = _normalized_path(example.dirpath)
        records.append(
            _result_record(
                root_records[key],
                predict_example(model, example, device),
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
            "case_count": len(records),
            "checkpoint": os.path.abspath(args.checkpoint),
            "root_results": os.path.abspath(args.root_results),
            "result": result_path,
        },
        os.path.join(args.output_dir, "inference_summary.json"),
        indent=2,
    )
    return result_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Candidate-conditioned hard-DAG PC-STGR root verifier."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    crossval = subparsers.add_parser(
        "crossval", help="Train and evaluate an incident-grouped OOF verifier."
    )
    crossval.add_argument("--data-root", required=True)
    crossval.add_argument("--root-results", required=True)
    crossval.add_argument("--stage1-model-dir")
    crossval.add_argument("--output-dir", required=True)
    crossval.add_argument("--weight-file")
    crossval.add_argument("--folds", type=int, default=5)
    crossval.add_argument("--top-k", type=int, default=5)
    crossval.add_argument("--max-candidate-nodes", type=int, default=80)
    crossval.add_argument("--max-path-depth", type=int, default=8)
    crossval.add_argument(
        "--edge-probability-method",
        choices=("deterministic_evidence_v1", "logit_softmax_v1"),
        default="deterministic_evidence_v1",
    )
    crossval.add_argument("--device", default="auto")
    crossval.add_argument("--max-correction-scale", type=float, default=1.0)
    crossval.add_argument("--gate-init", type=float, default=0.0)
    crossval.add_argument("--freeze-backbone", action="store_true")
    crossval.add_argument("--epochs", type=int, default=40)
    crossval.add_argument("--patience", type=int, default=8)
    crossval.add_argument("--learning-rate", type=float, default=1e-4)
    crossval.add_argument("--weight-decay", type=float, default=1e-4)
    crossval.add_argument("--gradient-accumulation", type=int, default=4)
    crossval.add_argument("--gradient-clip", type=float, default=2.0)
    crossval.add_argument("--auxiliary-margin-loss-weight", type=float, default=0.25)
    crossval.add_argument("--seed", type=int, default=42)

    inference = subparsers.add_parser(
        "infer", help="Run K candidate-conditioned verification passes without labels."
    )
    inference.add_argument("--data-root", required=True)
    inference.add_argument("--root-results", required=True)
    inference.add_argument("--checkpoint", required=True)
    inference.add_argument("--output-dir", required=True)
    inference.add_argument("--weight-file")
    inference.add_argument("--device", default="auto")
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
