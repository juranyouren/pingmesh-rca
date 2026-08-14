from __future__ import annotations

from math import log
from typing import Any, Dict, Mapping


def _normalized_triplet(forward: float, reverse: float, no_direct: float) -> tuple[float, float, float]:
    values = [max(0.0, float(forward)), max(0.0, float(reverse)), max(0.0, float(no_direct))]
    total = sum(values)
    if total <= 0.0:
        values = [1.0, 1.0, 1.0]
        total = 3.0
    normalized = [value / total for value in values]
    rounded = [round(normalized[0], 6), round(normalized[1], 6)]
    rounded.append(round(1.0 - rounded[0] - rounded[1], 6))
    return rounded[0], rounded[1], rounded[2]


def assign_edge_state_probabilities(edge_hypothesis: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize evidence support into three mutually exclusive edge states."""

    endpoint_a = str(edge_hypothesis.get("endpoint_a", "") or "")
    endpoint_b = str(edge_hypothesis.get("endpoint_b", "") or "")
    directions = [
        dict(item)
        for item in edge_hypothesis.get("directions", [])
        if isinstance(item, Mapping)
    ]
    by_direction = {
        (str(item.get("from", "")), str(item.get("to", ""))): item
        for item in directions
    }
    forward = by_direction.get((endpoint_a, endpoint_b), {})
    reverse = by_direction.get((endpoint_b, endpoint_a), {})
    states = edge_hypothesis.get("states", {})
    no_direct_support = max(
        float(states.get("no_direct_propagation", 0.0) or 0.0),
        float(states.get("inactive_or_unobserved", 0.0) or 0.0),
    )
    p_forward, p_reverse, p_no_direct = _normalized_triplet(
        float(forward.get("case_support_score", 0.0) or 0.0),
        float(reverse.get("case_support_score", 0.0) or 0.0),
        no_direct_support,
    )
    for item in directions:
        key = (str(item.get("from", "")), str(item.get("to", "")))
        if key == (endpoint_a, endpoint_b):
            item["state_probability"] = p_forward
        elif key == (endpoint_b, endpoint_a):
            item["state_probability"] = p_reverse

    probabilities = {
        "endpoint_a_to_b": p_forward,
        "endpoint_b_to_a": p_reverse,
        "no_direct_propagation": p_no_direct,
    }
    entropy = -sum(value * log(value) for value in probabilities.values() if value > 0.0)
    preferred_key = max(
        probabilities,
        key=lambda key: (probabilities[key], key == "no_direct_propagation", key),
    )
    preferred_state = {
        "endpoint_a_to_b": f"{endpoint_a}->{endpoint_b}",
        "endpoint_b_to_a": f"{endpoint_b}->{endpoint_a}",
        "no_direct_propagation": "no_direct_propagation",
    }[preferred_key]
    return {
        **dict(edge_hypothesis),
        "directions": directions,
        "state_probabilities": probabilities,
        "probability_method": "deterministic_evidence_v1",
        "distribution_entropy": round(entropy, 6),
        "preferred_state": preferred_state,
    }
