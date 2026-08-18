from __future__ import annotations

import copy
import math
import random
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError as exc:  # pragma: no cover - exercised on the training server
    raise RuntimeError(
        "Neural Stage 1 requires PyTorch. Install the server's torch/torch-npu build "
        "or run the deterministic Stage 1 pipeline instead."
    ) from exc

from Sys.RootCauseAnalyze.stage1.neural_graph import (
    EDGE_FEATURE_DIM,
    NODE_FEATURE_DIM,
    NODE_TYPE_FEATURE_DIM,
    NODE_TYPE_COUNT,
    RELATION_COUNT,
    PathConditionedGraph,
)


@dataclass(frozen=True)
class NeuralModelConfig:
    hidden_dim: int = 64
    heads: int = 4
    layers: int = 2
    dropout: float = 0.20
    event_embedding_dim: int = 16

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrainingConfig:
    epochs: int = 120
    patience: int = 20
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    gradient_accumulation: int = 8
    gradient_clip: float = 2.0
    seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def resolve_device(requested: str = "auto") -> torch.device:
    name = str(requested or "auto").lower()
    if name == "auto":
        try:
            import torch_npu  # noqa: F401
        except ImportError:
            pass
        if hasattr(torch, "npu") and torch.npu.is_available():
            return torch.device("npu:0")
        if torch.cuda.is_available():
            return torch.device("cuda:0")
        return torch.device("cpu")
    if name.startswith("npu"):
        try:
            import torch_npu  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("--device npu requires torch-npu") from exc
    return torch.device(requested)


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if hasattr(torch, "npu"):
        try:
            torch.npu.manual_seed_all(seed)
        except Exception:
            pass


def graph_to_tensors(graph: PathConditionedGraph, device: torch.device) -> Dict[str, torch.Tensor]:
    root_position = -1 if graph.root_device_position is None else graph.root_device_position
    return {
        "node_features": torch.tensor(graph.node_features, dtype=torch.float32, device=device),
        "node_types": torch.tensor(graph.node_types, dtype=torch.long, device=device),
        "token_ids": torch.tensor(graph.token_ids, dtype=torch.long, device=device),
        "edge_sources": torch.tensor(graph.edge_sources, dtype=torch.long, device=device),
        "edge_targets": torch.tensor(graph.edge_targets, dtype=torch.long, device=device),
        "edge_types": torch.tensor(graph.edge_types, dtype=torch.long, device=device),
        "edge_features": torch.tensor(
            graph.edge_features, dtype=torch.float32, device=device
        ).reshape(-1, EDGE_FEATURE_DIM),
        "device_indices": torch.tensor(graph.device_indices, dtype=torch.long, device=device),
        "root_position": torch.tensor(root_position, dtype=torch.long, device=device),
    }


def _segment_softmax(logits: torch.Tensor, destinations: torch.Tensor, node_count: int) -> torch.Tensor:
    """Stable softmax over incoming edges for every destination and head."""

    if logits.numel() == 0:
        return logits
    heads = logits.shape[1]
    expanded = destinations[:, None].expand(-1, heads)
    maxima = torch.full(
        (node_count, heads),
        -torch.inf,
        dtype=logits.dtype,
        device=logits.device,
    )
    used_scatter_reduce = False
    if hasattr(maxima, "scatter_reduce_"):
        try:
            maxima.scatter_reduce_(0, expanded, logits.detach(), reduce="amax", include_self=True)
            used_scatter_reduce = True
        except RuntimeError:
            # Some torch-npu releases expose scatter_reduce_ but do not
            # implement the amax kernel on every device generation.
            pass
    if not used_scatter_reduce:  # pragma: no cover - legacy/NPU fallback
        for destination in torch.unique(destinations).tolist():
            mask = destinations == int(destination)
            maxima[int(destination)] = logits[mask].detach().max(dim=0).values
    exponentials = torch.exp(logits - maxima[destinations])
    denominators = torch.zeros((node_count, heads), dtype=logits.dtype, device=logits.device)
    denominators.index_add_(0, destinations, exponentials)
    return exponentials / denominators[destinations].clamp_min(1e-12)


