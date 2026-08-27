from __future__ import annotations

import copy
import random
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError as exc:  # pragma: no cover - exercised on the training server
    raise RuntimeError(
        "Self-supervised PC-STGR requires PyTorch. Install the server's "
        "torch/torch-npu build or use the supervised PC-STGR pipeline instead."
    ) from exc

from Sys.RootCauseAnalyze.stage1.neural_graph import (
    NODE_EVENT,
    NODE_FEATURE_DIM,
    NODE_TYPE_COUNT,
    NODE_TYPE_FEATURE_DIM,
    RELATION_COUNT,
    PathConditionedGraph,
)
from Sys.RootCauseAnalyze.stage1.neural_model import (
    NeuralModelConfig,
    RelationalTemporalAttention,
    TrainingConfig,
    _rank_metrics,
    graph_to_tensors,
    resolve_device,
    set_seed,
)


CHECKPOINT_FORMAT = "pc-stgr-ssl-stage1-v1"


@dataclass(frozen=True)
class PretrainingConfig:
    epochs: int = 40
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    gradient_accumulation: int = 8
    gradient_clip: float = 2.0
    token_mask_rate: float = 0.25
    feature_mask_rate: float = 0.20
    edge_drop_rate: float = 0.15
    token_loss_weight: float = 1.0
    feature_loss_weight: float = 1.0
    edge_loss_weight: float = 1.0
    seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def validate(self) -> None:
        if self.epochs < 1:
            raise ValueError("pretraining epochs must be positive")
        if self.learning_rate <= 0.0:
            raise ValueError("pretraining learning rate must be positive")
        if self.weight_decay < 0.0:
            raise ValueError("pretraining weight decay must be non-negative")
        if self.gradient_accumulation < 1:
            raise ValueError("pretraining gradient accumulation must be positive")
        if self.gradient_clip <= 0.0:
            raise ValueError("pretraining gradient clip must be positive")
        for name in ("token_mask_rate", "feature_mask_rate", "edge_drop_rate"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1]")
        for name in (
            "token_loss_weight",
            "feature_loss_weight",
            "edge_loss_weight",
        ):
            if float(getattr(self, name)) < 0.0:
                raise ValueError(f"{name} must be non-negative")
        active_objectives = (
            self.token_loss_weight > 0.0 and self.token_mask_rate > 0.0,
            self.feature_loss_weight > 0.0 and self.feature_mask_rate > 0.0,
            self.edge_loss_weight > 0.0 and self.edge_drop_rate > 0.0,
        )
        if not any(active_objectives):
            raise ValueError("at least one self-supervised objective must be active")


