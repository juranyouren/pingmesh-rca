from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Mapping, Sequence

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.RootCauseAnalyze.stage1.neural_graph import (
    EventVocabulary,
    GraphBuildConfig,
    PathConditionedGraphBuilder,
    RawCase,
    grouped_kfold_indices,
    load_raw_cases,
)
from Sys.utils.io_utils import save_json


MODEL_NAME = "PC-STGR-SSL"
MODEL_VERSION = "self-supervised-pretrained-path-conditioned-spatiotemporal-graph-ranker-v1"


def _backend():
    from Sys.RootCauseAnalyze.stage1 import neural_ssl_model

    return neural_ssl_model


def _default_paths() -> tuple[str, str, str | None]:
    try:
        from Sys.config import config

        return config.data.nodes_labeled, config.data.results, config.data.alarm_weights
    except Exception:
        return "data/node/nodes_max_labeled", "data/res", None


def _graph_config(args: argparse.Namespace) -> GraphBuildConfig:
    return GraphBuildConfig(
        event_window_ms=args.event_window_ms,
        dedup_window_ms=args.dedup_window_ms,
        max_events_per_device=args.max_events_per_device,
        max_events_total=args.max_events_total,
        max_neighbor_event_edges_per_link=args.max_neighbor_event_edges_per_link,
        max_neighbor_lag_ms=args.max_neighbor_lag_ms,
        corridor_slack_hops=args.corridor_slack_hops,
        max_event_vocab=args.max_event_vocab,
        include_propagation_edge_probabilities=args.include_propagation_edge_probabilities,
        propagation_probability_method=args.propagation_probability_method,
        propagation_max_candidate_nodes=args.propagation_max_candidate_nodes,
    )


def _model_config(args: argparse.Namespace):
    backend = _backend()
    return backend.NeuralModelConfig(
        hidden_dim=args.hidden_dim,
        heads=args.heads,
        layers=args.layers,
        dropout=args.dropout,
        event_embedding_dim=args.event_embedding_dim,
        use_propagation_edge_probabilities=args.include_propagation_edge_probabilities,
    )


def _training_config(args: argparse.Namespace, *, seed: int | None = None):
    backend = _backend()
    return backend.TrainingConfig(
        epochs=args.epochs,
        patience=args.patience,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        gradient_accumulation=args.gradient_accumulation,
        gradient_clip=args.gradient_clip,
        seed=args.seed if seed is None else seed,
    )


def _pretraining_config(args: argparse.Namespace, *, seed: int | None = None):
    backend = _backend()
    return backend.PretrainingConfig(
        epochs=args.pretrain_epochs,
        learning_rate=args.pretrain_learning_rate,
        weight_decay=args.pretrain_weight_decay,
        gradient_accumulation=args.pretrain_gradient_accumulation,
        gradient_clip=args.pretrain_gradient_clip,
        token_mask_rate=args.pretrain_token_mask_rate,
        feature_mask_rate=args.pretrain_feature_mask_rate,
        edge_drop_rate=args.pretrain_edge_drop_rate,
        token_loss_weight=args.pretrain_token_loss_weight,
        feature_loss_weight=args.pretrain_feature_loss_weight,
        edge_loss_weight=args.pretrain_edge_loss_weight,
        seed=args.seed if seed is None else seed,
    )


def _response(rankings: Sequence[Mapping[str, Any]], reason: str) -> str:
    payload = {
        "reasoning": reason,
        "ip": [str(item.get("ip")) for item in rankings if item.get("ip")],
    }
    return f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"


