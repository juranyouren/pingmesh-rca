from __future__ import annotations

import copy
import math
import os
import random
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError as exc:  # pragma: no cover - exercised on the training server
    raise RuntimeError("The candidate-conditioned graph verifier requires PyTorch.") from exc

from Sys.RootCauseAnalyze.stage1.neural_graph import PathConditionedGraph
from Sys.RootCauseAnalyze.stage1.neural_model import (
    NeuralModelConfig,
    PathConditionedGraphRanker,
    graph_to_tensors,
    set_seed,
)


CHECKPOINT_FORMAT = "pc-stgr-candidate-graph-verifier-v1"
SUPERVISED_STAGE1_FORMAT = "pc-stgr-stage1-v1"
SSL_STAGE1_FORMAT = "pc-stgr-ssl-stage1-v1"


@dataclass(frozen=True)
class VerifierModelConfig:
    max_correction_scale: float = 1.0
    gate_init: float = 0.0
    freeze_backbone: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VerifierTrainingConfig:
    epochs: int = 40
    patience: int = 8
    learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    gradient_accumulation: int = 4
    gradient_clip: float = 2.0
    auxiliary_margin_loss_weight: float = 0.25
    seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateGraphView:
    ip: str
    initial_rank: int
    base_probability: float
    base_logit: float
    graph: PathConditionedGraph
    candidate_device_position: int


@dataclass
class CandidateGraphExample:
    dirpath: str
    candidates: List[CandidateGraphView]
    gt_ip: str | None = None
    diagnostics: Dict[str, Any] | None = None

    @property
    def target_position(self) -> int | None:
        if not self.gt_ip:
            return None
        for index, candidate in enumerate(self.candidates):
            if candidate.ip == self.gt_ip:
                return index
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def probability_logit(probability: Any) -> float:
    value = min(max(_safe_float(probability), 1e-8), 1.0 - 1e-8)
    return math.log(value) - math.log1p(-value)


def load_torch_payload(path: str, device: torch.device) -> Dict[str, Any]:
    try:
        payload = torch.load(path, map_location=device, weights_only=False)
    except TypeError:  # pragma: no cover - torch < 2.6
        payload = torch.load(path, map_location=device)
    if not isinstance(payload, Mapping):
        raise ValueError(f"checkpoint is not a mapping: {path}")
    return dict(payload)


def _new_backbone(
    *,
    stage1_format: str,
    vocabulary_size: int,
    model_config: NeuralModelConfig,
) -> nn.Module:
    if stage1_format == SUPERVISED_STAGE1_FORMAT:
        return PathConditionedGraphRanker(vocabulary_size, model_config)
    if stage1_format == SSL_STAGE1_FORMAT:
        from Sys.RootCauseAnalyze.stage1.neural_ssl_model import (
            SelfSupervisedPathConditionedGraphRanker,
        )

        return SelfSupervisedPathConditionedGraphRanker(
            vocabulary_size, model_config
        )
    raise ValueError(
        "candidate verifier requires a supervised or self-supervised PC-STGR "
        f"checkpoint, got {stage1_format!r}"
    )


class CandidateConditionedGraphVerifier(nn.Module):
    """Run PC-STGR once per candidate hard DAG and learn a conservative gate."""

    def __init__(self, backbone: nn.Module, config: VerifierModelConfig):
        super().__init__()
        if config.max_correction_scale <= 0.0:
            raise ValueError("max_correction_scale must be positive")
        self.backbone = backbone
        self.config = config
        self.verification_gate = nn.Parameter(
            torch.tensor(float(config.gate_init), dtype=torch.float32)
        )
        if config.freeze_backbone:
            for parameter in self.backbone.parameters():
                parameter.requires_grad_(False)

    def correction_scale(self) -> torch.Tensor:
        return float(self.config.max_correction_scale) * torch.tanh(
            self.verification_gate
        )

    def combine(
        self, base_logits: torch.Tensor, verification_margins: torch.Tensor
    ) -> torch.Tensor:
        return base_logits + self.correction_scale() * verification_margins


