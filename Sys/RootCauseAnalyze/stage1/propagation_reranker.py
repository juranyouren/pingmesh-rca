from __future__ import annotations

import copy
import math
import os
import random
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError as exc:  # pragma: no cover - exercised on the training server
    raise RuntimeError(
        "The propagation-conditioned root reranker requires PyTorch."
    ) from exc


CHECKPOINT_FORMAT = "propagation-statistical-listwise-reranker-v1"

FEATURE_NAMES = (
    "stage1_probability",
    "stage1_log_probability",
    "stage1_logit_gap_from_top1",
    "reciprocal_initial_rank",
    "explanation_score",
    "graph_score",
    "target_coverage",
    "empty_graph",
    "selected_edge_count_log",
    "selected_node_count_log",
    "supported_edge_ratio",
    "grounded_edge_ratio",
    "weak_edge_ratio",
    "contradiction_score",
    "mean_edge_probability",
    "min_edge_probability",
    "mean_direction_no_direct_margin",
    "min_direction_no_direct_margin",
    "mean_path_score",
    "min_path_score",
    "mean_path_length",
    "max_path_length",
    "root_evidence_count_log",
    "root_onset_available",
    "reachable_target_ratio",
    "path_candidate_count_log",
)


@dataclass(frozen=True)
class RerankerModelConfig:
    hidden_dim: int = 16
    dropout: float = 0.20
    correction_scale: float = 1.0
    feature_set: str = "all"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RerankerTrainingConfig:
    epochs: int = 100
    patience: int = 15
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    gradient_clip: float = 2.0
    seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RerankerExample:
    dirpath: str
    candidates: List[Dict[str, Any]]
    gt_ip: str | None = None
    diagnostics: Dict[str, Any] | None = None

    @property
    def target_position(self) -> int | None:
        if not self.gt_ip:
            return None
        for index, candidate in enumerate(self.candidates):
            if str(candidate.get("ip", "")) == self.gt_ip:
                return index
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _safe_log_probability(value: Any) -> float:
    return math.log(max(min(_safe_float(value), 1.0), 1e-8))


def _mean(values: Sequence[float], default: float = 0.0) -> float:
    return sum(values) / len(values) if values else default


def _root_ip(root_hypothesis: Mapping[str, Any]) -> str:
    devices = root_hypothesis.get("root_devices", [])
    if isinstance(devices, list):
        for value in devices:
            if value:
                return str(value)
    return ""


