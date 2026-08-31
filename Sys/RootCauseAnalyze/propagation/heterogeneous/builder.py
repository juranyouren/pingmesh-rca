from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple

from Sys.RootCauseAnalyze.propagation.heterogeneous.schema import (
    M1_HETEROGENEOUS_SCHEMA_VERSION,
    HeterogeneousConfig,
    normalize_heterogeneous_config,
)


def device_node_id(device_id: str) -> str:
    return f"device:{device_id}"


def event_node_id(evidence_id: str) -> str:
    return f"event:{evidence_id}"


def symptom_node_id() -> str:
    return "symptom:pingmesh"


def _event_time_center(event: Mapping[str, Any]) -> float | None:
    interval = event.get("onset_interval_ms")
    if isinstance(interval, list) and len(interval) == 2:
        try:
            return (float(interval[0]) + float(interval[1])) / 2.0
        except (TypeError, ValueError):
            return None
    return None


def _select_events(
    evidence_map: Mapping[str, Any],
    candidate_devices: Set[str],
    config: HeterogeneousConfig,
) -> List[Dict[str, Any]]:
    by_device: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for raw in evidence_map.values():
        if not isinstance(raw, Mapping):
            continue
        event = dict(raw)
        device_id = str(event.get("device_id", "") or "")
        relevance = float(event.get("incident_relevance", 0.0) or 0.0)
        if device_id not in candidate_devices or relevance < config.min_event_relevance:
            continue
        by_device[device_id].append(event)

    selected: List[Dict[str, Any]] = []
    for device_id in sorted(by_device):
        ranked = sorted(
            by_device[device_id],
            key=lambda item: (
                -float(item.get("incident_relevance", 0.0) or 0.0),
                _event_time_center(item) is None,
                _event_time_center(item) or 0.0,
                str(item.get("evidence_id", "")),
            ),
        )
        selected.extend(ranked[: config.max_events_per_device])
    return selected


def _candidate_event_pairs(
    events: Sequence[Mapping[str, Any]],
    physical_pairs: Set[Tuple[str, str]],
    config: HeterogeneousConfig,
) -> List[Dict[str, Any]]:
    candidates: List[Tuple[float, str, str, Dict[str, Any]]] = []
    for index, left in enumerate(events):
        left_id = str(left.get("evidence_id", "") or "")
        left_device = str(left.get("device_id", "") or "")
        if not left_id or not left_device:
            continue
        for right in events[index + 1 :]:
            right_id = str(right.get("evidence_id", "") or "")
            right_device = str(right.get("device_id", "") or "")
            if not right_id or not right_device:
                continue
            device_pair = tuple(sorted((left_device, right_device)))
            same_device = left_device == right_device
            if not same_device and device_pair not in physical_pairs:
                continue
            left_relevance = float(left.get("incident_relevance", 0.0) or 0.0)
            right_relevance = float(right.get("incident_relevance", 0.0) or 0.0)
            left_time = _event_time_center(left)
            right_time = _event_time_center(right)
            time_bonus = 0.0
            if left_time is not None and right_time is not None:
                gap = abs(left_time - right_time)
                time_bonus = 1.0 / (1.0 + gap / 60_000.0)
            priority = left_relevance + right_relevance + 0.15 * time_bonus
            if same_device:
                priority += 0.05
            row = {
                "event_pair_id": f"EEP:{min(left_id, right_id)}:{max(left_id, right_id)}",
                "endpoint_a": min(left_id, right_id),
                "endpoint_b": max(left_id, right_id),
                "endpoint_a_device": (
                    left_device if left_id <= right_id else right_device
                ),
                "endpoint_b_device": (
                    right_device if left_id <= right_id else left_device
                ),
                "same_device": same_device,
                "candidate_basis": "same_device" if same_device else "physical_adjacent",
            }
            candidates.append((-priority, row["endpoint_a"], row["endpoint_b"], row))
    candidates.sort(key=lambda item: item[:3])
    return [item[3] for item in candidates[: config.max_event_pairs]]