def result_record(
    case: RawCase,
    rankings: Sequence[Mapping[str, Any]],
    diagnostics: Mapping[str, Any],
    *,
    evaluation_mode: str,
    fold: int | None = None,
) -> Dict[str, Any]:
    canonical = [dict(item) for item in rankings]
    reason = f"{MODEL_NAME} Stage 1 ({MODEL_VERSION}); evaluation_mode={evaluation_mode}."
    response = _response(canonical, reason)
    metadata: Dict[str, Any] = {
        "method": MODEL_VERSION,
        "model_name": MODEL_NAME,
        "pretraining": "self_supervised",
        "evaluation_mode": evaluation_mode,
        "root_rankings": canonical,
        "diagnostics": dict(diagnostics),
    }
    if fold is not None:
        metadata["fold"] = int(fold)
    return {
        "dir": case.dirpath,
        "prompt": "PC_STGR_SSL_STAGE1_DEVICE_EVENT_GRAPH",
        "draft_response": response,
        "response": response,
        "ranked_ips": [str(item["ip"]) for item in canonical if item.get("ip")],
        "ranking_details": {
            "neural": {"topk": canonical, "rankings": canonical, "diagnostics": dict(diagnostics)},
            "combined": {"top3": canonical[:3], "topk": canonical, "rankings": canonical},
        },
        "stage1": metadata,
        "initial_root_rankings": canonical,
        "gt_ips": [],
    }


def _release_accelerator(backend: Any) -> None:
    gc.collect()
    if backend.torch.cuda.is_available():
        backend.torch.cuda.empty_cache()
    if hasattr(backend.torch, "npu"):
        try:
            backend.torch.npu.empty_cache()
        except Exception:
            pass


def _build_graphs(
    cases: Sequence[RawCase],
    vocabulary: EventVocabulary,
    graph_config: GraphBuildConfig,
    weight_file: str | None,
    *,
    include_labels: bool,
) -> List[Any]:
    builder = PathConditionedGraphBuilder(
        vocabulary, config=graph_config, weight_path=weight_file
    )
    return [builder.build(case, include_labels=include_labels) for case in cases]


def _label_free_index(data_root: str) -> Dict[str, RawCase]:
    return {
        os.path.normcase(os.path.normpath(case.dirpath)): case
        for case in load_raw_cases(data_root, require_labels=False)
    }


def _without_labels(
    cases: Sequence[RawCase], label_free_by_path: Mapping[str, RawCase]
) -> List[RawCase]:
    result = []
    for case in cases:
        key = os.path.normcase(os.path.normpath(case.dirpath))
        label_free = label_free_by_path.get(key)
        if label_free is None:
            raise ValueError(f"could not reload case without labels: {case.dirpath}")
        if label_free.gt_ip is not None:
            raise AssertionError("label-free case unexpectedly contains a root label")
        result.append(label_free)
    return result


def _inner_case_split(
    cases: Sequence[RawCase], *, seed: int
) -> tuple[List[RawCase], List[RawCase]]:
    """Select fine-tuning epochs without consulting the outer validation fold."""

    if len(cases) < 3:
        return list(cases), []
    try:
        validation = set(grouped_kfold_indices(cases, 5, seed)[0])
    except ValueError:
        return list(cases), []
    training = [case for index, case in enumerate(cases) if index not in validation]
    development = [case for index, case in enumerate(cases) if index in validation]
    if not training or not development:
        return list(cases), []
    return training, development


def _pretrain_and_finetune(
    *,
    backend: Any,
    pretraining_cases: Sequence[RawCase],
    training_cases: Sequence[RawCase],
    validation_cases: Sequence[RawCase],
    vocabulary: EventVocabulary,
    graph_config: GraphBuildConfig,
    model_config: Any,
    pretraining_config: Any,
    training_config: Any,
    weight_file: str | None,
    device: Any,
    fixed_epochs: int | None = None,
):
    pretraining_graphs = _build_graphs(
        pretraining_cases,
        vocabulary,
        graph_config,
        weight_file,
        include_labels=False,
    )
    training_graphs = _build_graphs(
        training_cases,
        vocabulary,
        graph_config,
        weight_file,
        include_labels=True,
    )
    validation_graphs = _build_graphs(
        validation_cases,
        vocabulary,
        graph_config,
        weight_file,
        include_labels=True,
    )
    model, pretraining_history = backend.pretrain_model(
        pretraining_graphs,
        vocabulary_size=len(vocabulary.itos),
        model_config=model_config,
        pretraining_config=pretraining_config,
        device=device,
    )
    model, best_epoch, finetuning_history = backend.finetune_model(
        model,
        training_graphs,
        validation_graphs,
        training_config=training_config,
        device=device,
        fixed_epochs=fixed_epochs,
    )
    return (
        model,
        best_epoch,
        pretraining_history,
        finetuning_history,
        training_graphs,
        validation_graphs,
    )


