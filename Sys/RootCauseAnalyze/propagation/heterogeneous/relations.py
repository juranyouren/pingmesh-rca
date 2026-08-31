from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from Sys.RootCauseAnalyze.propagation.heterogeneous.schema import (
    M2_HETEROGENEOUS_SCHEMA_VERSION,
    HeterogeneousConfig,
    normalize_heterogeneous_config,
)


def _direction_probability(pair: Mapping[str, Any], source: str, target: str) -> float:
    probabilities = pair.get("state_probabilities", {})
    if not isinstance(probabilities, Mapping):
        return 0.0
    endpoint_a = str(pair.get("endpoint_a", "") or "")
    endpoint_b = str(pair.get("endpoint_b", "") or "")
    if (source, target) == (endpoint_a, endpoint_b):
        key = "endpoint_a_to_b"
    elif (source, target) == (endpoint_b, endpoint_a):
        key = "endpoint_b_to_a"
    else:
        return 0.0
    return float(probabilities.get(key, 0.0) or 0.0)


def _event_time_center(event: Mapping[str, Any]) -> float | None:
    interval = event.get("onset_interval_ms")
    if isinstance(interval, list) and len(interval) == 2:
        try:
            return (float(interval[0]) + float(interval[1])) / 2.0
        except (TypeError, ValueError):
            return None
    return None


def _softmax(values: Sequence[float], temperature: float) -> List[float]:
    if not values:
        return []
    scaled = [float(value) / max(temperature, 1e-12) for value in values]
    maximum = max(scaled)
    exponentials = [math.exp(value - maximum) for value in scaled]
    denominator = sum(exponentials)
    return [value / denominator for value in exponentials]