class SelfSupervisedPathConditionedGraphRanker(nn.Module):
    """A separate PC-STGR variant with auxiliary pretraining heads.

    The encoder and root-ranking head intentionally mirror the supervised
    PC-STGR network. The original ``PathConditionedGraphRanker`` remains
    unchanged; these reconstruction heads are used only during pretraining.
    """

    def __init__(self, vocabulary_size: int, config: NeuralModelConfig):
        super().__init__()
        if config.event_embedding_dim <= 0:
            raise ValueError("event_embedding_dim must be positive")
        self.config = config
        self.vocabulary_size = int(vocabulary_size)
        self.event_embedding = nn.Embedding(
            vocabulary_size,
            config.event_embedding_dim,
            padding_idx=0,
        )
        node_input_dim = (
            NODE_FEATURE_DIM
            + NODE_TYPE_FEATURE_DIM
            + config.event_embedding_dim
        )
        self.input_projection = nn.Sequential(
            nn.Linear(node_input_dim, config.hidden_dim),
            nn.GELU(),
            nn.LayerNorm(config.hidden_dim),
        )
        self.layers = nn.ModuleList(
            RelationalTemporalAttention(config) for _ in range(config.layers)
        )
        self.feed_forward = nn.ModuleList(
            nn.Sequential(
                nn.Linear(config.hidden_dim, config.hidden_dim * 2),
                nn.GELU(),
                nn.Dropout(config.dropout),
                nn.Linear(config.hidden_dim * 2, config.hidden_dim),
                nn.Dropout(config.dropout),
                nn.LayerNorm(config.hidden_dim),
            )
            for _ in range(config.layers)
        )
        self.root_head = nn.Sequential(
            nn.Linear(config.hidden_dim, config.hidden_dim),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_dim, 1),
        )
        self.token_reconstruction_head = nn.Linear(config.hidden_dim, vocabulary_size)
        self.feature_reconstruction_head = nn.Linear(config.hidden_dim, NODE_FEATURE_DIM)
        self.edge_reconstruction_head = nn.Sequential(
            nn.Linear(config.hidden_dim * 2, config.hidden_dim),
            nn.GELU(),
            nn.Linear(config.hidden_dim, RELATION_COUNT + 1),
        )

    def encode_nodes(self, batch: Mapping[str, torch.Tensor]) -> torch.Tensor:
        node_type_one_hot = F.one_hot(
            batch["node_types"], num_classes=NODE_TYPE_COUNT
        ).to(dtype=batch["node_features"].dtype)
        node_input = torch.cat(
            [
                batch["node_features"],
                node_type_one_hot,
                self.event_embedding(batch["token_ids"]),
            ],
            dim=-1,
        )
        hidden = self.input_projection(node_input)
        for attention, feed_forward in zip(self.layers, self.feed_forward):
            hidden = attention(
                hidden,
                batch["edge_sources"],
                batch["edge_targets"],
                batch["edge_types"],
                batch["edge_features"],
            )
            hidden = hidden + feed_forward(hidden)
        return hidden

    def forward(self, batch: Mapping[str, torch.Tensor]) -> torch.Tensor:
        hidden = self.encode_nodes(batch)
        return self.root_head(hidden[batch["device_indices"]]).squeeze(-1)

    def ranking_loss(self, logits: torch.Tensor, root_position: torch.Tensor) -> torch.Tensor:
        if root_position.numel() != 1 or int(root_position.item()) < 0:
            raise ValueError("training graph has no ground-truth device in the graph")
        return F.cross_entropy(logits.unsqueeze(0), root_position.reshape(1))


def _sample_at_least_one(
    candidates: Sequence[Any], rate: float, rng: random.Random
) -> List[Any]:
    if not candidates or rate <= 0.0:
        return []
    selected = [value for value in candidates if rng.random() < rate]
    if not selected:
        selected = [candidates[rng.randrange(len(candidates))]]
    return selected


def _negative_edges(
    node_types: Sequence[int],
    original_edges: Sequence[Tuple[int, int]],
    positive_edges: Sequence[Tuple[int, int]],
    rng: random.Random,
) -> List[Tuple[int, int]]:
    if len(node_types) < 2 or not positive_edges:
        return []
    occupied = set(original_edges)
    selected: set[Tuple[int, int]] = set()
    result: List[Tuple[int, int]] = []
    by_type: Dict[int, List[int]] = {}
    for index, node_type in enumerate(node_types):
        by_type.setdefault(int(node_type), []).append(index)

    for positive_source, positive_target in positive_edges:
        sources = by_type[int(node_types[positive_source])]
        targets = by_type[int(node_types[positive_target])]
        candidate = None
        for _attempt in range(64):
            pair = (rng.choice(sources), rng.choice(targets))
            if pair[0] != pair[1] and pair not in occupied and pair not in selected:
                candidate = pair
                break
        if candidate is None:
            for source in sources:
                for target in targets:
                    pair = (source, target)
                    if source != target and pair not in occupied and pair not in selected:
                        candidate = pair
                        break
                if candidate is not None:
                    break
        if candidate is not None:
            selected.add(candidate)
            result.append(candidate)
    return result