def run_cross_validation(args: argparse.Namespace) -> str:
    backend = _backend()
    device = backend.resolve_device(args.device)
    cases = load_raw_cases(args.data_root, require_labels=True)
    if len(cases) < 2:
        raise ValueError(f"need at least two labeled cases, found {len(cases)} under {args.data_root}")
    label_free_by_path = _label_free_index(args.data_root)
    folds = grouped_kfold_indices(cases, args.folds, args.seed)
    graph_config = _graph_config(args)
    model_config = _model_config(args)
    os.makedirs(args.output_dir, exist_ok=True)
    fold_dir = os.path.join(args.output_dir, "folds")
    os.makedirs(fold_dir, exist_ok=True)

    print(
        f"{MODEL_NAME} Stage 1 OOF: cases={len(cases)}, folds={len(folds)}, "
        f"device={device}, model={MODEL_VERSION}"
    )
    started = time.time()
    records_by_index: Dict[int, Dict[str, Any]] = {}
    fold_summaries: List[Dict[str, Any]] = []
    histories: Dict[str, Any] = {}
    all_indices = set(range(len(cases)))

    for fold_number, validation_indices in enumerate(folds, 1):
        validation_set = set(validation_indices)
        training_indices = sorted(all_indices - validation_set)
        if not training_indices:
            raise ValueError(f"fold {fold_number} has no training cases")
        training_cases = [cases[index] for index in training_indices]
        validation_cases = [cases[index] for index in validation_indices]
        pretraining_cases = _without_labels(training_cases, label_free_by_path)
        vocabulary = EventVocabulary.fit(
            pretraining_cases, max_size=graph_config.max_event_vocab
        )
        inner_training_cases, inner_validation_cases = _inner_case_split(
            training_cases, seed=args.seed + fold_number
        )
        pretraining_config = _pretraining_config(args, seed=args.seed + fold_number)
        training_config = _training_config(args, seed=args.seed + fold_number)
        if inner_validation_cases:
            (
                selection_model,
                best_epoch,
                selection_pretraining_history,
                selection_finetuning_history,
                selection_training_graphs,
                selection_validation_graphs,
            ) = _pretrain_and_finetune(
                backend=backend,
                pretraining_cases=pretraining_cases,
                training_cases=inner_training_cases,
                validation_cases=inner_validation_cases,
                vocabulary=vocabulary,
                graph_config=graph_config,
                model_config=model_config,
                pretraining_config=pretraining_config,
                training_config=training_config,
                weight_file=args.weight_file,
                device=device,
            )
            del (
                selection_model,
                selection_training_graphs,
                selection_validation_graphs,
            )
            _release_accelerator(backend)
        else:
            best_epoch = max(1, int(args.epochs))
            selection_pretraining_history = []
            selection_finetuning_history = []
        outer_pretraining_config = _pretraining_config(
            args, seed=args.seed + 1_000 + fold_number
        )
        outer_training_config = _training_config(
            args, seed=args.seed + 1_000 + fold_number
        )
        (
            model,
            _outer_epoch,
            pretraining_history,
            finetuning_history,
            training_graphs,
            validation_graphs,
        ) = _pretrain_and_finetune(
            backend=backend,
            pretraining_cases=pretraining_cases,
            training_cases=training_cases,
            validation_cases=validation_cases,
            vocabulary=vocabulary,
            graph_config=graph_config,
            model_config=model_config,
            pretraining_config=outer_pretraining_config,
            training_config=outer_training_config,
            weight_file=args.weight_file,
            device=device,
            fixed_epochs=best_epoch,
        )
        missing_train_labels = sum(
            graph.root_device_position is None for graph in training_graphs
        )
        missing_validation_labels = sum(
            graph.root_device_position is None for graph in validation_graphs
        )
        validation_metrics = backend.evaluate_model(model, validation_graphs, device)
        checkpoint_path = os.path.join(fold_dir, f"fold_{fold_number}.pt")
        backend.save_checkpoint(
            checkpoint_path,
            model=model,
            vocabulary=vocabulary.to_dict(),
            graph_config=graph_config.to_dict(),
            model_config=model_config,
            training_config=outer_training_config,
            pretraining_config=outer_pretraining_config,
            metadata={
                "model_name": MODEL_NAME,
                "model_version": MODEL_VERSION,
                "pretraining": "self_supervised_training_fold_only",
                "evaluation_mode": "out_of_fold",
                "fold": fold_number,
                "best_epoch": best_epoch,
                "pretraining_case_count": len(pretraining_cases),
                "train_case_count": len(training_cases),
                "validation_case_count": len(validation_cases),
                "validation_metrics": validation_metrics,
            },
        )
        for original_index, case, graph in zip(
            validation_indices, validation_cases, validation_graphs
        ):
            rankings, diagnostics = backend.predict_graph(
                model, graph, device, top_k=args.top_k
            )
            records_by_index[original_index] = result_record(
                case,
                rankings,
                diagnostics,
                evaluation_mode="out_of_fold",
                fold=fold_number,
            )
        fold_training_result_path = os.path.join(
            fold_dir, f"fold_{fold_number}_train_res.json"
        )
        fold_training_records = []
        for case, graph in zip(training_cases, training_graphs):
            rankings, diagnostics = backend.predict_graph(
                model, graph, device, top_k=args.top_k
            )
            fold_training_records.append(
                result_record(
                    case,
                    rankings,
                    diagnostics,
                    evaluation_mode="outer_fold_training_prediction",
                    fold=fold_number,
                )
            )
        save_json(fold_training_records, fold_training_result_path, indent=2)
        fold_summary = {
            "fold": fold_number,
            "pretraining_cases": len(pretraining_cases),
            "train_cases": len(training_cases),
            "validation_cases": len(validation_cases),
            "vocabulary_size": len(vocabulary.itos),
            "pretraining_epochs": len(pretraining_history),
            "best_epoch": best_epoch,
            "train_labels_outside_graph": missing_train_labels,
            "validation_labels_outside_graph": missing_validation_labels,
            "validation_metrics": validation_metrics,
            "checkpoint": checkpoint_path,
            "training_predictions": fold_training_result_path,
        }
        fold_summaries.append(fold_summary)
        histories[str(fold_number)] = {
            "epoch_selection": {
                "pretraining": selection_pretraining_history,
                "finetuning": selection_finetuning_history,
            },
            "outer_training": {
                "pretraining": pretraining_history,
                "finetuning": finetuning_history,
            },
        }
        print(f"Fold {fold_number}/{len(folds)}: {json.dumps(fold_summary, ensure_ascii=False)}")
        del model, training_graphs, validation_graphs
        _release_accelerator(backend)

    if len(records_by_index) != len(cases):
        missing = sorted(set(range(len(cases))) - set(records_by_index))
        raise RuntimeError(f"OOF prediction is incomplete; missing indices={missing}")
    result_path = os.path.join(args.output_dir, "res.json")
    save_json([records_by_index[index] for index in range(len(cases))], result_path, indent=2)
    save_json(histories, os.path.join(args.output_dir, "training_history.json"), indent=2)

    final_pretraining_cases = _without_labels(cases, label_free_by_path)
    final_vocabulary = EventVocabulary.fit(
        final_pretraining_cases, max_size=graph_config.max_event_vocab
    )
    selected_epochs = max(
        1, int(statistics.median(item["best_epoch"] for item in fold_summaries))
    )
    final_pretraining = _pretraining_config(args, seed=args.seed + 10_000)
    final_training = _training_config(args, seed=args.seed + 10_000)
    (
        final_model,
        _final_epoch,
        final_pretraining_history,
        final_finetuning_history,
        final_graphs,
        _empty_validation,
    ) = _pretrain_and_finetune(
        backend=backend,
        pretraining_cases=final_pretraining_cases,
        training_cases=cases,
        validation_cases=[],
        vocabulary=final_vocabulary,
        graph_config=graph_config,
        model_config=model_config,
        pretraining_config=final_pretraining,
        training_config=final_training,
        weight_file=args.weight_file,
        device=device,
        fixed_epochs=selected_epochs,
    )
    final_checkpoint = os.path.join(args.output_dir, "final_model.pt")
    backend.save_checkpoint(
        final_checkpoint,
        model=final_model,
        vocabulary=final_vocabulary.to_dict(),
        graph_config=graph_config.to_dict(),
        model_config=model_config,
        training_config=final_training,
        pretraining_config=final_pretraining,
        metadata={
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "pretraining": "self_supervised_all_cases_without_labels",
            "evaluation_mode": "trained_on_all_labeled_cases",
            "pretraining_case_count": len(final_pretraining_cases),
            "train_case_count": len(cases),
            "epochs": selected_epochs,
            "source": "median_best_epoch_from_oof_folds",
        },
    )
    final_training_result_path = os.path.join(args.output_dir, "final_train_res.json")
    final_training_records = []
    for case, graph in zip(cases, final_graphs):
        rankings, diagnostics = backend.predict_graph(
            final_model, graph, device, top_k=args.top_k
        )
        final_training_records.append(
            result_record(
                case,
                rankings,
                diagnostics,
                evaluation_mode="trained_on_all_labeled_cases",
            )
        )
    save_json(final_training_records, final_training_result_path, indent=2)
    summary = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "pretraining": "self_supervised",
        "evaluation_mode": "out_of_fold",
        "case_count": len(cases),
        "fold_count": len(folds),
        "device": str(device),
        "elapsed_seconds": round(time.time() - started, 3),
        "graph_config": graph_config.to_dict(),
        "model_config": model_config.to_dict(),
        "pretraining_config": _pretraining_config(args).to_dict(),
        "training_config": _training_config(args).to_dict(),
        "folds": fold_summaries,
        "final_checkpoint": final_checkpoint,
        "final_training_predictions": final_training_result_path,
        "final_training_epochs": selected_epochs,
        "final_pretraining_history": final_pretraining_history,
        "final_training_history": final_finetuning_history,
        "oof_result": result_path,
    }
    save_json(summary, os.path.join(args.output_dir, "training_summary.json"), indent=2)
    print(f"OOF result: {result_path}")
    print(f"Final checkpoint: {final_checkpoint}")
    del final_model, final_graphs
    _release_accelerator(backend)
    return result_path