def build_candidate_heterogeneous_graph(
    hypothesis_graph: Mapping[str, Any],
    info: Mapping[str, Any],
    *,
    config: HeterogeneousConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Lift the reusable device hypothesis graph into a typed evidence graph."""

    cfg = normalize_heterogeneous_config(config)
    device_rows = [
        dict(item)
        for item in hypothesis_graph.get("nodes", [])
        if isinstance(item, Mapping) and item.get("device_id")
    ]
    candidate_devices = {str(item["device_id"]) for item in device_rows}
    physical_edges = [
        dict(item)
        for item in hypothesis_graph.get("candidate_topology_edges", [])
        if isinstance(item, Mapping)
        and item.get("endpoint_a") in candidate_devices
        and item.get("endpoint_b") in candidate_devices
    ]
    physical_pairs = {
        tuple(sorted((str(item["endpoint_a"]), str(item["endpoint_b"]))))
        for item in physical_edges
    }
    evidence_map = (
        hypothesis_graph.get("evidence_map", {})
        if isinstance(hypothesis_graph.get("evidence_map"), Mapping)
        else {}
    )
    events = _select_events(evidence_map, candidate_devices, cfg)
    event_pairs = _candidate_event_pairs(events, physical_pairs, cfg)

    nodes: List[Dict[str, Any]] = []
    for row in device_rows:
        device_id = str(row["device_id"])
        nodes.append(
            {
                "node_id": device_node_id(device_id),
                "node_type": "device",
                **row,
            }
        )
    for event in events:
        evidence_id = str(event.get("evidence_id", ""))
        nodes.append(
            {
                "node_id": event_node_id(evidence_id),
                "node_type": "event",
                **dict(event),
            }
        )

    symptom_id = symptom_node_id()
    nodes.append(
        {
            "node_id": symptom_id,
            "node_type": "symptom",
            "symptom_type": "pingmesh_anomaly",
            "alarm_time": info.get("alarm_time"),
            "source": info.get("source_ip", info.get("source")),
            "sink": info.get("sink_ip", info.get("sink")),
        }
    )

    relations: List[Dict[str, Any]] = []
    for index, edge in enumerate(physical_edges, 1):
        a = str(edge["endpoint_a"])
        b = str(edge["endpoint_b"])
        relations.append(
            {
                "relation_id": f"PHY:{index:05d}",
                "relation_type": "device_physical_adjacency",
                "source": device_node_id(a),
                "target": device_node_id(b),
                "directed": False,
                "topology_edge_ids": list(edge.get("topology_edge_ids", [])),
                "is_propagation_edge": False,
            }
        )
    for event in events:
        evidence_id = str(event.get("evidence_id", ""))
        device_id = str(event.get("device_id", ""))
        relations.append(
            {
                "relation_id": f"OBS:{evidence_id}",
                "relation_type": "event_observed_on_device",
                "source": event_node_id(evidence_id),
                "target": device_node_id(device_id),
                "directed": False,
                "evidence_ids": [evidence_id],
                "is_propagation_edge": False,
            }
        )
    anchor_roles = (
        ("source", hypothesis_graph.get("source_anchors", [])),
        ("sink", hypothesis_graph.get("sink_anchors", [])),
    )
    for role, values in anchor_roles:
        for device_id in sorted({str(value) for value in values if str(value) in candidate_devices}):
            relations.append(
                {
                    "relation_id": f"SYM:{role}:{device_id}",
                    "relation_type": "device_symptom_anchor",
                    "source": device_node_id(device_id),
                    "target": symptom_id,
                    "directed": False,
                    "anchor_role": role,
                    "is_propagation_edge": False,
                }
            )
    for pair in event_pairs:
        relations.append(
            {
                "relation_id": f"CAND:{pair['event_pair_id']}",
                "relation_type": "event_dependency_candidate",
                "source": event_node_id(str(pair["endpoint_a"])),
                "target": event_node_id(str(pair["endpoint_b"])),
                "directed": False,
                "candidate_basis": pair["candidate_basis"],
                "is_propagation_edge": False,
            }
        )

    return {
        "schema_version": M1_HETEROGENEOUS_SCHEMA_VERSION,
        "graph_type": "candidate_heterogeneous_evidence_graph",
        "nodes": sorted(nodes, key=lambda item: str(item.get("node_id", ""))),
        "relations": relations,
        "candidate_event_pairs": event_pairs,
        "affected_targets": [
            dict(item)
            for item in hypothesis_graph.get("affected_targets", [])
            if isinstance(item, Mapping)
        ],
        "source_anchors": list(hypothesis_graph.get("source_anchors", [])),
        "sink_anchors": list(hypothesis_graph.get("sink_anchors", [])),
        "evidence_map": {
            str(event.get("evidence_id")): dict(event)
            for event in events
            if event.get("evidence_id")
        },
        "diagnostics": {
            "device_node_count": len(device_rows),
            "event_node_count": len(events),
            "symptom_node_count": 1,
            "physical_relation_count": len(physical_edges),
            "event_pair_count": len(event_pairs),
            "input_relations_are_observational": True,
            "root_independent": True,
        },
        "config_version": cfg.config_version,
    }
