from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Mapping


HETEROGENEOUS_SCHEMA_VERSION = "heterogeneous-propagation-v0"
HETEROGENEOUS_CONFIG_VERSION = "heterogeneous-baseline-v0"
M1_HETEROGENEOUS_SCHEMA_VERSION = "candidate-heterogeneous-evidence-graph-v0"
M2_HETEROGENEOUS_SCHEMA_VERSION = "heterogeneous-relation-probabilities-v0"
M3_HETEROGENEOUS_SCHEMA_VERSION = "joint-root-graph-decoding-v0"


@dataclass(frozen=True)
class HeterogeneousConfig:
    """Small, dependency-free settings for the first runnable baseline.

    The V0 implementation intentionally uses transparent heuristic potentials
    and bounded single-device-root enumeration.  Its output contract is kept
    separate from the legacy Stage 1/Stage 2 schema so learned relation heads
    and an exact constrained solver can replace the internals later.
    """

    config_version: str = HETEROGENEOUS_CONFIG_VERSION
    max_root_candidates: int = 12
    max_root_graph_hypotheses: int = 5
    max_events_per_device: int = 8
    max_event_pairs: int = 500
    min_event_relevance: float = 0.45
    event_time_tolerance_ms: int = 30_000
    root_potential_weight: float = 0.35
    root_softmax_temperature: float = 0.25
    identifiability_margin: float = 0.10

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_heterogeneous_config(
    config: HeterogeneousConfig | Mapping[str, Any] | None,
) -> HeterogeneousConfig:
    if config is None:
        normalized = HeterogeneousConfig()
    elif isinstance(config, HeterogeneousConfig):
        normalized = config
    elif isinstance(config, Mapping):
        allowed = {item.name for item in fields(HeterogeneousConfig)}
        unknown = sorted(set(config) - allowed)
        if unknown:
            raise ValueError(f"unknown heterogeneous config keys: {unknown}")
        normalized = HeterogeneousConfig(**dict(config))
    else:
        raise TypeError("config must be HeterogeneousConfig, mapping, or None")

    for name in (
        "max_root_candidates",
        "max_root_graph_hypotheses",
        "max_events_per_device",
        "max_event_pairs",
    ):
        if int(getattr(normalized, name)) <= 0:
            raise ValueError(f"{name} must be positive")
    for name in (
        "min_event_relevance",
        "root_potential_weight",
        "identifiability_margin",
    ):
        value = float(getattr(normalized, name))
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be within [0, 1]")
    if normalized.event_time_tolerance_ms < 0:
        raise ValueError("event_time_tolerance_ms must be non-negative")
    if normalized.root_softmax_temperature <= 0.0:
        raise ValueError("root_softmax_temperature must be positive")
    return normalized