def run_train(args: argparse.Namespace) -> str:
    backend = _backend()
    device = backend.resolve_device(args.device)
    cases = load_raw_cases(args.data_root, require_labels=True)
    if len(cases) < 2:
        raise ValueError("training requires at least two labeled cases")
    validation_indices = set(
        grouped_kfold_indices(
            cases, max(2, round(1 / args.validation_ratio)), args.seed
        )[0]
    )
    training_cases = [
        case for index, case in enumerate(cases) if index not in validation_indices
    ]
    validation_cases = [
        case for index, case in enumerate(cases) if index in validation_indices
    ]
    label_free_by_path = _label_free_index(args.data_root)
    pretraining_cases = _without_labels(training_cases, label_free_by_path)
    graph_config = _graph_config(args)
    vocabulary = EventVocabulary.fit(
        pretraining_cases, max_size=graph_config.max_event_vocab
    )
    model_config = _model_config(args)
    pretraining_config = _pretraining_config(args)
    training_config = _training_config(args)
    (
        model,
        best_epoch,
        pretraining_history,
        finetuning_history,
        _training_graphs,
        validation_graphs,
    ) = _pretrain_and_finetune(
        backend=backend,
        pretraining_cases=pretraining_cases,
        training_cases=training_cases,
        validation_cases=validation_cases,
        vocabulary=vocabulary,
        graph_config=graph_config,
        model_config=model_config,
        pretraining_config=pretraining_config,
        training_config=training_config,
        weight_file=args.weight_file,
        device=device,
    )
    metrics = backend.evaluate_model(model, validation_graphs, device)
    backend.save_checkpoint(
        args.checkpoint,
        model=model,
        vocabulary=vocabulary.to_dict(),
        graph_config=graph_config.to_dict(),
        model_config=model_config,
        training_config=training_config,
        pretraining_config=pretraining_config,
        metadata={
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "pretraining": "self_supervised_training_split_only",
            "evaluation_mode": "holdout_validation",
            "pretraining_case_count": len(pretraining_cases),
            "train_case_count": len(training_cases),
            "validation_case_count": len(validation_cases),
            "best_epoch": best_epoch,
            "validation_metrics": metrics,
            "pretraining_history": pretraining_history,
            "finetuning_history": finetuning_history,
        },
    )
    print(
        json.dumps(
            {"checkpoint": args.checkpoint, "validation_metrics": metrics},
            ensure_ascii=False,
            indent=2,
        )
    )
    return args.checkpoint


