from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np


if __package__ in (None, ""):
    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)


from Sys.RootCauseAnalyze.propagation.candidates import build_candidate_graph
from Sys.RootCauseAnalyze.propagation.episodes import build_evidence_episodes
from Sys.RootCauseAnalyze.propagation.m1 import (
    EDGE_FEATURE_NAMES,
    STATE_NAMES,
    extract_edge_probability_features,
)
from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig
from Sys.RootCauseAnalyze.propagation.scorer import build_edge_relation_graph
from Sys.RootCauseAnalyze.propagation.topology_context import load_topology_context
from Sys.RootCauseAnalyze.stage1.alarm_topology_ranker import parse_endpoint_ips
from Sys.utils.case_utils import find_full_link_file, load_case_info, load_case_nodes
from Sys.utils.io_utils import load_json, save_json


MODEL_SCHEMA = "stage2-edge-classifier-v1"
MANIFEST_SCHEMA = "stage2-edge-classifier-oof-manifest-v1"
NO_DIRECT_INDEX = STATE_NAMES.index("no_direct_propagation")


def _discover_case_dirs(data_root: str) -> List[str]:
    result = []
    for dirpath, _dirnames, filenames in os.walk(data_root):
        if "info.json" in filenames and find_full_link_file(dirpath, filenames):
            result.append(os.path.abspath(dirpath))
    return sorted(result)