def infer_root_potentials(
    heterogeneous_graph: Mapping[str, Any],
    device_relations: Sequence[Mapping[str, Any]],
    *,
    config: HeterogeneousConfig | Mapping[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """Produce an internal, label-free unary root potential for V0.

    This is deliberately an interpretable placeholder for the learned root
    head.  It never reads a root label or an external candidate ranking.
    """

    cfg = normalize_heterogeneous_config(config)
    devices = [
        dict(item)
        for item in heterogeneous_graph.get("nodes", [])
        if isinstance(item, Mapping)
        and item.get("node_type") == "device"
        and item.get("device_id")
    ]
    events_by_device: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in heterogeneous_graph.get("nodes", []):
        if not isinstance(item, Mapping) or item.get("node_type") != "event":
            continue
        device_id = str(item.get("device_id", "") or "")
        if device_id:
            events_by_device[device_id].append(dict(item))

    earliest_by_device: Dict[str, float] = {}
    for device_id, events in events_by_device.items():
        times = [value for event in events if (value := _event_time_center(event)) is not None]
        if times:
            earliest_by_device[device_id] = min(times)
    global_min = min(earliest_by_device.values(), default=0.0)
    global_max = max(earliest_by_device.values(), default=0.0)

    directional_by_device: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    for pair in device_relations:
        if not isinstance(pair, Mapping):
            continue
        a = str(pair.get("endpoint_a", "") or "")
        b = str(pair.get("endpoint_b", "") or "")
        if not a or not b:
            continue
        directional_by_device[a].append(
            (_direction_probability(pair, a, b), _direction_probability(pair, b, a))
        )
        directional_by_device[b].append(
            (_direction_probability(pair, b, a), _direction_probability(pair, a, b))
        )

    rows: List[Dict[str, Any]] = []
    raw_scores: List[float] = []
    for device in devices:
        device_id = str(device["device_id"])
        events = events_by_device.get(device_id, [])
        relevances = [float(item.get("incident_relevance", 0.0) or 0.0) for item in events]
        event_support = (
            0.7 * max(relevances, default=0.0)
            + 0.3 * (sum(relevances) / len(relevances) if relevances else 0.0)
        )
        earliest = earliest_by_device.get(device_id)
        if earliest is None:
            early_support = 0.0
        elif global_max > global_min:
            early_support = (global_max - earliest) / (global_max - global_min)
        else:
            early_support = 0.5
        direction_values = directional_by_device.get(device_id, [])
        if direction_values:
            outward_support = sum(
                max(0.0, outgoing - incoming) + 0.5 * outgoing
                for outgoing, incoming in direction_values
            ) / (1.5 * len(direction_values))
        else:
            outward_support = 0.0
        corridor_support = 1.0 if device.get("in_corridor") else 0.0
        endpoint_distance_values = [
            float(value)
            for value in (device.get("source_distance"), device.get("sink_distance"))
            if isinstance(value, (int, float))
        ]
        structural_support = (
            1.0 / (1.0 + min(endpoint_distance_values))
            if endpoint_distance_values
            else 0.0
        )
        raw_score = (
            0.45 * event_support
            + 0.20 * early_support
            + 0.20 * outward_support
            + 0.10 * corridor_support
            + 0.05 * structural_support
        )
        raw_scores.append(raw_score)
        rows.append(
            {
                "device_id": device_id,
                "root_logit": round(raw_score, 6),
                "components": {
                    "event_support": round(event_support, 6),
                    "early_event_support": round(early_support, 6),
                    "outward_relation_support": round(outward_support, 6),
                    "corridor_support": round(corridor_support, 6),
                    "structural_support": round(structural_support, 6),
                },
                "evidence_ids": sorted(
                    {
                        str(item.get("evidence_id"))
                        for item in events
                        if item.get("evidence_id")
                    }
                ),
                "potential_method": "interpretable_unary_baseline_v0",
            }
        )

    probabilities = _softmax(raw_scores, cfg.root_softmax_temperature)
    for row, probability in zip(rows, probabilities):
        row["root_potential"] = round(probability, 6)
    return sorted(
        rows,
        key=lambda item: (-float(item.get("root_potential", 0.0)), item["device_id"]),
    )


def _semantic_rank(event: Mapping[str, Any]) -> float:
    layer = str(event.get("fault_layer", "unknown") or "unknown")
    return {
        "management": 0.0,
        "device": 0.0,
        "physical": 0.0,
        "control_plane": 1.0,
        "routing": 2.0,
        "unknown": 1.0,
    }.get(layer, 1.0)


def _event_direction_score(
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    device_direction: float,
    tolerance_ms: int,
) -> Tuple[float, Dict[str, float]]:
    source_time = _event_time_center(source)
    target_time = _event_time_center(target)
    if source_time is None or target_time is None:
        temporal = 0.25
    elif source_time <= target_time + tolerance_ms:
        gap = max(0.0, target_time - source_time)
        temporal = max(0.35, 1.0 - gap / 600_000.0)
    else:
        temporal = 0.05
    source_rank = _semantic_rank(source)
    target_rank = _semantic_rank(target)
    semantic = 1.0 if source_rank <= target_rank else 0.15
    relevance = min(
        float(source.get("incident_relevance", 0.0) or 0.0),
        float(target.get("incident_relevance", 0.0) or 0.0),
    )
    score = (
        0.15
        + 0.35 * temporal
        + 0.25 * semantic
        + 0.15 * device_direction
        + 0.10 * relevance
    )
    return score, {
        "temporal_support": round(temporal, 6),
        "semantic_transition_support": round(semantic, 6),
        "device_direction_support": round(device_direction, 6),
        "incident_relevance": round(relevance, 6),
    }


def infer_event_relation_probabilities(
    heterogeneous_graph: Mapping[str, Any],
    device_relations: Sequence[Mapping[str, Any]],
    *,
    config: HeterogeneousConfig | Mapping[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """Score EE direction/no-dependency states for the runnable baseline."""

    cfg = normalize_heterogeneous_config(config)
    events = {
        str(item.get("evidence_id")): dict(item)
        for item in heterogeneous_graph.get("nodes", [])
        if isinstance(item, Mapping)
        and item.get("node_type") == "event"
        and item.get("evidence_id")
    }
    device_pairs = {
        tuple(sorted((str(item.get("endpoint_a", "")), str(item.get("endpoint_b", ""))))): item
        for item in device_relations
        if isinstance(item, Mapping)
        and item.get("endpoint_a")
        and item.get("endpoint_b")
    }
    rows: List[Dict[str, Any]] = []
    for pair in heterogeneous_graph.get("candidate_event_pairs", []):
        if not isinstance(pair, Mapping):
            continue
        a = str(pair.get("endpoint_a", "") or "")
        b = str(pair.get("endpoint_b", "") or "")
        event_a = events.get(a)
        event_b = events.get(b)
        if event_a is None or event_b is None:
            continue
        device_a = str(event_a.get("device_id", "") or "")
        device_b = str(event_b.get("device_id", "") or "")
        if device_a == device_b:
            dd_a_to_b = dd_b_to_a = 0.5
        else:
            dd_pair = device_pairs.get(tuple(sorted((device_a, device_b))), {})
            dd_a_to_b = _direction_probability(dd_pair, device_a, device_b)
            dd_b_to_a = _direction_probability(dd_pair, device_b, device_a)
        forward_score, forward_features = _event_direction_score(
            event_a,
            event_b,
            device_direction=dd_a_to_b,
            tolerance_ms=cfg.event_time_tolerance_ms,
        )
        reverse_score, reverse_features = _event_direction_score(
            event_b,
            event_a,
            device_direction=dd_b_to_a,
            tolerance_ms=cfg.event_time_tolerance_ms,
        )
        missing_time = _event_time_center(event_a) is None or _event_time_center(event_b) is None
        generic = (
            event_a.get("event_type") == "generic_event"
            or event_b.get("event_type") == "generic_event"
        )
        no_dependency_score = 0.25 + (0.20 if missing_time else 0.0) + (0.15 if generic else 0.0)
        probabilities = _softmax(
            [forward_score, reverse_score, no_dependency_score],
            temperature=1.0,
        )
        probability_map = {
            "endpoint_a_to_b": round(probabilities[0], 6),
            "endpoint_b_to_a": round(probabilities[1], 6),
            "no_dependency": round(probabilities[2], 6),
        }
        preferred_key = max(probability_map, key=lambda key: probability_map[key])
        preferred_state = {
            "endpoint_a_to_b": f"{a}->{b}",
            "endpoint_b_to_a": f"{b}->{a}",
            "no_dependency": "no_dependency",
        }[preferred_key]
        entropy = -sum(
            value * math.log(value)
            for value in probability_map.values()
            if value > 0.0
        )
        rows.append(
            {
                "event_pair_id": pair.get("event_pair_id"),
                "endpoint_a": a,
                "endpoint_b": b,
                "endpoint_a_device": device_a,
                "endpoint_b_device": device_b,
                "state_probabilities": probability_map,
                "preferred_state": preferred_state,
                "forward_features": forward_features,
                "reverse_features": reverse_features,
                "distribution_entropy": round(entropy, 6),
                "probability_method": "temporal_semantic_baseline_v0",
                "relation_semantics": "dependency_or_evolution_not_proven_causality",
            }
        )
    return rows


def build_probabilistic_heterogeneous_relations(
    heterogeneous_graph: Mapping[str, Any],
    device_relations: Sequence[Mapping[str, Any]],
    *,
    config: HeterogeneousConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    cfg = normalize_heterogeneous_config(config)
    root_potentials = infer_root_potentials(
        heterogeneous_graph, device_relations, config=cfg
    )
    event_relations = infer_event_relation_probabilities(
        heterogeneous_graph, device_relations, config=cfg
    )
    return {
        "schema_version": M2_HETEROGENEOUS_SCHEMA_VERSION,
        "model_type": "interpretable_relation_baseline_v0",
        "root_potentials": root_potentials,
        "device_relations": [dict(item) for item in device_relations],
        "event_relations": event_relations,
        "fixed_observation_relations": [
            dict(item)
            for item in heterogeneous_graph.get("relations", [])
            if isinstance(item, Mapping)
            and item.get("relation_type")
            in {"event_observed_on_device", "device_symptom_anchor"}
        ],
        "diagnostics": {
            "root_candidate_count": len(root_potentials),
            "device_relation_count": len(device_relations),
            "event_relation_count": len(event_relations),
            "learned_model": False,
            "calibrated_probabilities": False,
        },
        "config_version": cfg.config_version,
    }