def corrupt_graph_batch(
    batch: Mapping[str, torch.Tensor],
    config: PretrainingConfig,
    *,
    seed: int,
) -> Tuple[Dict[str, torch.Tensor], Dict[str, torch.Tensor]]:
    """Create one deterministic corrupted view and its reconstruction targets."""

    config.validate()
    rng = random.Random(seed)
    corrupted = {key: value.clone() for key, value in batch.items()}
    device = batch["node_features"].device

    node_types = batch["node_types"].detach().cpu().tolist()
    token_ids = batch["token_ids"].detach().cpu().tolist()
    token_candidates = [
        index
        for index, (node_type, token_id) in enumerate(zip(node_types, token_ids))
        if node_type == NODE_EVENT and token_id > 1
    ]
    token_indices = _sample_at_least_one(token_candidates, config.token_mask_rate, rng)
    if token_indices:
        token_index_tensor = torch.tensor(token_indices, dtype=torch.long, device=device)
        token_targets = batch["token_ids"][token_index_tensor].clone()
        corrupted["token_ids"][token_index_tensor] = 1
    else:
        token_index_tensor = torch.empty(0, dtype=torch.long, device=device)
        token_targets = torch.empty(0, dtype=torch.long, device=device)

    raw_features = batch["node_features"].detach().cpu().tolist()
    feature_candidates = [
        (row_index, column_index)
        for row_index, row in enumerate(raw_features)
        for column_index, value in enumerate(row)
        if abs(float(value)) > 1e-12
    ]
    feature_positions = _sample_at_least_one(
        feature_candidates, config.feature_mask_rate, rng
    )
    feature_mask = torch.zeros_like(batch["node_features"], dtype=torch.bool)
    for row_index, column_index in feature_positions:
        feature_mask[row_index, column_index] = True
    feature_targets = batch["node_features"][feature_mask].clone()
    corrupted["node_features"][feature_mask] = 0.0

    edge_sources = batch["edge_sources"].detach().cpu().tolist()
    edge_targets = batch["edge_targets"].detach().cpu().tolist()
    edge_types = batch["edge_types"].detach().cpu().tolist()
    edge_indices = _sample_at_least_one(
        list(range(len(edge_sources))), config.edge_drop_rate, rng
    )
    edge_index_set = set(edge_indices)
    keep_indices = [index for index in range(len(edge_sources)) if index not in edge_index_set]
    keep_tensor = torch.tensor(keep_indices, dtype=torch.long, device=device)
    for key in ("edge_sources", "edge_targets", "edge_types", "edge_features"):
        corrupted[key] = batch[key][keep_tensor]

    positive_pairs = [(edge_sources[index], edge_targets[index]) for index in edge_indices]
    positive_labels = [edge_types[index] for index in edge_indices]
    negatives = _negative_edges(
        node_types,
        list(zip(edge_sources, edge_targets)),
        positive_pairs,
        rng,
    )
    edge_pairs = [*positive_pairs, *negatives]
    edge_labels = [*positive_labels, *([RELATION_COUNT] * len(negatives))]
    if edge_pairs:
        edge_pair_tensor = torch.tensor(edge_pairs, dtype=torch.long, device=device)
        edge_label_tensor = torch.tensor(edge_labels, dtype=torch.long, device=device)
    else:
        edge_pair_tensor = torch.empty((0, 2), dtype=torch.long, device=device)
        edge_label_tensor = torch.empty(0, dtype=torch.long, device=device)

    targets = {
        "token_indices": token_index_tensor,
        "token_targets": token_targets,
        "feature_mask": feature_mask,
        "feature_targets": feature_targets,
        "edge_pairs": edge_pair_tensor,
        "edge_labels": edge_label_tensor,
    }
    return corrupted, targets


def self_supervised_losses(
    model: SelfSupervisedPathConditionedGraphRanker,
    corrupted_batch: Mapping[str, torch.Tensor],
    targets: Mapping[str, torch.Tensor],
    config: PretrainingConfig,
) -> Dict[str, torch.Tensor]:
    hidden = model.encode_nodes(corrupted_batch)
    zero = hidden.sum() * 0.0

    token_indices = targets["token_indices"]
    token_loss = zero
    if token_indices.numel():
        token_logits = model.token_reconstruction_head(hidden[token_indices])
        token_loss = F.cross_entropy(token_logits, targets["token_targets"])

    feature_loss = zero
    feature_mask = targets["feature_mask"]
    if feature_mask.any():
        feature_predictions = model.feature_reconstruction_head(hidden)
        feature_loss = F.mse_loss(
            feature_predictions[feature_mask], targets["feature_targets"]
        )

    edge_loss = zero
    edge_pairs = targets["edge_pairs"]
    if edge_pairs.numel():
        pair_hidden = torch.cat(
            [hidden[edge_pairs[:, 0]], hidden[edge_pairs[:, 1]]], dim=-1
        )
        edge_logits = model.edge_reconstruction_head(pair_hidden)
        edge_loss = F.cross_entropy(edge_logits, targets["edge_labels"])

    total = (
        config.token_loss_weight * token_loss
        + config.feature_loss_weight * feature_loss
        + config.edge_loss_weight * edge_loss
    )
    return {
        "loss": total,
        "token_loss": token_loss,
        "feature_loss": feature_loss,
        "edge_loss": edge_loss,
    }


