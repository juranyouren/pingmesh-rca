from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import sys
import time
from dataclasses import asdict
from typing import Any, Dict, List, Mapping, Sequence

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.RootCauseAnalyze.stage1.neural_graph import (
    EventVocabulary,
    GraphBuildConfig,
    IncidentGraphBuilder,
    RawCase,
    grouped_kfold_indices,
    load_raw_cases,
)
from Sys.utils.io_utils import save_json


MODEL_VERSION = "incident-conditioned-spatiotemporal-heterograph-v1"


def _backend():
    from Sys.RootCauseAnalyze.stage1 import neural_model

    return neural_model


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
    )


def _model_config(args: argparse.Namespace):
    backend = _backend()
    return backend.NeuralModelConfig(
        hidden_dim=args.hidden_dim,
        heads=args.heads,
        layers=args.layers,
        dropout=args.dropout,
        pairwise_weight=args.pairwise_weight,
        hard_negative_k=args.hard_negative_k,
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
    reason = f"Neural Stage 1 ({MODEL_VERSION}); evaluation_mode={evaluation_mode}."
    response = _response(canonical, reason)
    metadata: Dict[str, Any] = {
        "method": MODEL_VERSION,
        "evaluation_mode": evaluation_mode,
        "root_rankings": canonical,
        "diagnostics": dict(diagnostics),
    }
    if fold is not None:
        metadata["fold"] = int(fold)
    return {
        "dir": case.dirpath,
        "prompt": "NEURAL_STAGE1_SPATIOTEMPORAL_GRAPH",
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
    builder = IncidentGraphBuilder(vocabulary, config=graph_config, weight_path=weight_file)
    return [builder.build(case, include_labels=include_labels) for case in cases]


def run_cross_validation(args: argparse.Namespace) -> str:
    backend = _backend()
    device = backend.resolve_device(args.device)
    cases = load_raw_cases(args.data_root, require_labels=True)
    if len(cases) < 2:
        raise ValueError(f"need at least two labeled cases, found {len(cases)} under {args.data_root}")
    folds = grouped_kfold_indices(cases, args.folds, args.seed)
    graph_config = _graph_config(args)
    model_config = _model_config(args)
    os.makedirs(args.output_dir, exist_ok=True)
    fold_dir = os.path.join(args.output_dir, "folds")
    os.makedirs(fold_dir, exist_ok=True)

    print(
        f"Neural Stage 1 OOF: cases={len(cases)}, folds={len(folds)}, "
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
        vocabulary = EventVocabulary.fit(training_cases, max_size=graph_config.max_event_vocab)
        training_graphs = _build_graphs(
            training_cases, vocabulary, graph_config, args.weight_file, include_labels=True
        )
        validation_graphs = _build_graphs(
            validation_cases, vocabulary, graph_config, args.weight_file, include_labels=True
        )
        missing_train_labels = sum(not graph.positive_device_positions for graph in training_graphs)
        missing_validation_labels = sum(not graph.positive_device_positions for graph in validation_graphs)
        if missing_train_labels or missing_validation_labels:
            print(
                f"[WARNING] fold={fold_number}: labels outside graph: "
                f"train={missing_train_labels}, validation={missing_validation_labels}"
            )
        training_config = _training_config(args, seed=args.seed + fold_number)
        model, best_epoch, history = backend.train_model(
            training_graphs,
            validation_graphs,
            vocabulary_size=len(vocabulary.itos),
            model_config=model_config,
            training_config=training_config,
            device=device,
        )
        validation_metrics = backend.evaluate_model(model, validation_graphs, device)
        checkpoint_path = os.path.join(fold_dir, f"fold_{fold_number}.pt")
        backend.save_checkpoint(
            checkpoint_path,
            model=model,
            vocabulary=vocabulary.to_dict(),
            graph_config=graph_config.to_dict(),
            model_config=model_config,
            training_config=training_config,
            metadata={
                "evaluation_mode": "out_of_fold",
                "fold": fold_number,
                "best_epoch": best_epoch,
                "train_case_count": len(training_cases),
                "validation_case_count": len(validation_cases),
                "validation_metrics": validation_metrics,
            },
        )
        for original_index, case, graph in zip(validation_indices, validation_cases, validation_graphs):
            rankings, diagnostics = backend.predict_graph(model, graph, device, top_k=args.top_k)
            records_by_index[original_index] = result_record(
                case,
                rankings,
                diagnostics,
                evaluation_mode="out_of_fold",
                fold=fold_number,
            )
        fold_summary = {
            "fold": fold_number,
            "train_cases": len(training_cases),
            "validation_cases": len(validation_cases),
            "vocabulary_size": len(vocabulary.itos),
            "best_epoch": best_epoch,
            "train_labels_outside_graph": missing_train_labels,
            "validation_labels_outside_graph": missing_validation_labels,
            "validation_metrics": validation_metrics,
            "checkpoint": checkpoint_path,
        }
        fold_summaries.append(fold_summary)
        histories[str(fold_number)] = history
        print(f"Fold {fold_number}/{len(folds)}: {json.dumps(fold_summary, ensure_ascii=False)}")
        del model, training_graphs, validation_graphs
        _release_accelerator(backend)

    if len(records_by_index) != len(cases):
        missing = sorted(set(range(len(cases))) - set(records_by_index))
        raise RuntimeError(f"OOF prediction is incomplete; missing indices={missing}")
    result_path = os.path.join(args.output_dir, "res.json")
    save_json([records_by_index[index] for index in range(len(cases))], result_path, indent=2)
    save_json(histories, os.path.join(args.output_dir, "training_history.json"), indent=2)

    final_vocabulary = EventVocabulary.fit(cases, max_size=graph_config.max_event_vocab)
    final_graphs = _build_graphs(
        cases, final_vocabulary, graph_config, args.weight_file, include_labels=True
    )
    selected_epochs = max(1, int(statistics.median(item["best_epoch"] for item in fold_summaries)))
    final_training = _training_config(args, seed=args.seed + 10_000)
    final_model, _final_epoch, final_history = backend.train_model(
        final_graphs,
        [],
        vocabulary_size=len(final_vocabulary.itos),
        model_config=model_config,
        training_config=final_training,
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
        metadata={
            "evaluation_mode": "trained_on_all_labeled_cases",
            "train_case_count": len(cases),
            "epochs": selected_epochs,
            "source": "median_best_epoch_from_oof_folds",
        },
    )
    summary = {
        "model_version": MODEL_VERSION,
        "evaluation_mode": "out_of_fold",
        "case_count": len(cases),
        "fold_count": len(folds),
        "device": str(device),
        "elapsed_seconds": round(time.time() - started, 3),
        "graph_config": graph_config.to_dict(),
        "model_config": model_config.to_dict(),
        "training_config": _training_config(args).to_dict(),
        "folds": fold_summaries,
        "final_checkpoint": final_checkpoint,
        "final_training_epochs": selected_epochs,
        "final_training_history": final_history,
        "oof_result": result_path,
    }
    save_json(summary, os.path.join(args.output_dir, "training_summary.json"), indent=2)
    print(f"OOF result: {result_path}")
    print(f"Final checkpoint: {final_checkpoint}")
    return result_path


def run_train(args: argparse.Namespace) -> str:
    backend = _backend()
    device = backend.resolve_device(args.device)
    cases = load_raw_cases(args.data_root, require_labels=True)
    if len(cases) < 2:
        raise ValueError("training requires at least two labeled cases")
    validation_indices = set(grouped_kfold_indices(cases, max(2, round(1 / args.validation_ratio)), args.seed)[0])
    training_cases = [case for index, case in enumerate(cases) if index not in validation_indices]
    validation_cases = [case for index, case in enumerate(cases) if index in validation_indices]
    graph_config = _graph_config(args)
    vocabulary = EventVocabulary.fit(training_cases, max_size=graph_config.max_event_vocab)
    train_graphs = _build_graphs(training_cases, vocabulary, graph_config, args.weight_file, include_labels=True)
    validation_graphs = _build_graphs(validation_cases, vocabulary, graph_config, args.weight_file, include_labels=True)
    model_config = _model_config(args)
    training_config = _training_config(args)
    model, best_epoch, history = backend.train_model(
        train_graphs,
        validation_graphs,
        vocabulary_size=len(vocabulary.itos),
        model_config=model_config,
        training_config=training_config,
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
        metadata={
            "evaluation_mode": "holdout_validation",
            "train_case_count": len(training_cases),
            "validation_case_count": len(validation_cases),
            "best_epoch": best_epoch,
            "validation_metrics": metrics,
            "history": history,
        },
    )
    print(json.dumps({"checkpoint": args.checkpoint, "validation_metrics": metrics}, ensure_ascii=False, indent=2))
    return args.checkpoint


def run_inference(args: argparse.Namespace) -> str:
    backend = _backend()
    device = backend.resolve_device(args.device)
    model, payload = backend.load_checkpoint(args.checkpoint, device)
    vocabulary = EventVocabulary.from_dict(payload["vocabulary"])
    graph_config = GraphBuildConfig(**payload["graph_config"])
    cases = load_raw_cases(args.data_root, require_labels=False)
    builder = IncidentGraphBuilder(vocabulary, config=graph_config, weight_path=args.weight_file)
    records = []
    for index, case in enumerate(cases, 1):
        graph = builder.build(case, include_labels=False)
        rankings, diagnostics = backend.predict_graph(model, graph, device, top_k=args.top_k)
        records.append(
            result_record(case, rankings, diagnostics, evaluation_mode="checkpoint_inference")
        )
        if index % 20 == 0:
            print(f"Inference: {index}/{len(cases)}")
    os.makedirs(args.output_dir, exist_ok=True)
    result_path = os.path.join(args.output_dir, "res.json")
    save_json(records, result_path, indent=2)
    save_json(
        {
            "model_version": MODEL_VERSION,
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
    parser.add_argument("--max-event-vocab", type=int, default=512)


def _add_model_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--heads", type=int, default=4)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.20)
    parser.add_argument("--pairwise-weight", type=float, default=0.20)
    parser.add_argument("--hard-negative-k", type=int, default=16)


def _add_training_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--gradient-accumulation", type=int, default=8)
    parser.add_argument("--gradient-clip", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=42)


def build_parser() -> argparse.ArgumentParser:
    default_data, default_results, default_weights = _default_paths()
    parser = argparse.ArgumentParser(
        description="Train or run the incident-conditioned spatio-temporal neural Stage 1 ranker."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    crossval = subparsers.add_parser("crossval", help="Generate leakage-safe out-of-fold predictions and a final checkpoint.")
    crossval.add_argument("--data-root", default=default_data)
    crossval.add_argument("--output-dir", default=os.path.join(default_results, "neural_stage1_cv"))
    crossval.add_argument("--folds", type=int, default=5)
    crossval.add_argument("--top-k", type=int, default=10)
    crossval.add_argument("--device", default="auto")
    _add_graph_args(crossval)
    crossval.set_defaults(weight_file=default_weights)
    _add_model_args(crossval)
    _add_training_args(crossval)

    train = subparsers.add_parser("train", help="Train one checkpoint with an internal validation holdout.")
    train.add_argument("--data-root", default=default_data)
    train.add_argument("--checkpoint", required=True)
    train.add_argument("--validation-ratio", type=float, default=0.20)
    train.add_argument("--device", default="auto")
    _add_graph_args(train)
    train.set_defaults(weight_file=default_weights)
    _add_model_args(train)
    _add_training_args(train)

    inference = subparsers.add_parser("infer", help="Run label-free inference with a saved checkpoint.")
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