def verifier_from_stage1_payload(
    payload: Mapping[str, Any],
    config: VerifierModelConfig,
    device: torch.device,
) -> CandidateConditionedGraphVerifier:
    stage1_format = str(payload.get("format_version", ""))
    model_config = NeuralModelConfig(**dict(payload.get("model_config", {})))
    if not model_config.use_propagation_edge_probabilities:
        raise ValueError(
            "candidate verification requires a Stage-1 checkpoint trained with "
            "root-independent propagation edge probabilities"
        )
    vocabulary_size = len(payload.get("vocabulary", {}).get("itos", []))
    if vocabulary_size < 2:
        raise ValueError("Stage-1 checkpoint has an invalid event vocabulary")
    backbone = _new_backbone(
        stage1_format=stage1_format,
        vocabulary_size=vocabulary_size,
        model_config=model_config,
    )
    backbone.load_state_dict(payload["model_state"])
    return CandidateConditionedGraphVerifier(backbone, config).to(device)


def _candidate_margin(
    device_logits: torch.Tensor, candidate_position: int
) -> torch.Tensor:
    if candidate_position < 0 or candidate_position >= int(device_logits.numel()):
        raise ValueError("candidate device position is outside the graph")
    own = device_logits[candidate_position]
    if device_logits.numel() == 1:
        return own
    positions = torch.arange(device_logits.numel(), device=device_logits.device)
    strongest_other = torch.max(device_logits[positions != candidate_position])
    return own - strongest_other


def score_example(
    model: CandidateConditionedGraphVerifier,
    example: CandidateGraphExample,
    device: torch.device,
) -> Dict[str, Any]:
    if not example.candidates:
        raise ValueError(f"candidate verifier received an empty case: {example.dirpath}")
    margins: List[torch.Tensor] = []
    candidate_logits: List[torch.Tensor] = []
    device_logits_by_candidate: List[torch.Tensor] = []
    for candidate in example.candidates:
        batch = graph_to_tensors(candidate.graph, device)
        device_logits = model.backbone(batch)
        device_logits_by_candidate.append(device_logits)
        candidate_logits.append(device_logits[candidate.candidate_device_position])
        margins.append(
            _candidate_margin(device_logits, candidate.candidate_device_position)
        )
    base_logits = torch.tensor(
        [candidate.base_logit for candidate in example.candidates],
        dtype=torch.float32,
        device=device,
    )
    verification_margins = torch.stack(margins)
    own_logits = torch.stack(candidate_logits)
    final_logits = model.combine(base_logits, verification_margins)
    return {
        "base_logits": base_logits,
        "verification_margins": verification_margins,
        "candidate_logits": own_logits,
        "final_logits": final_logits,
        "device_logits": device_logits_by_candidate,
    }


@torch.no_grad()
def predict_example(
    model: CandidateConditionedGraphVerifier,
    example: CandidateGraphExample,
    device: torch.device,
) -> List[Dict[str, Any]]:
    model.eval()
    outputs = score_example(model, example, device)
    final_logits = outputs["final_logits"]
    final_probabilities = torch.softmax(final_logits, dim=0)
    order = torch.argsort(final_logits, descending=True).tolist()
    scale = float(model.correction_scale().detach().cpu().item())
    rankings: List[Dict[str, Any]] = []
    for final_rank, raw_position in enumerate(order, 1):
        position = int(raw_position)
        candidate = example.candidates[position]
        device_logits = outputs["device_logits"][position]
        device_order = torch.argsort(device_logits, descending=True).tolist()
        self_rank = device_order.index(candidate.candidate_device_position) + 1
        self_probability = float(
            torch.softmax(device_logits, dim=0)[candidate.candidate_device_position]
        )
        margin = float(outputs["verification_margins"][position])
        base_logit = float(outputs["base_logits"][position])
        final_logit = float(final_logits[position])
        rankings.append(
            {
                "rank": final_rank,
                "ip": candidate.ip,
                "initial_rank": candidate.initial_rank,
                "stage1_score": round(candidate.base_probability, 8),
                "stage1_logit": round(base_logit, 8),
                "verification_candidate_probability": round(self_probability, 8),
                "verification_margin": round(margin, 8),
                "verification_self_rank": self_rank,
                "verification_top1": self_rank == 1,
                "verification_scale": round(scale, 8),
                "reranker_logit": round(final_logit, 8),
                "reranker_delta": round(final_logit - base_logit, 8),
                "combined_score": round(float(final_probabilities[position]), 8),
                "neural_score": round(float(final_probabilities[position]), 8),
            }
        )
    return rankings