def pretrain_model(
    graphs: Sequence[PathConditionedGraph],
    *,
    vocabulary_size: int,
    model_config: NeuralModelConfig,
    pretraining_config: PretrainingConfig,
    device: torch.device,
) -> Tuple[SelfSupervisedPathConditionedGraphRanker, List[Dict[str, Any]]]:
    if not graphs:
        raise ValueError("no graphs for self-supervised pretraining")
    if any(graph.root_device_position is not None for graph in graphs):
        raise ValueError("self-supervised pretraining graphs must not contain root labels")
    pretraining_config.validate()
    set_seed(pretraining_config.seed)
    model = SelfSupervisedPathConditionedGraphRanker(
        vocabulary_size, model_config
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=pretraining_config.learning_rate,
        weight_decay=pretraining_config.weight_decay,
    )
    history: List[Dict[str, Any]] = []
    accumulation = max(1, pretraining_config.gradient_accumulation)

    for epoch in range(1, pretraining_config.epochs + 1):
        model.train()
        order = list(range(len(graphs)))
        random.Random(pretraining_config.seed + epoch).shuffle(order)
        optimizer.zero_grad(set_to_none=True)
        totals = {"loss": 0.0, "token_loss": 0.0, "feature_loss": 0.0, "edge_loss": 0.0}
        processed = 0
        pending = 0
        for step, graph_index in enumerate(order):
            batch = graph_to_tensors(graphs[graph_index], device)
            corrupted, targets = corrupt_graph_batch(
                batch,
                pretraining_config,
                seed=pretraining_config.seed + epoch * 1_000_003 + step,
            )
            losses = self_supervised_losses(model, corrupted, targets, pretraining_config)
            (losses["loss"] / accumulation).backward()
            for key in totals:
                totals[key] += float(losses[key].detach().item())
            processed += 1
            pending += 1
            if pending >= accumulation:
                nn.utils.clip_grad_norm_(model.parameters(), pretraining_config.gradient_clip)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                pending = 0
        if pending:
            nn.utils.clip_grad_norm_(model.parameters(), pretraining_config.gradient_clip)
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
        history.append(
            {
                "epoch": epoch,
                **{key: value / max(processed, 1) for key, value in totals.items()},
            }
        )
    return model, history


@torch.no_grad()
def evaluate_model(
    model: SelfSupervisedPathConditionedGraphRanker,
    graphs: Sequence[PathConditionedGraph],
    device: torch.device,
) -> Dict[str, float]:
    model.eval()
    totals = {"loss": 0.0, "top1": 0.0, "top3": 0.0, "top5": 0.0, "mrr": 0.0}
    evaluated = 0
    for graph in graphs:
        if graph.root_device_position is None:
            continue
        batch = graph_to_tensors(graph, device)
        logits = model(batch)
        totals["loss"] += float(model.ranking_loss(logits, batch["root_position"]).item())
        metrics = _rank_metrics(logits, batch["root_position"])
        for key, value in metrics.items():
            totals[key] += value
        evaluated += 1
    if not evaluated:
        return {"cases": 0, **totals}
    return {"cases": evaluated, **{key: value / evaluated for key, value in totals.items()}}