def run_inference(args: argparse.Namespace) -> str:
    backend = _backend()
    device = backend.resolve_device(args.device)
    model, payload = backend.load_checkpoint(args.checkpoint, device)
    vocabulary = EventVocabulary.from_dict(payload["vocabulary"])
    graph_config = GraphBuildConfig(**payload["graph_config"])
    cases = load_raw_cases(args.data_root, require_labels=False)
    builder = PathConditionedGraphBuilder(
        vocabulary, config=graph_config, weight_path=args.weight_file
    )
    records = []
    for index, case in enumerate(cases, 1):
        graph = builder.build(case, include_labels=False)
        rankings, diagnostics = backend.predict_graph(
            model, graph, device, top_k=args.top_k
        )
        records.append(
            result_record(
                case, rankings, diagnostics, evaluation_mode="checkpoint_inference"
            )
        )
        if index % 20 == 0:
            print(f"Inference: {index}/{len(cases)}")
    os.makedirs(args.output_dir, exist_ok=True)
    result_path = os.path.join(args.output_dir, "res.json")
    save_json(records, result_path, indent=2)
    save_json(
        {
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "pretraining": "self_supervised",
            "checkpoint": args.checkpoint,
            "case_count": len(records),
            "device": str(device),
            "result": result_path,
        },
        os.path.join(args.output_dir, "inference_summary.json"),
        indent=2,
    )
    print(f"Inference result: {result_path}")
    return result_path