class RelationalTemporalAttention(nn.Module):
    def __init__(self, config: NeuralModelConfig):
        super().__init__()
        if config.hidden_dim % config.heads:
            raise ValueError("hidden_dim must be divisible by heads")
        self.hidden_dim = config.hidden_dim
        self.heads = config.heads
        self.head_dim = config.hidden_dim // config.heads
        self.query = nn.Linear(config.hidden_dim, config.hidden_dim, bias=False)
        self.key = nn.Linear(config.hidden_dim, config.hidden_dim, bias=False)
        self.value = nn.Linear(config.hidden_dim, config.hidden_dim, bias=False)
        self.relation_key = nn.Embedding(RELATION_COUNT, config.hidden_dim)
        self.relation_value = nn.Embedding(RELATION_COUNT, config.hidden_dim)
        self.relation_bias = nn.Embedding(RELATION_COUNT, config.heads)
        self.edge_key = nn.Linear(EDGE_FEATURE_DIM, config.hidden_dim, bias=False)
        self.edge_value = nn.Linear(EDGE_FEATURE_DIM, config.hidden_dim, bias=False)
        self.edge_bias = nn.Linear(EDGE_FEATURE_DIM, config.heads, bias=False)
        self.output = nn.Linear(config.hidden_dim, config.hidden_dim)
        self.norm = nn.LayerNorm(config.hidden_dim)
        self.dropout = nn.Dropout(config.dropout)

    def forward(
        self,
        hidden: torch.Tensor,
        sources: torch.Tensor,
        targets: torch.Tensor,
        relations: torch.Tensor,
        edge_features: torch.Tensor,
    ) -> torch.Tensor:
        if sources.numel() == 0:
            return self.norm(hidden)
        node_count = hidden.shape[0]
        query = self.query(hidden)[targets].view(-1, self.heads, self.head_dim)
        key = (
            self.key(hidden)[sources]
            + self.relation_key(relations)
            + self.edge_key(edge_features)
        ).view(-1, self.heads, self.head_dim)
        value = (
            self.value(hidden)[sources]
            + self.relation_value(relations)
            + self.edge_value(edge_features)
        ).view(-1, self.heads, self.head_dim)
        logits = (query * key).sum(dim=-1) / math.sqrt(self.head_dim)
        logits = logits + self.relation_bias(relations) + self.edge_bias(edge_features)
        attention = self.dropout(_segment_softmax(logits, targets, node_count))
        messages = attention.unsqueeze(-1) * value
        aggregated = torch.zeros(
            (node_count, self.heads, self.head_dim),
            dtype=hidden.dtype,
            device=hidden.device,
        )
        aggregated.index_add_(0, targets, messages)
        update = self.dropout(self.output(aggregated.reshape(node_count, self.hidden_dim)))
        return self.norm(hidden + update)


class PathConditionedGraphRanker(nn.Module):
    def __init__(self, vocabulary_size: int, config: NeuralModelConfig):
        super().__init__()
        if config.event_embedding_dim <= 0:
            raise ValueError("event_embedding_dim must be positive")
        self.config = config
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

    def forward(self, batch: Mapping[str, torch.Tensor]) -> torch.Tensor:
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
        return self.root_head(hidden[batch["device_indices"]]).squeeze(-1)

    def ranking_loss(self, logits: torch.Tensor, root_position: torch.Tensor) -> torch.Tensor:
        if root_position.numel() != 1 or int(root_position.item()) < 0:
            raise ValueError("training graph has no ground-truth device in the graph")
        root = root_position.reshape(1)
        return F.cross_entropy(logits.unsqueeze(0), root)


def _rank_metrics(logits: torch.Tensor, root_position: torch.Tensor) -> Dict[str, float]:
    order = torch.argsort(logits, descending=True).tolist()
    root = int(root_position.item())
    best_rank = next(
        (rank for rank, position in enumerate(order, 1) if position == root),
        len(order) + 1,
    )
    return {
        "top1": float(best_rank <= 1),
        "top3": float(best_rank <= 3),
        "top5": float(best_rank <= 5),
        "mrr": 1.0 / best_rank,
    }