def _original_ranking_by_ip(
    rankings: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for index, raw in enumerate(rankings, 1):
        if not isinstance(raw, Mapping):
            continue
        ip = str(raw.get("ip", raw.get("device_id", "")) or "")
        if not ip or ip in result:
            continue
        probability = _safe_float(
            raw.get(
                "combined_score",
                raw.get("neural_score", raw.get("score", 1.0 / index)),
            ),
            1.0 / index,
        )
        probability = max(0.0, min(1.0, probability))
        logit = _safe_float(raw.get("logit"), _safe_log_probability(probability))
        result[ip] = {
            **dict(raw),
            "rank": int(raw.get("rank", index) or index),
            "probability": probability,
            "logit": logit,
        }
    return result


def extract_candidate_rows(
    *,
    hypothesis_graph: Mapping[str, Any],
    root_conditioned_graphs: Sequence[Mapping[str, Any]],
    initial_root_rankings: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Extract one auditable statistical vector for every candidate root graph."""

    initial_by_ip = _original_ranking_by_ip(initial_root_rankings)
    top_logit = max(
        (_safe_float(item.get("logit")) for item in initial_by_ip.values()),
        default=0.0,
    )
    no_direct_by_hypothesis = {
        str(pair.get("edge_hypothesis_id", "")): _safe_float(
            pair.get("state_probabilities", {}).get("no_direct_propagation", 0.0)
        )
        for pair in hypothesis_graph.get("edge_hypotheses", [])
        if isinstance(pair, Mapping)
        and isinstance(pair.get("state_probabilities", {}), Mapping)
    }

    rows: List[Dict[str, Any]] = []
    for fallback_rank, raw_item in enumerate(root_conditioned_graphs, 1):
        if not isinstance(raw_item, Mapping):
            continue
        root = raw_item.get("root_hypothesis", {})
        graph = raw_item.get("propagation_graph", {})
        if not isinstance(root, Mapping) or not isinstance(graph, Mapping):
            continue
        ip = _root_ip(root)
        if not ip:
            continue
        original = initial_by_ip.get(ip, {})
        initial_rank = int(
            original.get("rank", root.get("rank", fallback_rank)) or fallback_rank
        )
        stage1_probability = _safe_float(
            original.get("probability", root.get("support_score", 1.0 / initial_rank))
        )
        stage1_probability = max(0.0, min(1.0, stage1_probability))
        stage1_logit = _safe_float(
            original.get("logit"), _safe_log_probability(stage1_probability)
        )

        edges = [
            edge for edge in graph.get("edges", []) if isinstance(edge, Mapping)
        ]
        nodes = [
            node for node in graph.get("nodes", []) if isinstance(node, Mapping)
        ]
        diagnostics = (
            graph.get("diagnostics", {})
            if isinstance(graph.get("diagnostics", {}), Mapping)
            else {}
        )
        edge_probabilities = [
            _safe_float(edge.get("state_probability", edge.get("support_score", 0.0)))
            for edge in edges
        ]
        direction_margins = [
            _safe_float(edge.get("state_probability", edge.get("support_score", 0.0)))
            - no_direct_by_hypothesis.get(
                str(edge.get("edge_hypothesis_id", "")), 0.0
            )
            for edge in edges
        ]

        paths = [
            path
            for path in graph.get("ranked_chains", [])
            if isinstance(path, Mapping)
        ]
        path_scores = [_safe_float(path.get("score", 0.0)) for path in paths]
        path_lengths = [
            max(0.0, float(len(path.get("devices", [])) - 1))
            for path in paths
            if isinstance(path.get("devices", []), list)
        ]
        root_node = next(
            (
                node
                for node in nodes
                if str(node.get("device_id", "")) == ip
                or str(node.get("role", "")) in {"root", "root_endpoint"}
            ),
            {},
        )
        root_evidence = root_node.get("evidence_ids", [])
        root_evidence_count = len(root_evidence) if isinstance(root_evidence, list) else 0
        target_count = int(diagnostics.get("target_count", 0) or 0)
        reachable_target_count = int(
            diagnostics.get("reachable_target_count", len(graph.get("covered_targets", [])))
            or 0
        )

        values = {
            "stage1_probability": stage1_probability,
            "stage1_log_probability": _safe_log_probability(stage1_probability),
            "stage1_logit_gap_from_top1": stage1_logit - top_logit,
            "reciprocal_initial_rank": 1.0 / max(initial_rank, 1),
            "explanation_score": _safe_float(raw_item.get("explanation_score", 0.0)),
            "graph_score": _safe_float(graph.get("graph_score", 0.0)),
            "target_coverage": _safe_float(graph.get("target_coverage", 0.0)),
            "empty_graph": float(not edges),
            "selected_edge_count_log": math.log1p(len(edges)),
            "selected_node_count_log": math.log1p(len(nodes)),
            "supported_edge_ratio": _safe_float(
                diagnostics.get("supported_edge_ratio", 0.0)
            ),
            "grounded_edge_ratio": _safe_float(
                diagnostics.get("grounded_edge_ratio", 0.0)
            ),
            "weak_edge_ratio": _safe_float(diagnostics.get("weak_edge_ratio", 0.0)),
            "contradiction_score": _safe_float(
                diagnostics.get("contradiction_score", 0.0)
            ),
            "mean_edge_probability": _mean(edge_probabilities),
            "min_edge_probability": min(edge_probabilities, default=0.0),
            "mean_direction_no_direct_margin": _mean(direction_margins),
            "min_direction_no_direct_margin": min(direction_margins, default=0.0),
            "mean_path_score": _mean(path_scores),
            "min_path_score": min(path_scores, default=0.0),
            "mean_path_length": _mean(path_lengths),
            "max_path_length": max(path_lengths, default=0.0),
            "root_evidence_count_log": math.log1p(root_evidence_count),
            "root_onset_available": float(
                isinstance(root_node.get("onset_interval_ms"), list)
                and len(root_node.get("onset_interval_ms", [])) == 2
            ),
            "reachable_target_ratio": (
                reachable_target_count / target_count if target_count else 0.0
            ),
            "path_candidate_count_log": math.log1p(
                int(diagnostics.get("path_candidate_count", 0) or 0)
            ),
        }
        rows.append(
            {
                "ip": ip,
                "initial_rank": initial_rank,
                "stage1_probability": stage1_probability,
                "stage1_logit": stage1_logit,
                "features": [float(values[name]) for name in FEATURE_NAMES],
                "feature_values": values,
            }
        )
    return sorted(rows, key=lambda row: (int(row["initial_rank"]), str(row["ip"])))


class StatisticalListwiseReranker(nn.Module):
    """Small residual MLP that scores all candidate roots within one incident."""

    def __init__(self, config: RerankerModelConfig):
        super().__init__()
        if config.hidden_dim <= 0:
            raise ValueError("reranker hidden_dim must be positive")
        if not 0.0 <= config.dropout < 1.0:
            raise ValueError("reranker dropout must be within [0, 1)")
        if config.correction_scale < 0.0:
            raise ValueError("reranker correction_scale must be non-negative")
        if config.feature_set not in {"all", "stage1_only", "graph_only"}:
            raise ValueError(
                "reranker feature_set must be all, stage1_only, or graph_only"
            )
        self.config = config
        if config.feature_set == "stage1_only":
            mask = [float(index < 4) for index in range(len(FEATURE_NAMES))]
        elif config.feature_set == "graph_only":
            mask = [float(index >= 4) for index in range(len(FEATURE_NAMES))]
        else:
            mask = [1.0] * len(FEATURE_NAMES)
        self.register_buffer("feature_mask", torch.tensor(mask, dtype=torch.float32))
        self.network = nn.Sequential(
            nn.Linear(len(FEATURE_NAMES), config.hidden_dim),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_dim, 1),
        )
        # The initial model is exactly the Stage-1 ranking. This makes the
        # learned graph branch a conservative residual correction.
        nn.init.zeros_(self.network[-1].weight)
        nn.init.zeros_(self.network[-1].bias)

    def forward(
        self, features: torch.Tensor, stage1_logits: torch.Tensor
    ) -> torch.Tensor:
        correction = self.network(features * self.feature_mask).squeeze(-1)
        return stage1_logits + float(self.config.correction_scale) * correction


def fit_standardizer(
    examples: Sequence[RerankerExample],
) -> Tuple[List[float], List[float]]:
    rows = [
        [float(value) for value in candidate.get("features", [])]
        for example in examples
        for candidate in example.candidates
        if len(candidate.get("features", [])) == len(FEATURE_NAMES)
    ]
    if not rows:
        raise ValueError("cannot fit reranker standardizer without candidate features")
    means = [sum(row[index] for row in rows) / len(rows) for index in range(len(FEATURE_NAMES))]
    variances = [
        sum((row[index] - means[index]) ** 2 for row in rows) / len(rows)
        for index in range(len(FEATURE_NAMES))
    ]
    scales = [max(math.sqrt(value), 1e-6) for value in variances]
    return means, scales


def _example_tensors(
    example: RerankerExample,
    feature_mean: Sequence[float],
    feature_scale: Sequence[float],
    device: torch.device,
) -> Tuple[torch.Tensor, torch.Tensor]:
    features = [
        [
            (float(value) - float(center)) / max(float(scale), 1e-6)
            for value, center, scale in zip(
                candidate["features"], feature_mean, feature_scale
            )
        ]
        for candidate in example.candidates
    ]
    stage1_logits = [
        _safe_float(candidate.get("stage1_logit"), _safe_log_probability(candidate.get("stage1_probability")))
        for candidate in example.candidates
    ]
    return (
        torch.tensor(features, dtype=torch.float32, device=device),
        torch.tensor(stage1_logits, dtype=torch.float32, device=device),
    )


@torch.no_grad()
def predict_example(
    model: StatisticalListwiseReranker,
    example: RerankerExample,
    feature_mean: Sequence[float],
    feature_scale: Sequence[float],
    device: torch.device,
) -> List[Dict[str, Any]]:
    model.eval()
    features, base_logits = _example_tensors(
        example, feature_mean, feature_scale, device
    )
    final_logits = model(features, base_logits)
    probabilities = torch.softmax(final_logits, dim=0)
    order = torch.argsort(final_logits, descending=True).tolist()
    result: List[Dict[str, Any]] = []
    for final_rank, position in enumerate(order, 1):
        candidate = example.candidates[int(position)]
        final_logit = float(final_logits[int(position)])
        base_logit = float(base_logits[int(position)])
        result.append(
            {
                "rank": final_rank,
                "ip": str(candidate.get("ip", "")),
                "initial_rank": int(candidate.get("initial_rank", position + 1)),
                "stage1_score": round(
                    _safe_float(candidate.get("stage1_probability", 0.0)), 8
                ),
                "stage1_logit": round(base_logit, 8),
                "reranker_logit": round(final_logit, 8),
                "reranker_delta": round(final_logit - base_logit, 8),
                "combined_score": round(float(probabilities[int(position)]), 8),
                "neural_score": round(float(probabilities[int(position)]), 8),
            }
        )
    return result


def evaluate_reranker(
    model: StatisticalListwiseReranker,
    examples: Sequence[RerankerExample],
    feature_mean: Sequence[float],
    feature_scale: Sequence[float],
    device: torch.device,
) -> Dict[str, Any]:
    labeled = [example for example in examples if example.gt_ip]
    if not labeled:
        return {"case_count": 0, "candidate_recall": 0.0}
    eligible = 0
    initial_top1 = 0
    final_top1 = 0
    final_top3 = 0
    final_top5 = 0
    reciprocal_rank = 0.0
    conditional_reciprocal_rank = 0.0
    corrections = 0
    corruptions = 0
    nll = 0.0
    brier = 0.0
    model.eval()
    with torch.no_grad():
        for example in labeled:
            target = example.target_position
            initial_correct = bool(
                example.candidates
                and str(example.candidates[0].get("ip", "")) == example.gt_ip
            )
            initial_top1 += int(initial_correct)
            if target is None:
                continue
            eligible += 1
            features, base_logits = _example_tensors(
                example, feature_mean, feature_scale, device
            )
            logits = model(features, base_logits)
            probabilities = torch.softmax(logits, dim=0)
            order = torch.argsort(logits, descending=True).tolist()
            rank = order.index(target) + 1
            final_correct = rank == 1
            final_top1 += int(final_correct)
            final_top3 += int(rank <= 3)
            final_top5 += int(rank <= 5)
            reciprocal_rank += 1.0 / rank
            conditional_reciprocal_rank += 1.0 / rank
            corrections += int(not initial_correct and final_correct)
            corruptions += int(initial_correct and not final_correct)
            probability = float(probabilities[target])
            nll += -math.log(max(probability, 1e-12))
            one_hot = torch.zeros_like(probabilities)
            one_hot[target] = 1.0
            brier += float(torch.mean((probabilities - one_hot) ** 2))
    total = len(labeled)
    return {
        "case_count": total,
        "eligible_case_count": eligible,
        "candidate_recall": round(eligible / total, 6),
        "initial_top1": round(initial_top1 / total, 6),
        "final_top1": round(final_top1 / total, 6),
        "final_top3": round(final_top3 / total, 6),
        "final_top5": round(final_top5 / total, 6),
        "mrr": round(reciprocal_rank / total, 6),
        "conditional_top1": round(final_top1 / eligible, 6) if eligible else 0.0,
        "conditional_mrr": (
            round(conditional_reciprocal_rank / eligible, 6) if eligible else 0.0
        ),
        "corrections": corrections,
        "corruptions": corruptions,
        "net_corrections": corrections - corruptions,
        "conditional_nll": round(nll / eligible, 6) if eligible else 0.0,
        "conditional_brier": round(brier / eligible, 6) if eligible else 0.0,
    }


def _validation_loss(
    model: StatisticalListwiseReranker,
    examples: Sequence[RerankerExample],
    feature_mean: Sequence[float],
    feature_scale: Sequence[float],
    device: torch.device,
) -> float:
    losses = []
    model.eval()
    with torch.no_grad():
        for example in examples:
            target = example.target_position
            if target is None:
                continue
            features, base_logits = _example_tensors(
                example, feature_mean, feature_scale, device
            )
            logits = model(features, base_logits)
            losses.append(
                float(
                    F.cross_entropy(
                        logits.unsqueeze(0),
                        torch.tensor([target], dtype=torch.long, device=device),
                    )
                )
            )
    return _mean(losses, float("inf"))


def train_reranker(
    training_examples: Sequence[RerankerExample],
    validation_examples: Sequence[RerankerExample],
    *,
    model_config: RerankerModelConfig,
    training_config: RerankerTrainingConfig,
    device: torch.device,
    fixed_epochs: int | None = None,
) -> Tuple[
    StatisticalListwiseReranker,
    List[float],
    List[float],
    int,
    List[Dict[str, float]],
]:
    eligible_training = [
        example for example in training_examples if example.target_position is not None
    ]
    if not eligible_training:
        raise ValueError("no training incident has its labeled root in the candidate set")
    feature_mean, feature_scale = fit_standardizer(training_examples)
    random.seed(training_config.seed)
    torch.manual_seed(training_config.seed)
    model = StatisticalListwiseReranker(model_config).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=training_config.learning_rate,
        weight_decay=training_config.weight_decay,
    )
    maximum_epochs = max(1, int(fixed_epochs or training_config.epochs))
    best_state = copy.deepcopy(model.state_dict())
    best_epoch = 1
    best_loss = float("inf")
    stale = 0
    history: List[Dict[str, float]] = []
    rng = random.Random(training_config.seed)

    for epoch in range(1, maximum_epochs + 1):
        order = list(range(len(eligible_training)))
        rng.shuffle(order)
        model.train()
        total_loss = 0.0
        optimizer.zero_grad(set_to_none=True)
        for position in order:
            example = eligible_training[position]
            target = int(example.target_position or 0)
            features, base_logits = _example_tensors(
                example, feature_mean, feature_scale, device
            )
            logits = model(features, base_logits)
            loss = F.cross_entropy(
                logits.unsqueeze(0),
                torch.tensor([target], dtype=torch.long, device=device),
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                model.parameters(), training_config.gradient_clip
            )
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            total_loss += float(loss.detach())
        train_loss = total_loss / len(eligible_training)
        validation_loss = (
            _validation_loss(
                model,
                validation_examples,
                feature_mean,
                feature_scale,
                device,
            )
            if validation_examples
            else train_loss
        )
        if not math.isfinite(validation_loss):
            validation_loss = train_loss
        history.append(
            {
                "epoch": float(epoch),
                "train_loss": round(train_loss, 8),
                "validation_loss": round(validation_loss, 8),
            }
        )
        if fixed_epochs is not None:
            continue
        if validation_loss < best_loss - 1e-8:
            best_loss = validation_loss
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            stale = 0
        else:
            stale += 1
            if stale >= max(1, training_config.patience):
                break

    if fixed_epochs is not None:
        best_epoch = maximum_epochs
        best_state = copy.deepcopy(model.state_dict())
    model.load_state_dict(best_state)
    return model, feature_mean, feature_scale, best_epoch, history


def save_checkpoint(
    path: str,
    *,
    model: StatisticalListwiseReranker,
    feature_mean: Sequence[float],
    feature_scale: Sequence[float],
    model_config: RerankerModelConfig,
    training_config: RerankerTrainingConfig,
    metadata: Mapping[str, Any],
) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    torch.save(
        {
            "format_version": CHECKPOINT_FORMAT,
            "model_state": model.state_dict(),
            "feature_names": list(FEATURE_NAMES),
            "feature_mean": list(feature_mean),
            "feature_scale": list(feature_scale),
            "model_config": model_config.to_dict(),
            "training_config": training_config.to_dict(),
            "metadata": dict(metadata),
        },
        path,
    )


def load_checkpoint(
    path: str, device: torch.device
) -> Tuple[StatisticalListwiseReranker, Dict[str, Any]]:
    try:
        payload = torch.load(path, map_location=device, weights_only=False)
    except TypeError:  # pragma: no cover - torch < 2.6
        payload = torch.load(path, map_location=device)
    if payload.get("format_version") != CHECKPOINT_FORMAT:
        raise ValueError("unsupported propagation reranker checkpoint")
    if tuple(payload.get("feature_names", [])) != FEATURE_NAMES:
        raise ValueError("propagation reranker feature contract does not match runtime")
    for key in ("feature_mean", "feature_scale"):
        if len(payload.get(key, [])) != len(FEATURE_NAMES):
            raise ValueError(f"propagation reranker {key} has an invalid shape")
    model = StatisticalListwiseReranker(
        RerankerModelConfig(**payload["model_config"])
    ).to(device)
    model.load_state_dict(payload["model_state"])
    model.eval()
    return model, dict(payload)


def serialize_examples(examples: Iterable[RerankerExample]) -> List[Dict[str, Any]]:
    return [
        {
            "dir": example.dirpath,
            "gt_ip": example.gt_ip,
            "target_position": example.target_position,
            "candidates": [dict(candidate) for candidate in example.candidates],
            "diagnostics": dict(example.diagnostics or {}),
        }
        for example in examples
    ]


__all__ = [
    "CHECKPOINT_FORMAT",
    "FEATURE_NAMES",
    "RerankerExample",
    "RerankerModelConfig",
    "RerankerTrainingConfig",
    "StatisticalListwiseReranker",
    "evaluate_reranker",
    "extract_candidate_rows",
    "fit_standardizer",
    "load_checkpoint",
    "predict_example",
    "save_checkpoint",
    "serialize_examples",
    "train_reranker",
]