def _add_graph_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--weight-file", default=None)
    parser.add_argument("--event-window-ms", type=int, default=1_800_000)
    parser.add_argument("--dedup-window-ms", type=int, default=60_000)
    parser.add_argument("--max-events-per-device", type=int, default=16)
    parser.add_argument("--max-events-total", type=int, default=1_024)
    parser.add_argument("--max-neighbor-event-edges-per-link", type=int, default=4)
    parser.add_argument("--max-neighbor-lag-ms", type=int, default=600_000)
    parser.add_argument("--corridor-slack-hops", type=int, default=2)
    parser.add_argument("--max-event-vocab", type=int, default=256)
    parser.add_argument(
        "--include-propagation-edge-probabilities",
        action="store_true",
        help=(
            "Append root-independent A->B/B->A/No-Direct probabilities to "
            "physical PC-STGR edge features."
        ),
    )
    parser.add_argument(
        "--propagation-probability-method",
        choices=("deterministic_evidence_v1", "logit_softmax_v1"),
        default="deterministic_evidence_v1",
    )
    parser.add_argument("--propagation-max-candidate-nodes", type=int, default=80)


def _add_model_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--heads", type=int, default=4)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.20)
    parser.add_argument("--event-embedding-dim", type=int, default=16)


def _add_training_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--gradient-accumulation", type=int, default=8)
    parser.add_argument("--gradient-clip", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=42)


