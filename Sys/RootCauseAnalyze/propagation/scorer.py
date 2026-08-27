from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple

from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig, normalize_config


def _episode_index(episodes: Sequence[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for raw in episodes:
        device_id = str(raw.get("device_id", "") or "")
        if device_id:
            result[device_id].append(dict(raw))
    return result


def _earliest_interval(device_episodes: Sequence[Mapping[str, Any]]) -> List[int] | None:
    intervals = [
        item.get("onset_interval_ms")
        for item in device_episodes
        if isinstance(item.get("onset_interval_ms"), list)
        and len(item.get("onset_interval_ms")) == 2
        and item.get("lifecycle") != "clear"
    ]
    if not intervals:
        return None
    return list(min(intervals, key=lambda value: (value[0], value[1])))


def _temporal_support(
    upstream: Sequence[Mapping[str, Any]],
    downstream: Sequence[Mapping[str, Any]],
    config: PropagationConfig,
) -> Tuple[float, List[int] | None, float]:
    u_interval = _earliest_interval(upstream)
    v_interval = _earliest_interval(downstream)
    if u_interval is None or v_interval is None:
        return 0.0, None, 0.0
    lag = [v_interval[0] - u_interval[1], v_interval[1] - u_interval[0]]
    allowed_low = -config.negative_lag_tolerance_ms
    allowed_high = config.max_propagation_lag_ms
    if lag[1] < allowed_low or lag[0] > allowed_high:
        return 0.0, lag, 0.65
    midpoint = (lag[0] + lag[1]) / 2.0
    if midpoint < 0:
        score = max(0.35, 1.0 - abs(midpoint) / max(config.negative_lag_tolerance_ms, 1))
    else:
        score = max(0.25, 1.0 - midpoint / max(config.max_propagation_lag_ms, 1))
    return round(min(score, 1.0), 6), lag, 0.0


def _semantic_support(
    upstream_id: str,
    downstream_id: str,
    upstream: Sequence[Mapping[str, Any]],
    downstream: Sequence[Mapping[str, Any]],
) -> Tuple[float, float, str, List[str], List[str]]:
    support = 0.0
    contradiction = 0.0
    relation = "inferred_impact"
    supporting: Set[str] = set()
    counter: Set[str] = set()

    u_types = {str(item.get("event_type", "")) for item in upstream}
    v_types = {str(item.get("event_type", "")) for item in downstream}
    physical_types = {"physical_link_down", "interface_state_down"}
    derivative_types = {
        "bgp_session_down",
        "bfd_session_down",
        "lldp_neighbor_change",
        "routing_change",
    }
    if u_types & physical_types and v_types & derivative_types:
        support = 1.0
        relation = "routing_convergence"
    elif u_types & physical_types and v_types & physical_types:
        support = 0.45
        relation = "physical_link"
    elif u_types & derivative_types and v_types & physical_types:
        contradiction = 0.65

    if support > 0 and not supporting:
        supporting.update(
            str(item.get("evidence_id"))
            for item in [*upstream, *downstream]
            if item.get("evidence_id")
            and float(item.get("incident_relevance", 0.0) or 0.0) >= 0.45
        )
    return support, contradiction, relation, sorted(supporting), sorted(counter)


def _direct_relation_support(
    upstream_id: str,
    downstream_id: str,
    upstream: Sequence[Mapping[str, Any]],
    downstream: Sequence[Mapping[str, Any]],
) -> Tuple[float, float, List[str], List[str]]:
    supporting: Set[str] = set()
    counter: Set[str] = set()
    support = 0.0
    contradiction = 0.0
    for item in upstream:
        if item.get("peer_device") != downstream_id:
            continue
        evidence_id = item.get("evidence_id")
        scope = str(item.get("observation_scope", "unknown"))
        if scope == "remote":
            contradiction = max(contradiction, 0.9)
            if evidence_id:
                counter.add(str(evidence_id))
        else:
            support = max(support, 1.0 if scope == "local" else 0.8)
            if evidence_id:
                supporting.add(str(evidence_id))
    for item in downstream:
        if item.get("peer_device") != upstream_id:
            continue
        evidence_id = item.get("evidence_id")
        scope = str(item.get("observation_scope", "unknown"))
        if scope == "local":
            contradiction = max(contradiction, 0.9)
            if evidence_id:
                counter.add(str(evidence_id))
        else:
            support = max(support, 1.0 if scope == "remote" else 0.8)
            if evidence_id:
                supporting.add(str(evidence_id))
    return support, contradiction, sorted(supporting), sorted(counter)


def _direction_case_hypothesis(
    *,
    upstream_id: str,
    downstream_id: str,
    candidate_edge: Mapping[str, Any],
    episode_by_device: Mapping[str, Sequence[Mapping[str, Any]]],
    config: PropagationConfig,
) -> Dict[str, Any]:
    upstream = episode_by_device.get(upstream_id, [])
    downstream = episode_by_device.get(downstream_id, [])
    semantic, semantic_contradiction, relation, semantic_ids, counter_ids = _semantic_support(
        upstream_id, downstream_id, upstream, downstream
    )
    temporal, lag_interval, temporal_contradiction = _temporal_support(upstream, downstream, config)
    direct, direct_contradiction, direct_ids, direct_counter_ids = (
        _direct_relation_support(
            upstream_id,
            downstream_id,
            upstream,
            downstream,
        )
    )
    contradiction = max(
        semantic_contradiction,
        temporal_contradiction,
        direct_contradiction,
    )
    # Probability evidence is intentionally limited to the three evidence
    # families in the method definition. Topology only decides which adjacent
    # device pairs are evaluated; it contributes no propagation-state score.
    score = 0.35 * temporal + 0.35 * semantic + 0.30 * direct - 0.35 * contradiction
    evidence_ids = sorted(
        set(semantic_ids)
        | set(direct_ids)
        | {
            str(item.get("evidence_id"))
            for item in [*upstream, *downstream]
            if item.get("evidence_id")
            and float(item.get("incident_relevance", 0.0) or 0.0) >= 0.45
        }
        | set(candidate_edge.get("direct_relation_evidence_ids", []))
    )[:20]
    return {
        "from": upstream_id,
        "to": downstream_id,
        "relation": relation,
        "case_support_score": round(max(0.0, min(1.0, score)), 6),
        "lag_interval_ms": lag_interval,
        "features": {
            "topology_valid": 1.0,
            "temporal_order_support": round(temporal, 6),
            "semantic_pair_support": round(semantic, 6),
            "direct_relation_support": round(direct, 6),
            "temporal_compatibility": round(temporal, 6),
            "temporal_available": lag_interval is not None,
            "case_contradiction": round(contradiction, 6),
        },
        "evidence_ids": evidence_ids,
        "counter_evidence_ids": sorted(set(counter_ids) | set(direct_counter_ids)),
    }


def build_edge_relation_graph(
    candidate_graph: Mapping[str, Any],
    episodes: Sequence[Mapping[str, Any]],
    *,
    config: PropagationConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Create root-independent edge states before constructing any DAG."""

    cfg = normalize_config(config)
    episode_by_device = _episode_index(episodes)
    hypotheses: List[Dict[str, Any]] = []
    state_counts: Counter[str] = Counter()

    for index, raw_edge in enumerate(candidate_graph.get("edges", []), 1):
        if not isinstance(raw_edge, Mapping):
            continue
        candidate_edge = dict(raw_edge)
        endpoint_a = str(candidate_edge.get("endpoint_a", "") or "")
        endpoint_b = str(candidate_edge.get("endpoint_b", "") or "")
        if not endpoint_a or not endpoint_b or endpoint_a == endpoint_b:
            continue
        directions = [
            _direction_case_hypothesis(
                upstream_id=upstream,
                downstream_id=downstream,
                candidate_edge=candidate_edge,
                episode_by_device=episode_by_device,
                config=cfg,
            )
            for upstream, downstream in ((endpoint_a, endpoint_b), (endpoint_b, endpoint_a))
        ]
        directions.sort(key=lambda item: (-float(item["case_support_score"]), item["from"], item["to"]))
        best_score = float(directions[0]["case_support_score"])
        other_score = float(directions[1]["case_support_score"])
        direction_gap = round(best_score - other_score, 6)
        semantic = max(
            float(item["features"].get("semantic_pair_support", 0.0) or 0.0) for item in directions
        )
        temporal = max(
            float(item["features"].get("temporal_compatibility", 0.0) or 0.0) for item in directions
        )
        direct = max(
            float(item["features"].get("direct_relation_support", 0.0) or 0.0)
            for item in directions
        )
        contradiction = max(
            float(item["features"].get("case_contradiction", 0.0) or 0.0)
            for item in directions
        )
        endpoint_a_events = episode_by_device.get(endpoint_a, [])
        endpoint_b_events = episode_by_device.get(endpoint_b, [])
        if not endpoint_a_events and not endpoint_b_events:
            semantic_no_direct = 1.0
        elif not endpoint_a_events or not endpoint_b_events:
            semantic_no_direct = 0.75
        else:
            # Alarm semantics may explicitly favor no direct propagation.
            # Direct peer/local-remote evidence reduces that alternative.
            semantic_no_direct = (1.0 - semantic) * (1.0 - direct) * 0.25
        inactive_support = round(
            max(0.0, min(1.0, semantic_no_direct + 0.35 * contradiction)),
            6,
        )
        if best_score < cfg.min_edge_support and inactive_support >= best_score:
            preferred_state = "inactive_or_unobserved"
        elif direction_gap <= cfg.direction_tie_margin:
            preferred_state = "direction_ambiguous"
        else:
            preferred_state = f"{directions[0]['from']}->{directions[0]['to']}"
        strength = (
            "strong"
            if best_score >= cfg.strong_edge_support
            else "moderate"
            if best_score >= cfg.moderate_edge_support
            else "weak"
            if best_score >= cfg.min_edge_support
            else "unobserved"
        )
        state_counts[preferred_state if preferred_state in {
            "inactive_or_unobserved", "direction_ambiguous"
        } else "directional"] += 1
        hypotheses.append(
            {
                "edge_hypothesis_id": f"EH{index:05d}",
                "endpoint_a": endpoint_a,
                "endpoint_b": endpoint_b,
                "edge_type": candidate_edge.get("edge_type", "physical"),
                "topology_edge_ids": list(candidate_edge.get("topology_edge_ids", [])),
                "states": {
                    "no_direct_propagation": inactive_support,
                },
                "directions": directions,
                "preferred_state": preferred_state,
                "relation_strength": strength,
                "direction_gap": direction_gap,
            }
        )

    return {
        "graph_type": "root_independent_weighted_relation_hypotheses",
        "edge_hypotheses": hypotheses,
        "summary": {
            "candidate_pair_count": len(hypotheses),
            "state_counts": dict(sorted(state_counts.items())),
            "interface_evidence_required": False,
        },
    }
