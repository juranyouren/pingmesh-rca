from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import replace
from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple

from Sys.RootCauseAnalyze.propagation.heterogeneous.builder import (
    device_node_id,
    event_node_id,
    symptom_node_id,
)
from Sys.RootCauseAnalyze.propagation.heterogeneous.schema import (
    M3_HETEROGENEOUS_SCHEMA_VERSION,
    HeterogeneousConfig,
    normalize_heterogeneous_config,
)
from Sys.RootCauseAnalyze.propagation.m2 import infer_root_paths
from Sys.RootCauseAnalyze.propagation.schema import (
    PropagationConfig,
    normalize_config,
    root_devices,
)


def _would_create_cycle(
    adjacency: Mapping[str, Set[str]], source: str, target: str
) -> bool:
    if source == target:
        return True
    queue = deque([target])
    seen = {target}
    while queue:
        node = queue.popleft()
        if node == source:
            return True
        for neighbor in adjacency.get(node, set()):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return False


def _root_rankings(
    root_potentials: Sequence[Mapping[str, Any]], config: HeterogeneousConfig
) -> List[Dict[str, Any]]:
    rows = []
    for index, item in enumerate(root_potentials[: config.max_root_candidates], 1):
        device_id = str(item.get("device_id", "") or "")
        if not device_id:
            continue
        rows.append(
            {
                "rank": index,
                "ip": device_id,
                "combined_score": float(item.get("root_potential", 0.0) or 0.0),
                "decision_state": "internal_root_potential_v0",
                "evidence_ids": list(item.get("evidence_ids", [])),
            }
        )
    return rows


def _selected_devices(graph: Mapping[str, Any]) -> Set[str]:
    devices = {
        str(item.get("device_id"))
        for item in graph.get("nodes", [])
        if isinstance(item, Mapping) and item.get("device_id")
    }
    for item in graph.get("edges", []):
        if not isinstance(item, Mapping):
            continue
        for key in ("from", "to"):
            value = str(item.get(key, "") or "")
            if value:
                devices.add(value)
    root = graph.get("root_hypothesis", {})
    if isinstance(root, Mapping):
        devices.update(root_devices(root))
    return devices