@torch.no_grad()
def evaluate_model(
    model: PathConditionedGraphRanker,
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


def train_model(
    train_graphs: Sequence[PathConditionedGraph],
    validation_graphs: Sequence[PathConditionedGraph],
    *,
    vocabulary_size: int,
    model_config: NeuralModelConfig,
    training_config: TrainingConfig,
    device: torch.device,
    fixed_epochs: int | None = None,
) -> Tuple[PathConditionedGraphRanker, int, List[Dict[str, Any]]]:
    if not train_graphs:
        raise ValueError("no training graphs")
    if not any(graph.root_device_position is not None for graph in train_graphs):
        raise ValueError("none of the training labels map to a device in its path-conditioned graph")
    set_seed(training_config.seed)
    model = PathConditionedGraphRanker(vocabulary_size, model_config).to(device)
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
        pending_gradients = 0
        accumulation = max(1, training_config.gradient_accumulation)
        for graph_index in order:
            graph = train_graphs[graph_index]
            if graph.root_device_position is None:
                continue
            batch = graph_to_tensors(graph, device)
            logits = model(batch)
            loss = model.ranking_loss(logits, batch["root_position"])
            (loss / accumulation).backward()
            running_loss += float(loss.detach().item())
            processed += 1
            pending_gradients += 1
            if pending_gradients >= accumulation:
                nn.utils.clip_grad_norm_(model.parameters(), training_config.gradient_clip)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                pending_gradients = 0
        if pending_gradients:
            nn.utils.clip_grad_norm_(model.parameters(), training_config.gradient_clip)
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)

        validation = (
            evaluate_model(model, validation_graphs, device)
            if validation_graphs
            else evaluate_model(model, train_graphs, device)
        )
        selection_score = float(validation["mrr"])
        row = {
            "epoch": epoch,
            "train_loss": running_loss / max(processed, 1),
            "validation": validation,
        }
        history.append(row)
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
    model: PathConditionedGraphRanker,
    graph: PathConditionedGraph,
    device: torch.device,
    *,
    top_k: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    model.eval()
    batch = graph_to_tensors(graph, device)
    logits = model(batch)
    probabilities = torch.softmax(logits, dim=0)
    count = min(max(1, int(top_k)), len(graph.device_ips))
    values, indices = torch.topk(probabilities, k=count)
    rankings = [
        {
            "rank": rank,
            "ip": graph.device_ips[int(position)],
            "combined_score": round(float(probability), 8),
            "neural_score": round(float(probability), 8),
            "logit": round(float(logits[int(position)]), 8),
        }
        for rank, (probability, position) in enumerate(zip(values.tolist(), indices.tolist()), 1)
    ]
    entropy = -torch.sum(probabilities * torch.log(probabilities.clamp_min(1e-12)))
    normalized_entropy = float(entropy / math.log(max(len(graph.device_ips), 2)))
    margin = float(values[0] - values[1]) if len(values) > 1 else float(values[0])
    diagnostics = {
        **graph.diagnostics,
        "normalized_entropy": round(normalized_entropy, 8),
        "top1_margin": round(margin, 8),
    }
    return rankings, diagnostics


def save_checkpoint(
    path: str,
    *,
    model: PathConditionedGraphRanker,
    vocabulary: Mapping[str, Any],
    graph_config: Mapping[str, Any],
    model_config: NeuralModelConfig,
    training_config: TrainingConfig,
    metadata: Mapping[str, Any],
) -> None:
    import os

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    torch.save(
        {
            "format_version": "pc-stgr-stage1-v1",
            "model_state": model.state_dict(),
            "vocabulary": dict(vocabulary),
            "graph_config": dict(graph_config),
            "model_config": model_config.to_dict(),
            "training_config": training_config.to_dict(),
            "metadata": dict(metadata),
        },
        path,
    )


def load_checkpoint(path: str, device: torch.device) -> Tuple[PathConditionedGraphRanker, Dict[str, Any]]:
    try:
        payload = torch.load(path, map_location=device, weights_only=False)
    except TypeError:  # pragma: no cover - torch < 2.6
        payload = torch.load(path, map_location=device)
    if payload.get("format_version") != "pc-stgr-stage1-v1":
        raise ValueError("unsupported checkpoint: expected a PC-STGR Stage 1 model")
    model_config = NeuralModelConfig(**payload["model_config"])
    vocabulary_size = len(payload.get("vocabulary", {}).get("itos", []))
    model = PathConditionedGraphRanker(vocabulary_size, model_config).to(device)
    model.load_state_dict(payload["model_state"])
    model.eval()
    return model, payload