def _label_path(data_root: str, labels_root: str, dirpath: str) -> str | None:
    relative = os.path.relpath(dirpath, data_root)
    filename = "propagation_label.json"
    candidates = [
        os.path.join(labels_root, relative, filename),
        os.path.join(labels_root, os.path.basename(os.path.normpath(dirpath)), filename),
        os.path.join(dirpath, filename),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _positive_edges(label: Mapping[str, Any]) -> set[Tuple[str, str]]:
    result: set[Tuple[str, str]] = set()
    for item in label.get("edges", []):
        if not isinstance(item, Mapping):
            continue
        if item.get("membership") not in {"definite", "possible"}:
            continue
        edge = (str(item.get("from", "") or ""), str(item.get("to", "") or ""))
        if all(edge):
            result.add(edge)
    return result


def _split_group_key(info: Mapping[str, Any]) -> str:
    source, sink = parse_endpoint_ips(info)
    return json.dumps(
        {
            "source": sorted(str(value) for value in source),
            "sink": sorted(str(value) for value in sink),
            "alarm_name": str(info.get("alarm_name", "")),
            "source_az": str(info.get("source_az", "")),
            "sink_az": str(info.get("sink_az", "")),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _edge_class(pair: Mapping[str, Any], positives: set[Tuple[str, str]]) -> int | None:
    endpoint_a = str(pair.get("endpoint_a", "") or "")
    endpoint_b = str(pair.get("endpoint_b", "") or "")
    forward = (endpoint_a, endpoint_b) in positives
    reverse = (endpoint_b, endpoint_a) in positives
    if forward and reverse:
        return None
    if forward:
        return 0
    if reverse:
        return 1
    return NO_DIRECT_INDEX


def _raw_relation_graph(dirpath: str, config: PropagationConfig) -> Dict[str, Any]:
    nodes = load_case_nodes(dirpath)
    info = load_case_info(dirpath)
    if not nodes or not info:
        raise ValueError("missing nodes or info")
    episodes = build_evidence_episodes(nodes, info, config=config)
    topology = load_topology_context(dirpath, node_list=nodes, info=info)
    candidates = build_candidate_graph(nodes, info, topology, episodes, config=config)
    return build_edge_relation_graph(candidates, episodes, config=config)


def _swap_orientation(vector: Sequence[float]) -> List[float]:
    values = dict(zip(EDGE_FEATURE_NAMES, (float(value) for value in vector)))
    swapped: Dict[str, float] = {}
    for name in EDGE_FEATURE_NAMES:
        if name.startswith("forward_"):
            swapped[name] = values["reverse_" + name[len("forward_") :]]
        elif name.startswith("reverse_"):
            swapped[name] = values["forward_" + name[len("reverse_") :]]
        elif name == "signed_support_gap":
            swapped[name] = -values[name]
        else:
            swapped[name] = values[name]
    return [swapped[name] for name in EDGE_FEATURE_NAMES]


def collect_labeled_cases(
    data_root: str,
    labels_root: str,
    *,
    config: PropagationConfig | None = None,
    augment_orientation: bool = True,
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Build edge samples. This training-only function is the sole label consumer."""

    cfg = config or PropagationConfig()
    cases: List[Dict[str, Any]] = []
    diagnostics: Counter[str] = Counter()
    dynamic_index = EDGE_FEATURE_NAMES.index("any_dynamic_support")
    for dirpath in _discover_case_dirs(data_root):
        path = _label_path(data_root, labels_root, dirpath)
        if not path:
            diagnostics["cases_without_path_labels"] += 1
            continue
        label = load_json(path, default=None)
        if not isinstance(label, Mapping):
            diagnostics["invalid_path_labels"] += 1
            continue
        positives = _positive_edges(label)
        try:
            info = load_case_info(dirpath)
            relation_graph = _raw_relation_graph(dirpath, cfg)
        except Exception:
            diagnostics["case_build_errors"] += 1
            continue
        x_rows: List[List[float]] = []
        y_rows: List[int] = []
        for pair in relation_graph.get("edge_hypotheses", []):
            if not isinstance(pair, Mapping):
                continue
            target = _edge_class(pair, positives)
            if target is None:
                diagnostics["ambiguous_bidirectional_pairs"] += 1
                continue
            features = extract_edge_probability_features(pair)
            vector = [features[name] for name in EDGE_FEATURE_NAMES]
            if vector[dynamic_index] <= 0.0:
                diagnostics["hard_fallback_pairs"] += 1
                if target != NO_DIRECT_INDEX:
                    diagnostics["positive_pairs_without_dynamic_support"] += 1
                continue
            x_rows.append(vector)
            y_rows.append(target)
            if augment_orientation:
                x_rows.append(_swap_orientation(vector))
                y_rows.append(1 - target if target in {0, 1} else target)
        if not x_rows:
            diagnostics["cases_without_trainable_pairs"] += 1
            continue
        cases.append(
            {
                "dirpath": os.path.abspath(dirpath),
                "case_id": os.path.basename(os.path.normpath(dirpath)),
                "group_key": _split_group_key(info),
                "x": x_rows,
                "y": y_rows,
            }
        )
        diagnostics["labeled_cases"] += 1
        diagnostics["trainable_pairs"] += len(x_rows)
    return cases, dict(sorted(diagnostics.items()))


def _join_cases(cases: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray([row for case in cases for row in case["x"]], dtype=np.float64)
    y = np.asarray([row for case in cases for row in case["y"]], dtype=np.int64)
    if x.ndim != 2 or x.shape[1] != len(EDGE_FEATURE_NAMES):
        raise ValueError("edge classifier feature matrix is empty or malformed")
    return x, y


def _class_weights(y: np.ndarray) -> np.ndarray:
    counts = np.bincount(y, minlength=len(STATE_NAMES)).astype(np.float64)
    weights = np.zeros(len(STATE_NAMES), dtype=np.float64)
    present = counts > 0
    weights[present] = len(y) / (present.sum() * counts[present])
    return weights


def _softmax(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    scaled = logits / max(float(temperature), 1e-12)
    scaled = scaled - scaled.max(axis=1, keepdims=True)
    exp = np.exp(scaled)
    return exp / exp.sum(axis=1, keepdims=True)


def _loss(
    x: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    bias: np.ndarray,
    class_weights: np.ndarray,
    l2: float,
) -> float:
    probabilities = _softmax(x @ weights.T + bias)
    sample_weights = class_weights[y]
    nll = -np.log(np.maximum(probabilities[np.arange(len(y)), y], 1e-12))
    return float((nll * sample_weights).sum() / max(sample_weights.sum(), 1e-12) + 0.5 * l2 * np.sum(weights**2))


def _optimize(
    x: np.ndarray,
    y: np.ndarray,
    *,
    validation: tuple[np.ndarray, np.ndarray] | None,
    epochs: int,
    patience: int,
    learning_rate: float,
    l2: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, int, List[Dict[str, float]]]:
    rng = np.random.default_rng(seed)
    weights = rng.normal(0.0, 0.01, size=(len(STATE_NAMES), x.shape[1]))
    bias = np.zeros(len(STATE_NAMES), dtype=np.float64)
    first_moment_w = np.zeros_like(weights)
    second_moment_w = np.zeros_like(weights)
    first_moment_b = np.zeros_like(bias)
    second_moment_b = np.zeros_like(bias)
    class_weights = _class_weights(y)
    best_weights = weights.copy()
    best_bias = bias.copy()
    best_epoch = 1
    best_loss = float("inf")
    stale = 0
    history: List[Dict[str, float]] = []
    beta1, beta2 = 0.9, 0.999
    for epoch in range(1, max(1, epochs) + 1):
        logits = x @ weights.T + bias
        probabilities = _softmax(logits)
        one_hot = np.eye(len(STATE_NAMES), dtype=np.float64)[y]
        sample_weights = class_weights[y]
        normalizer = max(sample_weights.sum(), 1e-12)
        grad_logits = (probabilities - one_hot) * sample_weights[:, None] / normalizer
        grad_w = grad_logits.T @ x + l2 * weights
        grad_b = grad_logits.sum(axis=0)
        first_moment_w = beta1 * first_moment_w + (1.0 - beta1) * grad_w
        second_moment_w = beta2 * second_moment_w + (1.0 - beta2) * (grad_w**2)
        first_moment_b = beta1 * first_moment_b + (1.0 - beta1) * grad_b
        second_moment_b = beta2 * second_moment_b + (1.0 - beta2) * (grad_b**2)
        correction1 = 1.0 - beta1**epoch
        correction2 = 1.0 - beta2**epoch
        weights -= learning_rate * (first_moment_w / correction1) / (
            np.sqrt(second_moment_w / correction2) + 1e-8
        )
        bias -= learning_rate * (first_moment_b / correction1) / (
            np.sqrt(second_moment_b / correction2) + 1e-8
        )
        train_loss = _loss(x, y, weights, bias, class_weights, l2)
        if validation is not None and len(validation[1]):
            validation_loss = _loss(
                validation[0],
                validation[1],
                weights,
                bias,
                _class_weights(validation[1]),
                l2,
            )
        else:
            validation_loss = train_loss
        history.append(
            {
                "epoch": float(epoch),
                "train_loss": round(train_loss, 8),
                "validation_loss": round(validation_loss, 8),
            }
        )
        if validation_loss < best_loss - 1e-7:
            best_loss = validation_loss
            best_weights = weights.copy()
            best_bias = bias.copy()
            best_epoch = epoch
            stale = 0
        else:
            stale += 1
        if validation is not None and stale >= patience:
            break
    return best_weights, best_bias, best_epoch, history


def _temperature(
    x: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    bias: np.ndarray,
) -> float:
    if not len(y):
        return 1.0
    logits = x @ weights.T + bias
    candidates = (0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 3.00)
    losses = []
    for candidate in candidates:
        probabilities = _softmax(logits, candidate)
        nll = -np.log(np.maximum(probabilities[np.arange(len(y)), y], 1e-12)).mean()
        losses.append((float(nll), candidate))
    return min(losses)[1]


def fit_softmax_classifier(
    training: tuple[np.ndarray, np.ndarray],
    validation: tuple[np.ndarray, np.ndarray] | None = None,
    *,
    epochs: int = 300,
    patience: int = 30,
    learning_rate: float = 0.03,
    l2: float = 1e-3,
    seed: int = 42,
    fixed_epochs: int | None = None,
    fixed_temperature: float | None = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    train_x, train_y = training
    mean = train_x.mean(axis=0)
    scale = train_x.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized_train = (train_x - mean) / scale
    standardized_validation = None
    if validation is not None:
        standardized_validation = ((validation[0] - mean) / scale, validation[1])
    optimize_epochs = fixed_epochs if fixed_epochs is not None else epochs
    weights, bias, best_epoch, history = _optimize(
        standardized_train,
        train_y,
        validation=standardized_validation if fixed_epochs is None else None,
        epochs=optimize_epochs,
        patience=patience,
        learning_rate=learning_rate,
        l2=l2,
        seed=seed,
    )
    if fixed_epochs is not None:
        best_epoch = fixed_epochs
    if fixed_temperature is not None:
        temperature = fixed_temperature
    elif standardized_validation is not None:
        temperature = _temperature(
            standardized_validation[0], standardized_validation[1], weights, bias
        )
    else:
        temperature = 1.0
    model = {
        "schema_version": MODEL_SCHEMA,
        "model_type": "class_weighted_multinomial_logistic_regression",
        "probability_method": "supervised_softmax_v1",
        "state_names": list(STATE_NAMES),
        "feature_names": list(EDGE_FEATURE_NAMES),
        "feature_mean": mean.tolist(),
        "feature_scale": scale.tolist(),
        "weights": weights.tolist(),
        "bias": bias.tolist(),
        "temperature": float(temperature),
        "training": {
            "epochs": int(best_epoch),
            "learning_rate": float(learning_rate),
            "l2": float(l2),
            "class_counts": np.bincount(train_y, minlength=len(STATE_NAMES)).tolist(),
        },
    }
    return model, {"best_epoch": best_epoch, "history": history}


def predict_probabilities(model: Mapping[str, Any], x: np.ndarray) -> np.ndarray:
    mean = np.asarray(model["feature_mean"], dtype=np.float64)
    scale = np.asarray(model["feature_scale"], dtype=np.float64)
    weights = np.asarray(model["weights"], dtype=np.float64)
    bias = np.asarray(model["bias"], dtype=np.float64)
    standardized = (x - mean) / np.maximum(scale, 1e-12)
    return _softmax(
        standardized @ weights.T + bias,
        float(model.get("temperature", 1.0)),
    )


def classification_metrics(
    model: Mapping[str, Any], x: np.ndarray, y: np.ndarray
) -> Dict[str, Any]:
    probabilities = predict_probabilities(model, x)
    predicted = probabilities.argmax(axis=1)
    recalls = []
    for state in range(len(STATE_NAMES)):
        mask = y == state
        recalls.append(float((predicted[mask] == state).mean()) if mask.any() else None)
    one_hot = np.eye(len(STATE_NAMES), dtype=np.float64)[y]
    return {
        "samples": int(len(y)),
        "accuracy": round(float((predicted == y).mean()), 6),
        "negative_log_likelihood": round(
            float(-np.log(np.maximum(probabilities[np.arange(len(y)), y], 1e-12)).mean()),
            6,
        ),
        "brier": round(float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))), 6),
        "recall_by_state": {
            name: round(value, 6) if value is not None else None
            for name, value in zip(STATE_NAMES, recalls)
        },
        "class_counts": {
            name: int((y == index).sum()) for index, name in enumerate(STATE_NAMES)
        },
    }


def _folds(
    cases: Sequence[Mapping[str, Any]], fold_count: int, seed: int
) -> List[List[int]]:
    if len(cases) < 2:
        raise ValueError("at least two labeled cases are required")
    groups: Dict[str, List[int]] = defaultdict(list)
    for index, case in enumerate(cases):
        groups[str(case["group_key"])].append(index)
    if len(groups) < 2:
        raise ValueError("P4 grouped cross-validation requires at least two incident groups")
    ordered = list(groups.items())
    random.Random(seed).shuffle(ordered)
    ordered.sort(key=lambda item: -len(item[1]))
    buckets: List[List[int]] = [
        [] for _ in range(min(max(2, fold_count), len(ordered)))
    ]
    for _key, indices in ordered:
        target = min(range(len(buckets)), key=lambda idx: (len(buckets[idx]), idx))
        buckets[target].extend(indices)
    return [sorted(bucket) for bucket in buckets if bucket]


def _inner_split(
    cases: Sequence[Mapping[str, Any]], indices: Sequence[int], seed: int
) -> tuple[List[int], List[int]]:
    groups: Dict[str, List[int]] = defaultdict(list)
    for index in indices:
        groups[str(cases[index]["group_key"])].append(index)
    ordered = list(groups.items())
    random.Random(seed).shuffle(ordered)
    if len(ordered) < 2:
        return sorted(indices), []
    validation_target = max(1, round(len(indices) * 0.20))
    validation: List[int] = []
    training: List[int] = []
    for position, (_key, group_indices) in enumerate(ordered):
        if len(validation) < validation_target and position < len(ordered) - 1:
            validation.extend(group_indices)
        else:
            training.extend(group_indices)
    return sorted(training), sorted(validation)


def _model_id(model: Mapping[str, Any], prefix: str) -> str:
    content = json.dumps(
        {key: model[key] for key in ("weights", "bias", "feature_mean", "feature_scale")},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(content).hexdigest()[:12]}"


def _save_model(model: Dict[str, Any], path: str, prefix: str) -> str:
    model = dict(model)
    model["model_id"] = _model_id(model, prefix)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    save_json(model, path, indent=2)
    return os.path.abspath(path)


def run_crossval(args: argparse.Namespace) -> str:
    config = PropagationConfig(
        max_candidate_nodes=args.max_candidate_nodes,
        max_path_depth=args.max_path_depth,
    )
    cases, diagnostics = collect_labeled_cases(
        args.data_root,
        args.labels_root,
        config=config,
        augment_orientation=not args.no_orientation_augmentation,
    )
    folds = _folds(cases, args.folds, args.seed)
    os.makedirs(args.output_dir, exist_ok=True)
    fold_dir = os.path.join(args.output_dir, "folds")
    os.makedirs(fold_dir, exist_ok=True)
    all_indices = set(range(len(cases)))
    case_models: Dict[str, str] = {}
    fold_rows = []
    selected_epochs = []
    selected_temperatures = []
    for fold_number, test_indices in enumerate(folds, 1):
        outer_train = sorted(all_indices - set(test_indices))
        inner_train, inner_validation = _inner_split(
            cases, outer_train, args.seed + fold_number
        )
        if inner_validation:
            selection_model, selection = fit_softmax_classifier(
                _join_cases([cases[index] for index in inner_train]),
                _join_cases([cases[index] for index in inner_validation]),
                epochs=args.epochs,
                patience=args.patience,
                learning_rate=args.learning_rate,
                l2=args.l2,
                seed=args.seed + fold_number,
            )
            best_epoch = int(selection["best_epoch"])
            temperature = float(selection_model["temperature"])
        else:
            best_epoch = args.epochs
            temperature = 1.0
        fold_model, _ = fit_softmax_classifier(
            _join_cases([cases[index] for index in outer_train]),
            fixed_epochs=best_epoch,
            fixed_temperature=temperature,
            epochs=args.epochs,
            patience=args.patience,
            learning_rate=args.learning_rate,
            l2=args.l2,
            seed=args.seed + 1000 + fold_number,
        )
        model_path = _save_model(
            fold_model,
            os.path.join(fold_dir, f"fold_{fold_number}.json"),
            f"p4-fold-{fold_number}",
        )
        test_x, test_y = _join_cases([cases[index] for index in test_indices])
        metrics = classification_metrics(fold_model, test_x, test_y)
        for index in test_indices:
            case_models[os.path.abspath(cases[index]["dirpath"])] = model_path
        selected_epochs.append(best_epoch)
        selected_temperatures.append(temperature)
        fold_rows.append(
            {
                "fold": fold_number,
                "outer_train_cases": len(outer_train),
                "inner_train_cases": len(inner_train),
                "inner_validation_cases": len(inner_validation),
                "test_cases": len(test_indices),
                "selected_epochs": best_epoch,
                "selected_temperature": temperature,
                "test_metrics": metrics,
                "model": model_path,
            }
        )
        print(json.dumps(fold_rows[-1], ensure_ascii=False))

    final_epochs = max(1, int(statistics.median(selected_epochs)))
    final_temperature = float(statistics.median(selected_temperatures))
    final_model, _ = fit_softmax_classifier(
        _join_cases(cases),
        fixed_epochs=final_epochs,
        fixed_temperature=final_temperature,
        epochs=args.epochs,
        patience=args.patience,
        learning_rate=args.learning_rate,
        l2=args.l2,
        seed=args.seed + 10_000,
    )
    final_path = _save_model(
        final_model, os.path.join(args.output_dir, "final_model.json"), "p4-final"
    )
    oof_case_paths = set(case_models)
    runtime_case_dirs = _discover_case_dirs(args.data_root)
    for dirpath in runtime_case_dirs:
        # Cases without usable path labels are not part of P4 training, so the
        # model trained on all labeled cases is leakage-safe for them.
        case_models.setdefault(os.path.abspath(dirpath), final_path)
    case_id_counts = Counter(
        os.path.basename(os.path.normpath(dirpath)) for dirpath in runtime_case_dirs
    )
    case_id_models = {
        os.path.basename(os.path.normpath(dirpath)): case_models[os.path.abspath(dirpath)]
        for dirpath in runtime_case_dirs
        if case_id_counts[os.path.basename(os.path.normpath(dirpath))] == 1
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "probability_method": "supervised_softmax_v1",
        "evaluation_mode": "out_of_fold",
        "split_unit": "source_sink_alarm_az_incident_group",
        "incident_group_count": len({case["group_key"] for case in cases}),
        "case_models": case_models,
        "case_id_models": case_id_models,
        "oof_labeled_case_count": len(oof_case_paths),
        "final_model_unlabeled_case_count": len(case_models) - len(oof_case_paths),
        "folds": fold_rows,
        "final_model": final_path,
        "final_training_epochs": final_epochs,
        "final_temperature": final_temperature,
        "dataset_diagnostics": diagnostics,
    }
    manifest_path = os.path.join(args.output_dir, "oof_manifest.json")
    save_json(manifest, manifest_path, indent=2)
    save_json(
        {
            "schema_version": MANIFEST_SCHEMA,
            "case_count": len(cases),
            "fold_count": len(folds),
            "folds": fold_rows,
            "final_model": final_path,
            "oof_manifest": os.path.abspath(manifest_path),
            "dataset_diagnostics": diagnostics,
        },
        os.path.join(args.output_dir, "training_summary.json"),
        indent=2,
    )
    print(f"OOF manifest: {os.path.abspath(manifest_path)}")
    print(f"Final model: {final_path}")
    return os.path.abspath(manifest_path)


def run_train(args: argparse.Namespace) -> str:
    cases, diagnostics = collect_labeled_cases(
        args.data_root,
        args.labels_root,
        config=PropagationConfig(
            max_candidate_nodes=args.max_candidate_nodes,
            max_path_depth=args.max_path_depth,
        ),
        augment_orientation=not args.no_orientation_augmentation,
    )
    train_indices, validation_indices = _inner_split(
        cases, list(range(len(cases))), args.seed
    )
    if validation_indices:
        selection_model, selection = fit_softmax_classifier(
            _join_cases([cases[index] for index in train_indices]),
            _join_cases([cases[index] for index in validation_indices]),
            epochs=args.epochs,
            patience=args.patience,
            learning_rate=args.learning_rate,
            l2=args.l2,
            seed=args.seed,
        )
        selected_epochs = int(selection["best_epoch"])
        temperature = float(selection_model["temperature"])
    else:
        selected_epochs = args.epochs
        temperature = 1.0
    model, _ = fit_softmax_classifier(
        _join_cases(cases),
        fixed_epochs=selected_epochs,
        fixed_temperature=temperature,
        epochs=args.epochs,
        patience=args.patience,
        learning_rate=args.learning_rate,
        l2=args.l2,
        seed=args.seed + 10_000,
    )
    model["dataset_diagnostics"] = diagnostics
    checkpoint = _save_model(model, args.checkpoint, "p4-final")
    print(json.dumps({"checkpoint": checkpoint, "diagnostics": diagnostics}, ensure_ascii=False, indent=2))
    return checkpoint


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--labels-root", required=True)
    parser.add_argument("--max-candidate-nodes", type=int, default=80)
    parser.add_argument("--max-path-depth", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--learning-rate", type=float, default=0.03)
    parser.add_argument("--l2", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-orientation-augmentation", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train the P4 three-state supervised Stage 2 edge classifier."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    crossval = subparsers.add_parser(
        "crossval", help="Train case-grouped OOF models and one final model."
    )
    _add_common_args(crossval)
    crossval.add_argument("--output-dir", required=True)
    crossval.add_argument("--folds", type=int, default=5)
    train = subparsers.add_parser("train", help="Train one final JSON model.")
    _add_common_args(train)
    train.add_argument("--checkpoint", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "crossval":
        run_crossval(args)
    elif args.command == "train":
        run_train(args)


if __name__ == "__main__":
    main()