def evaluate_verifier(
    model: CandidateConditionedGraphVerifier,
    examples: Sequence[CandidateGraphExample],
    device: torch.device,
) -> Dict[str, Any]:
    labeled = [example for example in examples if example.gt_ip]
    if not labeled:
        return {"case_count": 0, "candidate_recall": 0.0}
    eligible = 0
    initial_top1 = 0
    final_hits = {1: 0, 3: 0, 5: 0}
    reciprocal_rank = 0.0
    corrections = 0
    corruptions = 0
    gt_self_top1 = 0
    false_self_top1 = 0
    false_view_count = 0
    gt_margin_sum = 0.0
    false_margin_sum = 0.0
    model.eval()
    with torch.no_grad():
        for example in labeled:
            target = example.target_position
            initial_correct = bool(
                example.candidates and example.candidates[0].ip == example.gt_ip
            )
            initial_top1 += int(initial_correct)
            if target is None:
                continue
            eligible += 1
            outputs = score_example(model, example, device)
            order = torch.argsort(outputs["final_logits"], descending=True).tolist()
            final_rank = order.index(target) + 1
            final_correct = final_rank == 1
            reciprocal_rank += 1.0 / final_rank
            corrections += int(not initial_correct and final_correct)
            corruptions += int(initial_correct and not final_correct)
            for cutoff in final_hits:
                final_hits[cutoff] += int(final_rank <= cutoff)
            for position, device_logits in enumerate(outputs["device_logits"]):
                candidate = example.candidates[position]
                self_top1 = int(torch.argmax(device_logits)) == candidate.candidate_device_position
                margin = float(outputs["verification_margins"][position])
                if position == target:
                    gt_self_top1 += int(self_top1)
                    gt_margin_sum += margin
                else:
                    false_view_count += 1
                    false_self_top1 += int(self_top1)
                    false_margin_sum += margin
    total = len(labeled)
    return {
        "case_count": total,
        "eligible_case_count": eligible,
        "candidate_recall": round(eligible / total, 6),
        "initial_top1": round(initial_top1 / total, 6),
        "final_top1": round(final_hits[1] / total, 6),
        "final_top3": round(final_hits[3] / total, 6),
        "final_top5": round(final_hits[5] / total, 6),
        "mrr": round(reciprocal_rank / total, 6),
        "conditional_top1": round(final_hits[1] / eligible, 6) if eligible else 0.0,
        "corrections": corrections,
        "corruptions": corruptions,
        "net_corrections": corrections - corruptions,
        "gt_view_self_top1": round(gt_self_top1 / eligible, 6) if eligible else 0.0,
        "false_view_self_top1": (
            round(false_self_top1 / false_view_count, 6)
            if false_view_count
            else 0.0
        ),
        "mean_gt_verification_margin": (
            round(gt_margin_sum / eligible, 6) if eligible else 0.0
        ),
        "mean_false_verification_margin": (
            round(false_margin_sum / false_view_count, 6)
            if false_view_count
            else 0.0
        ),
        "verification_scale": round(
            float(model.correction_scale().detach().cpu().item()), 8
        ),
    }


def _validation_loss(
    model: CandidateConditionedGraphVerifier,
    examples: Sequence[CandidateGraphExample],
    training_config: VerifierTrainingConfig,
    device: torch.device,
) -> float:
    losses: List[float] = []
    model.eval()
    with torch.no_grad():
        for example in examples:
            target = example.target_position
            if target is None:
                continue
            outputs = score_example(model, example, device)
            target_tensor = torch.tensor([target], dtype=torch.long, device=device)
            loss = F.cross_entropy(outputs["final_logits"].unsqueeze(0), target_tensor)
            if training_config.auxiliary_margin_loss_weight > 0.0:
                loss = loss + float(training_config.auxiliary_margin_loss_weight) * F.cross_entropy(
                    outputs["verification_margins"].unsqueeze(0), target_tensor
                )
            losses.append(float(loss))
    return sum(losses) / len(losses) if losses else float("inf")