def _selected_event_layer(
    heterogeneous_graph: Mapping[str, Any],
    event_relations: Sequence[Mapping[str, Any]],
    device_graph: Mapping[str, Any],
) -> Dict[str, Any]:
    selected_devices = _selected_devices(device_graph)
    selected_device_edges = {
        (str(item.get("from", "")), str(item.get("to", "")))
        for item in device_graph.get("edges", [])
        if isinstance(item, Mapping) and item.get("from") and item.get("to")
    }
    events = {
        str(item.get("evidence_id")): dict(item)
        for item in heterogeneous_graph.get("nodes", [])
        if isinstance(item, Mapping)
        and item.get("node_type") == "event"
        and item.get("evidence_id")
        and str(item.get("device_id", "")) in selected_devices
    }

    candidates: List[Tuple[float, str, str, Mapping[str, Any]]] = []
    for relation in event_relations:
        if not isinstance(relation, Mapping):
            continue
        a = str(relation.get("endpoint_a", "") or "")
        b = str(relation.get("endpoint_b", "") or "")
        if a not in events or b not in events:
            continue
        probabilities = relation.get("state_probabilities", {})
        if not isinstance(probabilities, Mapping):
            continue
        p_ab = float(probabilities.get("endpoint_a_to_b", 0.0) or 0.0)
        p_ba = float(probabilities.get("endpoint_b_to_a", 0.0) or 0.0)
        p_none = float(probabilities.get("no_dependency", 0.0) or 0.0)
        if max(p_ab, p_ba) <= p_none or max(p_ab, p_ba) < 0.40:
            continue
        source, target, probability = (a, b, p_ab) if p_ab >= p_ba else (b, a, p_ba)
        source_device = str(events[source].get("device_id", "") or "")
        target_device = str(events[target].get("device_id", "") or "")
        if source_device != target_device and (
            source_device,
            target_device,
        ) not in selected_device_edges:
            continue
        candidates.append((-probability, source, target, relation))

    adjacency: Dict[str, Set[str]] = defaultdict(set)
    selected_relations: List[Dict[str, Any]] = []
    for negative_probability, source, target, relation in sorted(candidates):
        if _would_create_cycle(adjacency, source, target):
            continue
        adjacency[source].add(target)
        selected_relations.append(
            {
                "relation_id": f"EE:{len(selected_relations) + 1:05d}",
                "relation_type": "event_dependency_or_evolution",
                "source": event_node_id(source),
                "target": event_node_id(target),
                "source_evidence_id": source,
                "target_evidence_id": target,
                "probability": round(-negative_probability, 6),
                "evidence_ids": [source, target],
                "is_propagation_edge": False,
                "semantics": "dependency_or_evolution_not_proven_causality",
            }
        )

    event_nodes = [events[key] for key in sorted(events)]
    grounding_relations = [
        {
            "relation_id": f"GROUND:{event_id}",
            "relation_type": "event_observed_on_device",
            "source": event_node_id(event_id),
            "target": device_node_id(str(events[event_id].get("device_id", ""))),
            "directed": False,
            "evidence_ids": [event_id],
            "is_propagation_edge": False,
        }
        for event_id in sorted(events)
    ]
    covered_targets = {
        str(value) for value in device_graph.get("covered_targets", []) if value
    }
    symptom_relations = [
        {
            "relation_id": f"IMPACT:{device_id}",
            "relation_type": "device_explains_pingmesh_symptom",
            "source": device_node_id(device_id),
            "target": symptom_node_id(),
            "directed": True,
            "is_propagation_edge": False,
        }
        for device_id in sorted(covered_targets)
    ]
    return {
        "event_nodes": event_nodes,
        "event_relations": selected_relations,
        "evidence_grounding_relations": grounding_relations,
        "symptom_explanation_relations": symptom_relations,
    }


def _compact_root_graph_hypothesis(item: Mapping[str, Any]) -> Dict[str, Any]:
    root = item.get("root_hypothesis", {})
    propagation = item.get("propagation_graph", {})
    root_ids = root_devices(root) if isinstance(root, Mapping) else []
    return {
        "root_device": root_ids[0] if root_ids else None,
        "root_potential": (
            float(root.get("support_score", 0.0) or 0.0)
            if isinstance(root, Mapping)
            else 0.0
        ),
        "explanation_score": float(item.get("explanation_score", 0.0) or 0.0),
        "joint_score": float(item.get("final_score", 0.0) or 0.0),
        "target_coverage": (
            float(propagation.get("target_coverage", 0.0) or 0.0)
            if isinstance(propagation, Mapping)
            else 0.0
        ),
        "device_edges": [
            dict(edge)
            for edge in (
                propagation.get("edges", []) if isinstance(propagation, Mapping) else []
            )
            if isinstance(edge, Mapping)
        ],
    }


def _identifiability(
    inference: Mapping[str, Any],
    selected_graph: Mapping[str, Any],
    config: HeterogeneousConfig,
) -> Dict[str, Any]:
    rankings = [
        dict(item)
        for item in inference.get("final_root_rankings", [])
        if isinstance(item, Mapping)
    ]
    best = float(rankings[0].get("final_score", 0.0) or 0.0) if rankings else 0.0
    second = float(rankings[1].get("final_score", 0.0) or 0.0) if len(rankings) > 1 else 0.0
    margin = best - second
    coverage = float(selected_graph.get("target_coverage", 0.0) or 0.0)
    has_device_edges = bool(selected_graph.get("edges"))
    if not rankings or not has_device_edges or coverage <= 0.0:
        state = "unidentifiable"
        reason = "no_supported_root_to_symptom_graph"
    elif margin >= config.identifiability_margin:
        state = "identifiable"
        reason = "root_and_graph_score_margin_is_stable"
    else:
        state = "partially_identifiable"
        reason = "near_tied_root_graph_hypotheses"
    return {
        "state": state,
        "reason": reason,
        "best_second_margin": round(margin, 6),
        "threshold": config.identifiability_margin,
        "method": "score_margin_baseline_v0",
    }