def finetune_model(
    model: SelfSupervisedPathConditionedGraphRanker,
    train_graphs: Sequence[PathConditionedGraph],
    validation_graphs: Sequence[PathConditionedGraph],
    *,
    training_config: TrainingConfig,
    device: torch.device,
    fixed_epochs: int | None = None,
) -> Tuple[SelfSupervisedPathConditionedGraphRanker, int, List[Dict[str, Any]]]:
    if not train_graphs:
        raise ValueError("no training graphs")
    if not any(graph.root_device_position is not None for graph in train_graphs):
        raise ValueError("none of the training labels map to a device in its graph")
    set_seed(training_config.seed)
    model = model.to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=training_config.learning_rate,
        weight_decay=training_config.weight_decay,
    )
    maximum_epochs = max(1, int(fixed_epochs or training_config.epochs))
    patience = maximum_epochs + 1 if fixed_epochs is not None else max(1, training_config.patience)
    best_state = copy.deepcopy(model.state_dict())
    best_epoch = 1
    best_score = -float("inf")
    stale = 0
    history: List[Dict[str, Any]] = []

    for epoch in range(1, maximum_epochs + 1):
        model.train()
        order = list(range(len(train_graphs)))
        random.Random(training_config.seed + epoch).shuffle(order)
        optimizer.zero_grad(set_to_none=True)
        running_loss = 0.0
        processed = 0
        pending = 0
        accumulation = max(1, training_config.gradient_accumulation)
        for graph_index in order:
            graph = train_graphs[graph_index]
            if graph.root_device_position is None:
                continue
            batch = graph_to_tensors(graph, device)
            loss = model.ranking_loss(model(batch), batch["root_position"])
            (loss / accumulation).backward()
            running_loss += float(loss.detach().item())
            processed += 1
            pending += 1
            if pending >= accumulation:
                nn.utils.clip_grad_norm_(model.parameters(), training_config.gradient_clip)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                pending = 0
        if pending:
            nn.utils.clip_grad_norm_(model.parameters(), training_config.gradient_clip)
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)

        validation = (
            evaluate_model(model, validation_graphs, device)
            if validation_graphs
            else evaluate_model(model, train_graphs, device)
        )
        history.append(
            {
                "epoch": epoch,
                "train_loss": running_loss / max(processed, 1),
                "validation": validation,
            }
        )
        selection_score = float(validation["mrr"])
        if selection_score > best_score + 1e-9:
            best_score = selection_score
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            stale = 0
        else:
            stale += 1
        if fixed_epochs is None and stale >= patience:
            break

    if fixed_epochs is not None:
        best_state = copy.deepcopy(model.state_dict())
        best_epoch = maximum_epochs
    model.load_state_dict(best_state)
    return model, best_epoch, history


@torch.no_grad()
def predict_graph(
    model: SelfSupervisedPathConditionedGraphRanker,
    graph: PathConditionedGraph,
    device: torch.device,
    *,
    top_k: int,
):
    from Sys.RootCauseAnalyze.stage1.neural_model import predict_graph as supervised_predict

    return supervised_predict(model, graph, device, top_k=top_k)


def save_checkpoint(
    path: str,
    *,
    model: SelfSupervisedPathConditionedGraphRanker,
    vocabulary: Mapping[str, Any],
    graph_config: Mapping[str, Any],
    model_config: NeuralModelConfig,
    training_config: TrainingConfig,
    pretraining_config: PretrainingConfig,
    metadata: Mapping[str, Any],
) -> None:
    import os

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    torch.save(
        {
            "format_version": CHECKPOINT_FORMAT,
            "model_state": model.state_dict(),
            "vocabulary": dict(vocabulary),
            "graph_config": dict(graph_config),
            "model_config": model_config.to_dict(),
            "training_config": training_config.to_dict(),
            "pretraining_config": pretraining_config.to_dict(),
            "metadata": dict(metadata),
        },
        path,
    )


def load_checkpoint(
    path: str, device: torch.device
) -> Tuple[SelfSupervisedPathConditionedGraphRanker, Dict[str, Any]]:
    try:
        payload = torch.load(path, map_location=device, weights_only=False)
    except TypeError:  # pragma: no cover - torch < 2.6
        payload = torch.load(path, map_location=device)
    if payload.get("format_version") != CHECKPOINT_FORMAT:
        raise ValueError("unsupported checkpoint: expected a self-supervised PC-STGR model")
    model_config = NeuralModelConfig(**payload["model_config"])
    vocabulary_size = len(payload.get("vocabulary", {}).get("itos", []))
    model = SelfSupervisedPathConditionedGraphRanker(
        vocabulary_size, model_config
    ).to(device)
    model.load_state_dict(payload["model_state"])
    model.eval()
    return model, payload


__all__ = [
    "CHECKPOINT_FORMAT",
    "NeuralModelConfig",
    "PretrainingConfig",
    "SelfSupervisedPathConditionedGraphRanker",
    "TrainingConfig",
    "corrupt_graph_batch",
    "evaluate_model",
    "finetune_model",
    "graph_to_tensors",
    "load_checkpoint",
    "predict_graph",
    "pretrain_model",
    "resolve_device",
    "save_checkpoint",
    "self_supervised_losses",
    "torch",
]