def train_verifier(
    stage1_payload: Mapping[str, Any],
    training_examples: Sequence[CandidateGraphExample],
    validation_examples: Sequence[CandidateGraphExample],
    *,
    model_config: VerifierModelConfig,
    training_config: VerifierTrainingConfig,
    device: torch.device,
    fixed_epochs: int | None = None,
) -> Tuple[CandidateConditionedGraphVerifier, int, List[Dict[str, float]]]:
    eligible = [
        example for example in training_examples if example.target_position is not None
    ]
    if not eligible:
        raise ValueError("no verifier training case contains its root in Top-K")
    set_seed(training_config.seed)
    model = verifier_from_stage1_payload(stage1_payload, model_config, device)
    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(
        parameters,
        lr=training_config.learning_rate,
        weight_decay=training_config.weight_decay,
    )
    maximum_epochs = max(1, int(fixed_epochs or training_config.epochs))
    best_state = copy.deepcopy(model.state_dict())
    best_epoch = 1
    best_loss = float("inf")
    stale = 0
    history: List[Dict[str, float]] = []
    accumulation = max(1, int(training_config.gradient_accumulation))

    for epoch in range(1, maximum_epochs + 1):
        model.train()
        if model_config.freeze_backbone:
            model.backbone.eval()
        order = list(range(len(eligible)))
        random.Random(training_config.seed + epoch).shuffle(order)
        optimizer.zero_grad(set_to_none=True)
        total_loss = 0.0
        pending = 0
        for example_index in order:
            example = eligible[example_index]
            target = int(example.target_position or 0)
            outputs = score_example(model, example, device)
            target_tensor = torch.tensor([target], dtype=torch.long, device=device)
            loss = F.cross_entropy(outputs["final_logits"].unsqueeze(0), target_tensor)
            if training_config.auxiliary_margin_loss_weight > 0.0:
                loss = loss + float(training_config.auxiliary_margin_loss_weight) * F.cross_entropy(
                    outputs["verification_margins"].unsqueeze(0), target_tensor
                )
            (loss / accumulation).backward()
            total_loss += float(loss.detach())
            pending += 1
            if pending >= accumulation:
                nn.utils.clip_grad_norm_(parameters, training_config.gradient_clip)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                pending = 0
        if pending:
            nn.utils.clip_grad_norm_(parameters, training_config.gradient_clip)
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)

        train_loss = total_loss / len(eligible)
        validation_loss = (
            _validation_loss(model, validation_examples, training_config, device)
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
                "verification_scale": round(
                    float(model.correction_scale().detach().cpu().item()), 8
                ),
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
            if stale >= max(1, int(training_config.patience)):
                break

    if fixed_epochs is not None:
        best_epoch = maximum_epochs
        best_state = copy.deepcopy(model.state_dict())
    model.load_state_dict(best_state)
    return model, best_epoch, history


def save_checkpoint(
    path: str,
    *,
    model: CandidateConditionedGraphVerifier,
    stage1_payload: Mapping[str, Any],
    model_config: VerifierModelConfig,
    training_config: VerifierTrainingConfig,
    propagation_config: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    torch.save(
        {
            "format_version": CHECKPOINT_FORMAT,
            "model_state": model.state_dict(),
            "stage1_format_version": stage1_payload.get("format_version"),
            "vocabulary": dict(stage1_payload.get("vocabulary", {})),
            "graph_config": dict(stage1_payload.get("graph_config", {})),
            "stage1_model_config": dict(stage1_payload.get("model_config", {})),
            "verifier_model_config": model_config.to_dict(),
            "training_config": training_config.to_dict(),
            "propagation_config": dict(propagation_config),
            "metadata": dict(metadata),
        },
        path,
    )


def load_checkpoint(
    path: str, device: torch.device
) -> Tuple[CandidateConditionedGraphVerifier, Dict[str, Any]]:
    payload = load_torch_payload(path, device)
    if payload.get("format_version") != CHECKPOINT_FORMAT:
        raise ValueError("unsupported candidate-conditioned verifier checkpoint")
    model_config = VerifierModelConfig(**payload["verifier_model_config"])
    stage1_format = str(payload.get("stage1_format_version", ""))
    stage1_model_config = NeuralModelConfig(**payload["stage1_model_config"])
    vocabulary_size = len(payload.get("vocabulary", {}).get("itos", []))
    backbone = _new_backbone(
        stage1_format=stage1_format,
        vocabulary_size=vocabulary_size,
        model_config=stage1_model_config,
    )
    model = CandidateConditionedGraphVerifier(backbone, model_config).to(device)
    model.load_state_dict(payload["model_state"])
    model.eval()
    return model, payload


__all__ = [
    "CHECKPOINT_FORMAT",
    "CandidateConditionedGraphVerifier",
    "CandidateGraphExample",
    "CandidateGraphView",
    "VerifierModelConfig",
    "VerifierTrainingConfig",
    "evaluate_verifier",
    "load_checkpoint",
    "load_torch_payload",
    "predict_example",
    "probability_logit",
    "save_checkpoint",
    "score_example",
    "train_verifier",
    "verifier_from_stage1_payload",
]