def _add_pretraining_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pretrain-epochs", type=int, default=40)
    parser.add_argument("--pretrain-learning-rate", type=float, default=1e-3)
    parser.add_argument("--pretrain-weight-decay", type=float, default=1e-4)
    parser.add_argument("--pretrain-gradient-accumulation", type=int, default=8)
    parser.add_argument("--pretrain-gradient-clip", type=float, default=2.0)
    parser.add_argument("--pretrain-token-mask-rate", type=float, default=0.25)
    parser.add_argument("--pretrain-feature-mask-rate", type=float, default=0.20)
    parser.add_argument("--pretrain-edge-drop-rate", type=float, default=0.15)
    parser.add_argument("--pretrain-token-loss-weight", type=float, default=1.0)
    parser.add_argument("--pretrain-feature-loss-weight", type=float, default=1.0)
    parser.add_argument("--pretrain-edge-loss-weight", type=float, default=1.0)


def build_parser() -> argparse.ArgumentParser:
    default_data, default_results, default_weights = _default_paths()
    parser = argparse.ArgumentParser(
        description="Train or run the optional self-supervised PC-STGR Stage 1 ranker."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    crossval = subparsers.add_parser(
        "crossval",
        help="Generate leakage-safe OOF predictions after fold-local self-supervised pretraining.",
    )
    crossval.add_argument("--data-root", default=default_data)
    crossval.add_argument(
        "--output-dir", default=os.path.join(default_results, "pc_stgr_ssl_cv")
    )
    crossval.add_argument("--folds", type=int, default=5)
    crossval.add_argument("--top-k", type=int, default=10)
    crossval.add_argument("--device", default="auto")
    _add_graph_args(crossval)
    crossval.set_defaults(weight_file=default_weights)
    _add_model_args(crossval)
    _add_pretraining_args(crossval)
    _add_training_args(crossval)

    train = subparsers.add_parser(
        "train", help="Pretrain and fine-tune one checkpoint with an internal holdout."
    )
    train.add_argument("--data-root", default=default_data)
    train.add_argument("--checkpoint", required=True)
    train.add_argument("--validation-ratio", type=float, default=0.20)
    train.add_argument("--device", default="auto")
    _add_graph_args(train)
    train.set_defaults(weight_file=default_weights)
    _add_model_args(train)
    _add_pretraining_args(train)
    _add_training_args(train)

    inference = subparsers.add_parser(
        "infer", help="Run label-free inference with a self-supervised PC-STGR checkpoint."
    )
    inference.add_argument("--data-root", default=default_data)
    inference.add_argument("--checkpoint", required=True)
    inference.add_argument("--output-dir", required=True)
    inference.add_argument("--top-k", type=int, default=10)
    inference.add_argument("--device", default="auto")
    inference.add_argument("--weight-file", default=default_weights)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "crossval":
        run_cross_validation(args)
    elif args.command == "train":
        if not 0.0 < args.validation_ratio < 1.0:
            parser.error("--validation-ratio must be within (0, 1)")
        run_train(args)
    elif args.command == "infer":
        run_inference(args)
    else:  # pragma: no cover
        parser.error(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
