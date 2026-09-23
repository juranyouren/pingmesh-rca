"""``decode``: anchor-conditioned backbone reconstruction and DAG augmentation.

M1 leaves a *relation likelihood graph*: for each topology-admissible device
pair, two independent directional scores. Local evidence alone cannot say which
global structure those relations belong to - two locally plausible directions
may be incompatible once assembled, and a device may carry strong evidence from
a part of the network the anchor never reached. This module turns that graph
into one propagation graph, and does it in two explicitly separated steps.

**Backbone - structural selection.**
The directional evidence is accumulated in log-odds space, so the *lift* over
the pair prior is additive and a maximum-weight arborescence is well posed.
Each device gets exactly one incoming relation, chosen so the total lift is
maximal, with cycles resolved by contraction. The anchor is forced to be the
root, which is what makes this anchor-conditioned: an arborescence rooted at
``a`` orients every edge away from ``a`` by construction, so no separate
orientation heuristic is needed or used.

**Augmentation - multi-parent recovery.**
A tree gives every device a single parent, but a real incident can have two
independent causes reaching the same device. Secondary edges are therefore
re-added under three constraints: their own directional evidence must clear a
threshold, their source must already be reachable from the anchor, and the
result must stay acyclic. The reachability constraint is what keeps the
augmentation an *outward* expansion of the anchor's graph instead of a way for
an unrelated, strongly-evidenced island to attach itself.

Two rules this module exists to enforce:

* **Structure is selected with weights that are not scores.** Contraction
  rewrites edge weights into quantities that are no longer evidence, so every
  emitted row carries the *original* probability and lift, and the reweighted
  values never leave the solver.
* **Absence of evidence is not a relation.** A device that no relation claims
  stays out of the graph. It is reported under ``diagnostics.unreached_nodes``
  and is deliberately kept out of ``nodes``: a node listed there must be
  reachable from the anchor, which is what ``trust._root_reachable`` checks.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple

from Sys.RootCauseAnalyze.propagation.m3.arborescence import (
    WeightedEdge,
    maximum_arborescence_with_null_option,
)
from Sys.RootCauseAnalyze.propagation.schema import (
    PropagationConfig,
    normalize_config,
    root_devices,
)

SCHEMA_VERSION = "anchor-conditioned-backbone-v1"

_BACKBONE_ORIGIN = "backbone"
_AUGMENTED_ORIGIN = "augmented"


@dataclass(frozen=True)
class _Direction:
    """One directional relation hypothesis, with everything needed to emit it."""

    hypothesis_id: str
    source: str
    target: str
    edge_type: str
    lift: float
    probability: float
    relation: str
    case_support_score: float
    lag_interval_ms: Any
    features: Mapping[str, Any] = field(default_factory=dict)
    evidence_ids: Tuple[str, ...] = ()
    counter_evidence_ids: Tuple[str, ...] = ()
    topology_edge_ids: Tuple[str, ...] = ()


def _as_str_tuple(values: Any) -> Tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return ()
    return tuple(sorted({str(item) for item in values if item}))


def _topology_ids_by_pair(hypothesis_graph: Mapping[str, Any]) -> Dict[Tuple[str, str], Set[str]]:
    result: Dict[Tuple[str, str], Set[str]] = {}
    for item in hypothesis_graph.get("candidate_topology_edges", []):
        if not isinstance(item, Mapping):
            continue
        endpoint_a = str(item.get("endpoint_a", "") or "")
        endpoint_b = str(item.get("endpoint_b", "") or "")
        if not endpoint_a or not endpoint_b or endpoint_a == endpoint_b:
            continue
        ids = {str(value) for value in item.get("topology_edge_ids", []) if value}
        if ids:
            result.setdefault(tuple(sorted((endpoint_a, endpoint_b))), set()).update(ids)
    return result


def _directions(
    hypothesis_graph: Mapping[str, Any],
    config: PropagationConfig,
) -> Dict[Tuple[str, str], _Direction]:
    """Collect every topology-validated directional relation, keyed ``(from, to)``.

    A pair is a candidate only when its hypothesis and the candidate topology
    agree on at least one raw topology edge id, which is the same constraint the
    beam-search solver applies. When two hypotheses claim the same ordered pair
    the stronger lift wins, with the hypothesis id breaking ties so the choice
    is deterministic.
    """

    topology_ids = _topology_ids_by_pair(hypothesis_graph)
    selected: Dict[Tuple[str, str], _Direction] = {}
    missing_details = 0

    for pair in hypothesis_graph.get("edge_hypotheses", []):
        if not isinstance(pair, Mapping):
            continue
        endpoint_a = str(pair.get("endpoint_a", "") or "")
        endpoint_b = str(pair.get("endpoint_b", "") or "")
        if not endpoint_a or not endpoint_b or endpoint_a == endpoint_b:
            continue
        validated = sorted(
            set(str(value) for value in pair.get("topology_edge_ids", []) if value)
            & topology_ids.get(tuple(sorted((endpoint_a, endpoint_b))), set())
        )
        if not validated:
            continue

        details = pair.get("probability_details")
        if not isinstance(details, Mapping):
            missing_details += 1
            continue
        prior_logit = float(details.get("prior_logit", 0.0) or 0.0)
        edge_type = str(pair.get("edge_type", "physical") or "physical")
        hypothesis_id = str(pair.get("edge_hypothesis_id", "") or "")

        by_endpoints = {
            (str(item.get("from", "") or ""), str(item.get("to", "") or "")): item
            for item in pair.get("directions", [])
            if isinstance(item, Mapping)
        }
        for source, target, key, score_key, contribution_key in (
            (endpoint_a, endpoint_b, "a_to_b_logit", "a_to_b_score", "a_to_b_contributions"),
            (endpoint_b, endpoint_a, "b_to_a_logit", "b_to_a_score", "b_to_a_contributions"),
        ):
            logit = details.get(key)
            if logit is None:
                missing_details += 1
                continue
            direction = by_endpoints.get((source, target), {})
            contributions = [
                item
                for item in details.get(contribution_key, []) or []
                if isinstance(item, Mapping)
            ]
            counter_ids = {
                str(evidence_id)
                for item in contributions
                if float(item.get("log_contribution", 0.0) or 0.0) < 0.0
                for evidence_id in item.get("evidence_ids", []) or []
            }
            candidate = _Direction(
                hypothesis_id=hypothesis_id,
                source=source,
                target=target,
                edge_type=edge_type,
                lift=round(float(logit) - prior_logit, 9),
                probability=float(details.get(score_key, 0.0) or 0.0),
                relation=str(direction.get("relation", "inferred_impact")),
                case_support_score=float(direction.get("case_support_score", 0.0) or 0.0),
                lag_interval_ms=direction.get("lag_interval_ms"),
                features=dict(direction.get("features", {}) or {}),
                evidence_ids=_as_str_tuple(direction.get("evidence_ids")),
                counter_evidence_ids=_as_str_tuple(
                    [*(direction.get("counter_evidence_ids") or []), *sorted(counter_ids)]
                ),
                topology_edge_ids=tuple(validated),
            )
            current = selected.get((source, target))
            if (
                current is None
                or candidate.lift > current.lift
                or (
                    candidate.lift == current.lift
                    and candidate.hypothesis_id < current.hypothesis_id
                )
            ):
                selected[(source, target)] = candidate

    if not selected and missing_details:
        raise ValueError(
            "maximum_evidence_arborescence_v1 needs additive directional evidence; "
            "no edge hypothesis carried logit details"
        )
    return selected


def _reaches(adjacency: Mapping[str, Set[str]], source: str, target: str) -> bool:
    """Is ``target`` reachable from ``source`` along the current directed graph?"""

    if source == target:
        return True
    seen = {source}
    stack = [source]
    while stack:
        for neighbour in adjacency.get(stack.pop(), ()):
            if neighbour == target:
                return True
            if neighbour not in seen:
                seen.add(neighbour)
                stack.append(neighbour)
    return False


def _reachable_set(adjacency: Mapping[str, Set[str]], source: str) -> Set[str]:
    seen = {source}
    stack = [source]
    while stack:
        for neighbour in adjacency.get(stack.pop(), ()):
            if neighbour not in seen:
                seen.add(neighbour)
                stack.append(neighbour)
    return seen


def _support_level(probability: float, config: PropagationConfig) -> str:
    if probability >= config.strong_edge_support:
        return "strong"
    if probability >= config.moderate_edge_support:
        return "moderate"
    return "weak"


def _episode_index(
    episodes: Sequence[Mapping[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in episodes:
        if isinstance(item, Mapping) and item.get("device_id"):
            result[str(item["device_id"])].append(dict(item))
    return result


def _node_row(
    device_id: str,
    role: str,
    episode_by_device: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Dict[str, Any]:
    episodes = list(episode_by_device.get(device_id, []))
    intervals = [
        item.get("onset_interval_ms")
        for item in episodes
        if isinstance(item.get("onset_interval_ms"), list)
        and len(item.get("onset_interval_ms")) == 2
        and item.get("lifecycle") != "clear"
    ]
    relevance = max(
        (float(item.get("incident_relevance", 0.0) or 0.0) for item in episodes),
        default=0.0,
    )
    return {
        "device_id": device_id,
        "role": role,
        "onset_interval_ms": list(min(intervals, key=lambda value: (value[0], value[1])))
        if intervals
        else None,
        "support_level": (
            "strong" if relevance >= 0.8 else "moderate" if relevance >= 0.55 else "weak"
        ),
        "evidence_ids": sorted(
            {str(item.get("evidence_id")) for item in episodes if item.get("evidence_id")}
        ),
    }


def _edge_row(
    direction: _Direction,
    *,
    edge_id: str,
    origin: str,
    root_distance_consistency: float,
    config: PropagationConfig,
) -> Dict[str, Any]:
    """Emit one selected relation, carrying the evidence that selected it.

    ``support_score`` is the direction's own probability, never the reweighted
    value the arborescence used internally. ``features.evidence_lift`` records
    the quantity that actually drove the structural decision.
    """

    return {
        "edge_id": edge_id,
        "edge_hypothesis_id": direction.hypothesis_id,
        "from": direction.source,
        "to": direction.target,
        "edge_type": direction.edge_type,
        "edge_origin": origin,
        "relation": direction.relation,
        "direction_status": "likely",
        "lag_interval_ms": direction.lag_interval_ms,
        "case_support_score": round(direction.case_support_score, 6),
        "state_probability": round(direction.probability, 6),
        "support_score": round(direction.probability, 6),
        "support_level": _support_level(direction.probability, config),
        "features": {
            **dict(direction.features),
            "topology_valid": 1.0,
            "evidence_lift": round(direction.lift, 9),
            "root_distance_consistency": root_distance_consistency,
            "contradiction": 0.0,
        },
        "topology_edge_ids": list(direction.topology_edge_ids),
        "topology_validation": "raw_edge_match",
        "evidence_ids": list(direction.evidence_ids),
        "counter_evidence_ids": list(direction.counter_evidence_ids),
        "alternative_group": None,
    }


def _ranked_chains(
    edges: Sequence[Mapping[str, Any]],
    anchor: str,
    targets: Sequence[str],
) -> List[Dict[str, Any]]:
    adjacency: Dict[str, List[str]] = defaultdict(list)
    for edge in edges:
        adjacency[str(edge["from"])].append(str(edge["to"]))
    for values in adjacency.values():
        values.sort()

    predecessor: Dict[str, str] = {}
    seen = {anchor}
    queue = deque([anchor])
    while queue:
        node = queue.popleft()
        for neighbour in adjacency.get(node, []):
            if neighbour not in seen:
                seen.add(neighbour)
                predecessor[neighbour] = node
                queue.append(neighbour)

    score_by_pair = {(str(edge["from"]), str(edge["to"])): float(edge["support_score"]) for edge in edges}
    chains: List[Dict[str, Any]] = []
    for target in targets:
        if target not in seen or target == anchor:
            continue
        devices = [target]
        while devices[-1] != anchor:
            devices.append(predecessor[devices[-1]])
        devices.reverse()
        scores = [
            score_by_pair.get((devices[index], devices[index + 1]), 0.0)
            for index in range(len(devices) - 1)
        ]
        chains.append(
            {
                "target": target,
                "devices": devices,
                "score": round(sum(scores) / len(scores), 6) if scores else 0.0,
                "covered_targets": [target],
            }
        )
    chains.sort(key=lambda item: (-float(item["score"]), item["target"]))
    return chains


def decode_backbone(
    hypothesis_graph: Mapping[str, Any],
    root_hypothesis: Mapping[str, Any],
    episodes: Sequence[Mapping[str, Any]],
    *,
    config: PropagationConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Reconstruct one anchor-conditioned propagation graph from M1 relations."""

    cfg = normalize_config(config)
    if cfg.edge_probability_method != "logit_evidence_v1":
        raise ValueError(
            "maximum_evidence_arborescence_v1 maximises a sum of directional "
            "evidence, which only logit_evidence_v1 makes additive; set "
            f"edge_probability_method='logit_evidence_v1' (got "
            f"{cfg.edge_probability_method!r})"
        )

    anchors = root_devices(root_hypothesis)
    if not anchors:
        raise ValueError("root_hypothesis names no anchor device")
    anchor = anchors[0]

    node_ids = sorted(
        {
            str(item.get("device_id"))
            for item in hypothesis_graph.get("nodes", [])
            if isinstance(item, Mapping) and item.get("device_id")
        }
        | {anchor}
    )
    directions = _directions(hypothesis_graph, cfg)

    # --- backbone: global structural selection ---------------------------
    backbone_candidates = [
        WeightedEdge(direction.source, direction.target, direction.lift)
        for direction in directions.values()
        if direction.lift > cfg.backbone_null_weight
    ]
    forest = maximum_arborescence_with_null_option(
        node_ids,
        backbone_candidates,
        anchor,
        null_weight=cfg.backbone_null_weight,
    )
    backbone_pairs = {(edge.source, edge.target) for edge in forest.edges}

    adjacency: Dict[str, Set[str]] = defaultdict(set)
    for edge in forest.edges:
        adjacency[edge.source].add(edge.target)

    # --- augmentation: recover the extra direct relations -----------------
    augmented_pairs: Set[Tuple[str, str]] = set()
    if cfg.dag_augmentation:
        candidates = sorted(
            (
                direction
                for key, direction in directions.items()
                if key not in backbone_pairs
            ),
            key=lambda direction: (-direction.lift, direction.source, direction.target),
        )
        # Augmentation grows outward in rounds: accepting a->b makes b
        # reachable, which can qualify an edge out of b that a single descending
        # pass would already have rejected. Iterate to a fixed point so the
        # result does not depend on where a candidate happens to sit in the
        # ordering relative to the edge that would have reached its source.
        added = True
        while added:
            added = False
            for direction in candidates:
                if (direction.source, direction.target) in augmented_pairs:
                    continue
                if direction.probability < cfg.augmentation_min_probability:
                    continue
                if direction.source not in _reachable_set(adjacency, anchor):
                    continue
                if _reaches(adjacency, direction.target, direction.source):
                    continue
                adjacency[direction.source].add(direction.target)
                augmented_pairs.add((direction.source, direction.target))
                added = True

    reached = _reachable_set(adjacency, anchor)

    # --- emit ------------------------------------------------------------
    distance: Dict[str, int] = {anchor: 0}
    queue = deque([anchor])
    while queue:
        node = queue.popleft()
        for neighbour in sorted(adjacency.get(node, ())):
            if neighbour not in distance:
                distance[neighbour] = distance[node] + 1
                queue.append(neighbour)

    selected: List[Tuple[str, _Direction]] = []
    for source, target in sorted(backbone_pairs | augmented_pairs):
        direction = directions.get((source, target))
        if direction is None:
            continue
        selected.append(
            (
                _BACKBONE_ORIGIN if (source, target) in backbone_pairs else _AUGMENTED_ORIGIN,
                direction,
            )
        )

    edge_rows = [
        _edge_row(
            direction,
            edge_id=f"P{index}",
            origin=origin,
            root_distance_consistency=(
                1.0
                if distance.get(direction.target, 0) > distance.get(direction.source, 0)
                else 0.0
            ),
            config=cfg,
        )
        for index, (origin, direction) in enumerate(selected, 1)
    ]

    target_ids = [
        str(item.get("device_id"))
        for item in hypothesis_graph.get("affected_targets", [])
        if isinstance(item, Mapping) and item.get("device_id")
    ]
    target_set = {device for device in target_ids if device}
    covered = sorted(target_set & reached)

    root_scope = str(root_hypothesis.get("root_scope", "device"))
    episode_by_device = _episode_index(episodes)
    node_rows = [
        _node_row(
            device,
            "root_endpoint"
            if device == anchor and root_scope == "inter_device_link"
            else "root"
            if device == anchor
            else "affected"
            if device in target_set
            else "propagation",
            episode_by_device,
        )
        for device in sorted(reached)
    ]

    scores = [float(edge["support_score"]) for edge in edge_rows]
    graph_score = sum(scores) / len(scores) if scores else 0.0
    supported = sum(
        1 for edge in edge_rows if edge["support_level"] in {"moderate", "strong"}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "root_hypothesis": dict(root_hypothesis),
        "nodes": node_rows,
        "edges": edge_rows,
        "covered_targets": covered,
        "target_coverage": round(len(covered) / len(target_set), 6) if target_set else 0.0,
        "graph_score": round(graph_score, 6),
        "hypothesis_score": round(graph_score, 6),
        "ranked_chains": _ranked_chains(edge_rows, anchor, covered),
        "alternative_hypotheses": [],
        "diagnostics": {
            "anchor_device": anchor,
            "anchor_candidates": anchors,
            "backbone_method": "maximum_evidence_arborescence_v1",
            "target_count": len(target_set),
            "selected_edge_count": len(edge_rows),
            "backbone_edge_count": len(backbone_pairs),
            "augmented_edge_count": len(augmented_pairs),
            "cycle_contraction_count": forest.contraction_count,
            "backbone_objective": round(forest.objective, 9),
            "backbone_arborescence_weight": round(forest.arborescence_weight, 9),
            # Backbone-only view, kept because augmentation may later reach
            # some of these devices.
            "backbone_unreached_nodes": list(forest.unreached),
            "unreached_nodes": sorted(set(node_ids) - reached),
            "uncovered_targets": sorted(target_set - reached),
            "supported_edge_ratio": round(supported / len(edge_rows), 6) if edge_rows else 0.0,
            "grounded_edge_ratio": (
                sum(1 for edge in edge_rows if edge["evidence_ids"]) / len(edge_rows)
                if edge_rows
                else 0.0
            ),
            "weak_edge_ratio": (
                sum(1 for edge in edge_rows if edge["support_level"] == "weak")
                / len(edge_rows)
                if edge_rows
                else 0.0
            ),
            "contradiction_score": 0.0,
            "root_distance_consistency": (
                sum(
                    float(edge["features"]["root_distance_consistency"])
                    for edge in edge_rows
                )
                / len(edge_rows)
                if edge_rows
                else 0.0
            ),
        },
    }
