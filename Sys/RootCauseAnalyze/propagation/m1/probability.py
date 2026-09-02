from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from typing import Any, Dict, Mapping, Sequence

from Sys.RootCauseAnalyze.propagation.schema import (
    PropagationConfig,
    normalize_config,
)


STATE_NAMES = (
    "endpoint_a_to_b",
    "endpoint_b_to_a",
    "no_direct_propagation",
)

EDGE_FEATURE_NAMES = (
    "forward_case_support",
    "forward_temporal",
    "forward_semantic",
    "forward_direct",
    "forward_contradiction",
    "forward_temporal_available",
    "forward_evidence_count",
    "forward_relation_routing",
    "forward_relation_physical",
    "forward_relation_inferred",
    "reverse_case_support",
    "reverse_temporal",
    "reverse_semantic",
    "reverse_direct",
    "reverse_contradiction",
    "reverse_temporal_available",
    "reverse_evidence_count",
    "reverse_relation_routing",
    "reverse_relation_physical",
    "reverse_relation_inferred",
    "inactive_support",
    "signed_support_gap",
    "any_dynamic_support",
)


def _normalized_triplet(
    forward: float, reverse: float, no_direct: float
) -> tuple[float, float, float]:
    values = [
        max(0.0, float(forward)),
        max(0.0, float(reverse)),
        max(0.0, float(no_direct)),
    ]
    total = sum(values)
    if total <= 0.0:
        values = [1.0, 1.0, 1.0]
        total = 3.0
    normalized = [value / total for value in values]
    rounded = [round(normalized[0], 6), round(normalized[1], 6)]
    rounded.append(round(1.0 - rounded[0] - rounded[1], 6))
    return rounded[0], rounded[1], rounded[2]


def _softmax_triplet(logits: Sequence[float], temperature: float) -> tuple[float, float, float]:
    scaled = [float(value) / temperature for value in logits]
    maximum = max(scaled)
    exponentials = [math.exp(value - maximum) for value in scaled]
    return _normalized_triplet(*exponentials)


def _direction_map(edge_hypothesis: Mapping[str, Any]) -> Dict[tuple[str, str], Dict[str, Any]]:
    return {
        (str(item.get("from", "")), str(item.get("to", ""))): dict(item)
        for item in edge_hypothesis.get("directions", [])
        if isinstance(item, Mapping)
    }


def _inactive_support(edge_hypothesis: Mapping[str, Any]) -> float:
    states = edge_hypothesis.get("states", {})
    if not isinstance(states, Mapping):
        return 0.0
    return max(
        float(states.get("no_direct_propagation", 0.0) or 0.0),
        float(states.get("inactive_or_unobserved", 0.0) or 0.0),
    )


def _direction_feature_values(direction: Mapping[str, Any]) -> Dict[str, float]:
    raw_features = direction.get("features", {})
    features = raw_features if isinstance(raw_features, Mapping) else {}
    evidence_ids = direction.get("evidence_ids", [])
    evidence_count = len(evidence_ids) if isinstance(evidence_ids, list) else 0
    relation = str(direction.get("relation", "inferred_impact") or "inferred_impact")
    return {
        "case_support": float(direction.get("case_support_score", 0.0) or 0.0),
        "temporal": float(features.get("temporal_order_support", 0.0) or 0.0),
        "semantic": float(features.get("semantic_pair_support", 0.0) or 0.0),
        "direct": float(features.get("direct_relation_support", 0.0) or 0.0),
        "contradiction": float(features.get("case_contradiction", 0.0) or 0.0),
        "temporal_available": float(bool(features.get("temporal_available", False))),
        "evidence_count": min(float(evidence_count), 10.0) / 10.0,
        "relation_routing": float(relation == "routing_convergence"),
        "relation_physical": float(relation == "physical_link"),
        "relation_inferred": float(
            relation not in {"routing_convergence", "physical_link"}
        ),
    }