def decode_joint_root_and_graph(
    hypothesis_graph: Mapping[str, Any],
    heterogeneous_graph: Mapping[str, Any],
    probabilistic_graph: Mapping[str, Any],
    *,
    propagation_config: PropagationConfig | Mapping[str, Any] | None = None,
    heterogeneous_config: HeterogeneousConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Jointly select a single device root and its propagation explanation.

    V0 uses bounded enumeration: each internally scored device root is decoded
    with the shared DD probability graph, and the root/graph joint score selects
    the result.  This removes the external-root requirement while keeping the
    implementation dependency-free.
    """

    pcfg = normalize_config(propagation_config)
    hcfg = normalize_heterogeneous_config(heterogeneous_config)
    rankings = _root_rankings(probabilistic_graph.get("root_potentials", []), hcfg)
    joint_config = replace(
        pcfg,
        root_top_k=max(1, min(hcfg.max_root_candidates, len(rankings) or 1)),
        stage1_weight=hcfg.root_potential_weight,
    )
    inference = infer_root_paths(
        hypothesis_graph=hypothesis_graph,
        initial_root_rankings=rankings,
        config=joint_config,
    )
    selected_graph = (
        dict(inference.get("selected_propagation_graph", {}))
        if isinstance(inference.get("selected_propagation_graph"), Mapping)
        else {}
    )
    event_layer = _selected_event_layer(
        heterogeneous_graph,
        probabilistic_graph.get("event_relations", []),
        selected_graph,
    )
    solved = [
        dict(item)
        for item in inference.get("root_conditioned_propagation_graphs", [])
        if isinstance(item, Mapping)
    ]
    solved.sort(
        key=lambda item: (
            -float(item.get("final_score", 0.0) or 0.0),
            str(item.get("root_hypothesis", {}).get("hypothesis_id", "")),
        )
    )
    alternatives = [
        _compact_root_graph_hypothesis(item)
        for item in solved[: hcfg.max_root_graph_hypotheses]
    ]
    selected_evidence_ids = {
        str(evidence_id)
        for item in [
            *selected_graph.get("nodes", []),
            *selected_graph.get("edges", []),
            *event_layer["event_relations"],
        ]
        if isinstance(item, Mapping)
        for evidence_id in item.get("evidence_ids", [])
        if evidence_id
    }
    evidence_map = heterogeneous_graph.get("evidence_map", {})
    selected_evidence = {
        evidence_id: dict(evidence_map[evidence_id])
        for evidence_id in sorted(selected_evidence_ids)
        if isinstance(evidence_map, Mapping)
        and evidence_id in evidence_map
        and isinstance(evidence_map[evidence_id], Mapping)
    }
    return {
        "schema_version": M3_HETEROGENEOUS_SCHEMA_VERSION,
        "decoder_type": "bounded_single_device_root_enumeration_v0",
        "selected_root": inference.get("selected_root"),
        "device_propagation_graph": selected_graph,
        "event_explanation_graph": {
            "nodes": event_layer["event_nodes"],
            "relations": event_layer["event_relations"],
        },
        "evidence_grounding_relations": event_layer[
            "evidence_grounding_relations"
        ],
        "symptom_explanation_relations": event_layer[
            "symptom_explanation_relations"
        ],
        "root_graph_hypotheses": alternatives,
        "identifiability": _identifiability(inference, selected_graph, hcfg),
        "evidence_map": selected_evidence,
        "diagnostics": {
            "root_candidates_considered": len(rankings),
            "joint_root_graph_search": True,
            "oracle_root_used": False,
            "root_scope": "single_device_only",
            "exact_cp_sat": False,
            "selected_event_count": len(event_layer["event_nodes"]),
            "selected_event_relation_count": len(event_layer["event_relations"]),
        },
        "config_version": hcfg.config_version,
    }
