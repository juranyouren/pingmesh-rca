from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, List, Mapping, Sequence


M1_SCHEMA_VERSION = "hypothesis-graph-v1"
M2_SCHEMA_VERSION = "root-path-inference-v1"
SCHEMA_VERSION = "two-stage-output-v1"
CONFIG_VERSION = "two-stage-v1"


@dataclass(frozen=True)
class PropagationConfig:
    """Versioned settings for the two-stage root/path pipeline.

    Values are intentionally conservative. They are algorithm settings, not
    claims of calibrated causal probability, and must be selected without
    consulting the held-out path labels.
    """

    config_version: str = CONFIG_VERSION
    root_top_k: int = 3
    incident_neighborhood_hops: int = 1
    corridor_slack_hops: int = 2
    max_candidate_nodes: int = 80
    max_targets: int = 10
    event_window_ms: int = 300_000
    dedup_window_ms: int = 60_000
    timestamp_uncertainty_ms: int = 5_000
    negative_lag_tolerance_ms: int = 30_000
    max_propagation_lag_ms: int = 600_000
    max_path_depth: int = 8
    beam_width: int = 32
    top_k_paths_per_target: int = 3
    max_ranked_chains: int = 10
    max_alternative_hypotheses: int = 3
    min_edge_support: float = 0.25
    moderate_edge_support: float = 0.40
    strong_edge_support: float = 0.60
    direction_tie_margin: float = 0.08
    unique_hypothesis_margin: float = 0.08
    min_target_coverage_for_partial: float = 0.35
    min_target_coverage_for_full: float = 0.70
    stage1_weight: float = 0.50
    max_edge_hypotheses_output: int = 200
    edge_probability_method: str = "deterministic_evidence_v1"
    edge_probability_model_path: str | None = None
    edge_probability_temperature: float = 1.0
    logit_direction_bias: float = -1.50
    logit_temporal_weight: float = 1.50
    logit_semantic_weight: float = 2.00
    logit_direct_weight: float = 1.50
    logit_contradiction_weight: float = 2.00
    logit_no_direct_bias: float = -0.25
    logit_inactive_weight: float = 2.50
    logit_missing_relation_weight: float = 0.50
    logit_routing_convergence_bias: float = 0.25
    logit_physical_link_bias: float = 0.00
    logit_inferred_impact_bias: float = -0.25

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_config(config: PropagationConfig | Mapping[str, Any] | None) -> PropagationConfig:
    if config is None:
        normalized = PropagationConfig()
    elif isinstance(config, PropagationConfig):
        normalized = config
    elif isinstance(config, Mapping):
        allowed = {item.name for item in fields(PropagationConfig)}
        unknown = sorted(set(config) - allowed)
        if unknown:
            raise ValueError(f"unknown propagation config keys: {unknown}")
        normalized = PropagationConfig(**dict(config))
    else:
        raise TypeError("config must be PropagationConfig, mapping, or None")
    if not 0.0 <= normalized.stage1_weight <= 1.0:
        raise ValueError("stage1_weight must be within [0, 1]")
    allowed_probability_methods = {
        "deterministic_evidence_v1",
        "logit_softmax_v1",
        "supervised_softmax_v1",
    }
    if normalized.edge_probability_method not in allowed_probability_methods:
        raise ValueError(
            "edge_probability_method must be one of "
            f"{sorted(allowed_probability_methods)}"
        )
    if normalized.edge_probability_temperature <= 0.0:
        raise ValueError("edge_probability_temperature must be positive")
    if (
        normalized.edge_probability_method == "supervised_softmax_v1"
        and not normalized.edge_probability_model_path
    ):
        raise ValueError(
            "edge_probability_model_path is required for supervised_softmax_v1"
        )
    return normalized


def _as_score(item: Mapping[str, Any], rank: int) -> float:
    for key in (
        "combined_score",
        "stage1_score",
        "score",
        "support_score",
        "pr_score",
    ):
        value = item.get(key)
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            continue
    return 1.0 / max(rank, 1)


def build_root_hypotheses(
    rankings: Sequence[str | Mapping[str, Any]] | None,
    *,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Convert Stage 1 rankings into the Stage 2 root-hypothesis contract."""

    result: List[Dict[str, Any]] = []
    seen = set()
    for index, raw in enumerate(rankings or [], 1):
        if isinstance(raw, str):
            ip = raw
            item: Mapping[str, Any] = {}
        elif isinstance(raw, Mapping):
            ip = str(raw.get("ip", raw.get("device_id", "")) or "")
            item = raw
        else:
            continue
        if not ip or ip in seen:
            continue
        seen.add(ip)
        rank = len(result) + 1
        result.append(
            {
                "hypothesis_id": f"R{rank}",
                "root_scope": "device",
                "root_devices": [ip],
                "root_link": None,
                "rank": rank,
                "support_score": round(_as_score(item, index), 6),
                "decision_state": str(item.get("decision_state", "ranked_candidate")),
                "evidence_ids": list(item.get("evidence_ids", []))
                if isinstance(item.get("evidence_ids", []), list)
                else [],
            }
        )
        if len(result) >= max(1, int(top_k)):
            break
    return result


def root_devices(root_hypothesis: Mapping[str, Any]) -> List[str]:
    devices = [
        str(value)
        for value in root_hypothesis.get("root_devices", [])
        if isinstance(value, str) and value
    ]
    root_link = root_hypothesis.get("root_link")
    if isinstance(root_link, Mapping):
        for key in ("endpoint_a", "endpoint_b"):
            value = root_link.get(key)
            if isinstance(value, str) and value and value not in devices:
                devices.append(value)
    return devices