def extract_edge_probability_features(
    edge_hypothesis: Mapping[str, Any],
) -> Dict[str, float]:
    """Return the canonical, root-independent P4 feature vector for one pair."""

    endpoint_a = str(edge_hypothesis.get("endpoint_a", "") or "")
    endpoint_b = str(edge_hypothesis.get("endpoint_b", "") or "")
    by_direction = _direction_map(edge_hypothesis)
    forward = _direction_feature_values(by_direction.get((endpoint_a, endpoint_b), {}))
    reverse = _direction_feature_values(by_direction.get((endpoint_b, endpoint_a), {}))
    dynamic_values = [
        forward["temporal"],
        forward["semantic"],
        forward["direct"],
        reverse["temporal"],
        reverse["semantic"],
        reverse["direct"],
    ]
    result = {
        **{f"forward_{key}": value for key, value in forward.items()},
        **{f"reverse_{key}": value for key, value in reverse.items()},
        "inactive_support": _inactive_support(edge_hypothesis),
        "signed_support_gap": forward["case_support"] - reverse["case_support"],
        "any_dynamic_support": float(max(dynamic_values, default=0.0) > 0.0),
    }
    return {name: float(result.get(name, 0.0)) for name in EDGE_FEATURE_NAMES}


def _result(
    edge_hypothesis: Mapping[str, Any],
    probabilities: Sequence[float],
    *,
    method: str,
    details: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    endpoint_a = str(edge_hypothesis.get("endpoint_a", "") or "")
    endpoint_b = str(edge_hypothesis.get("endpoint_b", "") or "")
    directions = [
        dict(item)
        for item in edge_hypothesis.get("directions", [])
        if isinstance(item, Mapping)
    ]
    p_forward, p_reverse, p_no_direct = _normalized_triplet(*probabilities)
    for item in directions:
        key = (str(item.get("from", "")), str(item.get("to", "")))
        if key == (endpoint_a, endpoint_b):
            item["state_probability"] = p_forward
        elif key == (endpoint_b, endpoint_a):
            item["state_probability"] = p_reverse

    probability_map = dict(zip(STATE_NAMES, (p_forward, p_reverse, p_no_direct)))
    entropy = -sum(value * math.log(value) for value in probability_map.values() if value > 0.0)
    preferred_key = max(
        probability_map,
        key=lambda key: (probability_map[key], key == "no_direct_propagation", key),
    )
    preferred_state = {
        "endpoint_a_to_b": f"{endpoint_a}->{endpoint_b}",
        "endpoint_b_to_a": f"{endpoint_b}->{endpoint_a}",
        "no_direct_propagation": "no_direct_propagation",
    }[preferred_key]
    payload = {
        **dict(edge_hypothesis),
        "directions": directions,
        "state_probabilities": probability_map,
        "probability_method": method,
        "distribution_entropy": round(entropy, 6),
        "preferred_state": preferred_state,
    }
    if details:
        payload["probability_details"] = dict(details)
    return payload


def _deterministic_probabilities(edge_hypothesis: Mapping[str, Any]) -> tuple[float, float, float]:
    endpoint_a = str(edge_hypothesis.get("endpoint_a", "") or "")
    endpoint_b = str(edge_hypothesis.get("endpoint_b", "") or "")
    by_direction = _direction_map(edge_hypothesis)
    forward = by_direction.get((endpoint_a, endpoint_b), {})
    reverse = by_direction.get((endpoint_b, endpoint_a), {})
    return _normalized_triplet(
        float(forward.get("case_support_score", 0.0) or 0.0),
        float(reverse.get("case_support_score", 0.0) or 0.0),
        _inactive_support(edge_hypothesis),
    )


def _logit_probabilities(
    edge_hypothesis: Mapping[str, Any], config: PropagationConfig
) -> tuple[tuple[float, float, float], Dict[str, Any]]:
    features = extract_edge_probability_features(edge_hypothesis)
    if features["any_dynamic_support"] <= 0.0:
        return (0.0, 0.0, 1.0), {
            "override": "no_dynamic_propagation_support",
            "feature_names": list(EDGE_FEATURE_NAMES),
        }

    def direction_logit(prefix: str) -> float:
        return (
            config.logit_direction_bias
            + config.logit_temporal_weight * features[f"{prefix}_temporal"]
            + config.logit_semantic_weight * features[f"{prefix}_semantic"]
            + config.logit_direct_weight * features[f"{prefix}_direct"]
            - config.logit_contradiction_weight * features[f"{prefix}_contradiction"]
            + config.logit_routing_convergence_bias
            * features[f"{prefix}_relation_routing"]
            + config.logit_physical_link_bias
            * features[f"{prefix}_relation_physical"]
            + config.logit_inferred_impact_bias
            * features[f"{prefix}_relation_inferred"]
        )

    maximum_relation = max(
        features["forward_semantic"],
        features["forward_direct"],
        features["reverse_semantic"],
        features["reverse_direct"],
    )
    logits = (
        direction_logit("forward"),
        direction_logit("reverse"),
        config.logit_no_direct_bias
        + config.logit_inactive_weight * features["inactive_support"]
        + config.logit_missing_relation_weight * (1.0 - maximum_relation),
    )
    probabilities = _softmax_triplet(logits, config.edge_probability_temperature)
    return probabilities, {
        "logits": dict(zip(STATE_NAMES, (round(value, 6) for value in logits))),
        "temperature": config.edge_probability_temperature,
        "feature_names": list(EDGE_FEATURE_NAMES),
    }


@lru_cache(maxsize=32)
def _load_supervised_model(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("schema_version") != "stage2-edge-classifier-v1":
        raise ValueError(f"unsupported edge classifier schema in {path}")
    if tuple(payload.get("state_names", [])) != STATE_NAMES:
        raise ValueError(f"edge classifier states do not match runtime contract: {path}")
    if tuple(payload.get("feature_names", [])) != EDGE_FEATURE_NAMES:
        raise ValueError(f"edge classifier features do not match runtime contract: {path}")
    feature_count = len(EDGE_FEATURE_NAMES)
    weights = payload.get("weights", [])
    if len(weights) != len(STATE_NAMES) or any(len(row) != feature_count for row in weights):
        raise ValueError(f"edge classifier weight shape is invalid: {path}")
    for key in ("feature_mean", "feature_scale"):
        if len(payload.get(key, [])) != feature_count:
            raise ValueError(f"edge classifier {key} shape is invalid: {path}")
    if len(payload.get("bias", [])) != len(STATE_NAMES):
        raise ValueError(f"edge classifier bias shape is invalid: {path}")
    return dict(payload)


def _supervised_probabilities(
    edge_hypothesis: Mapping[str, Any], config: PropagationConfig
) -> tuple[tuple[float, float, float], Dict[str, Any]]:
    features = extract_edge_probability_features(edge_hypothesis)
    model_path = os.path.abspath(str(config.edge_probability_model_path))
    model = _load_supervised_model(model_path)
    vector = [features[name] for name in EDGE_FEATURE_NAMES]
    mean = [float(value) for value in model["feature_mean"]]
    scale = [max(float(value), 1e-12) for value in model["feature_scale"]]
    standardized = [
        (value - center) / spread
        for value, center, spread in zip(vector, mean, scale)
    ]
    logits = [
        float(bias)
        + sum(float(weight) * value for weight, value in zip(row, standardized))
        for row, bias in zip(model["weights"], model["bias"])
    ]
    temperature = (
        config.edge_probability_temperature
        * max(float(model.get("temperature", 1.0) or 1.0), 1e-12)
    )
    probabilities = _softmax_triplet(logits, temperature)
    return probabilities, {
        "logits": dict(zip(STATE_NAMES, (round(value, 6) for value in logits))),
        "temperature": round(temperature, 6),
        "model_id": model.get("model_id", os.path.basename(model_path)),
        "feature_names": list(EDGE_FEATURE_NAMES),
        "dynamic_support_available": bool(features["any_dynamic_support"] > 0.0),
        "decision_policy": dict(
            model.get(
                "decision_policy",
                {
                    "direction_min_probability": 0.50,
                    "direction_vs_no_direct_margin": 0.10,
                    "selection_objective": "conservative_legacy_default",
                },
            )
        ),
    }


def assign_edge_state_probabilities(
    edge_hypothesis: Mapping[str, Any],
    *,
    config: PropagationConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Convert root-independent evidence features into three exclusive states."""

    cfg = normalize_config(config)
    method = cfg.edge_probability_method
    if method == "deterministic_evidence_v1":
        probabilities = _deterministic_probabilities(edge_hypothesis)
        details: Mapping[str, Any] | None = None
    elif method == "logit_softmax_v1":
        probabilities, details = _logit_probabilities(edge_hypothesis, cfg)
    elif method == "supervised_softmax_v1":
        probabilities, details = _supervised_probabilities(edge_hypothesis, cfg)
    else:  # normalize_config validates this; retain a defensive runtime guard.
        raise ValueError(f"unsupported edge probability method: {method}")
    return _result(
        edge_hypothesis,
        probabilities,
        method=method,
        details=details,
    )
