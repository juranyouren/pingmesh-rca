from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig, normalize_config
from Sys.RootCauseAnalyze.propagation.topology_context import physical_adjacency, topology_edges_between
from Sys.utils.case_utils import get_device_ip


def shortest_distances(
    adjacency: Mapping[str, Set[str]],
    seeds: Iterable[str],
    *,
    max_depth: int | None = None,
) -> Dict[str, int]:
    distance: Dict[str, int] = {}
    queue = deque()
    for seed in sorted(set(seeds)):
        if seed in adjacency and seed not in distance:
            distance[seed] = 0
            queue.append(seed)
    while queue:
        node = queue.popleft()
        if max_depth is not None and distance[node] >= max_depth:
            continue
        for neighbor in sorted(adjacency.get(node, set())):
            if neighbor in distance:
                continue
            distance[neighbor] = distance[node] + 1
            queue.append(neighbor)
    return distance


def shortest_path(
    adjacency: Mapping[str, Set[str]],
    source: str,
    target: str,
) -> List[str]:
    if source not in adjacency or target not in adjacency:
        return []
    if source == target:
        return [source]
    parent: Dict[str, str | None] = {source: None}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        for neighbor in sorted(adjacency.get(node, set())):
            if neighbor in parent:
                continue
            parent[neighbor] = node
            if neighbor == target:
                path = [target]
                while parent[path[-1]] is not None:
                    path.append(str(parent[path[-1]]))
                return list(reversed(path))
            queue.append(neighbor)
    return []


def _corridor_nodes(
    adjacency: Mapping[str, Set[str]],
    source_anchors: Sequence[str],
    sink_anchors: Sequence[str],
    slack: int,
) -> Tuple[Set[str], Dict[str, int], Dict[str, int], int | None]:
    source_distance = shortest_distances(adjacency, source_anchors)
    sink_distance = shortest_distances(adjacency, sink_anchors)
    shortest = min(
        (source_distance[sink] for sink in sink_anchors if sink in source_distance),
        default=None,
    )
    if shortest is None:
        return set(), source_distance, sink_distance, None
    corridor = {
        node
        for node in adjacency
        if node in source_distance
        and node in sink_distance
        and source_distance[node] + sink_distance[node] <= shortest + max(0, slack)
    }
    return corridor, source_distance, sink_distance, shortest


def _episode_index(episodes: Sequence[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for episode in episodes:
        device_id = str(episode.get("device_id", "") or "")
        if device_id:
            result[device_id].append(dict(episode))
    for values in result.values():
        values.sort(key=lambda item: str(item.get("evidence_id", "")))
    return result


def _select_targets(
    episode_by_device: Mapping[str, Sequence[Mapping[str, Any]]],
    endpoint_anchors: Sequence[str],
    config: PropagationConfig,
) -> List[Dict[str, Any]]:
    target_scores: Dict[str, Dict[str, Any]] = {}
    for device_id in sorted(set(endpoint_anchors)):
        target_scores[device_id] = {
            "device_id": device_id,
            "target_type": "pingmesh_endpoint_anchor",
            "target_prize": 1.0,
            "evidence_ids": [],
        }
    for device_id, device_episodes in episode_by_device.items():
        relevant = [
            episode
            for episode in device_episodes
            if float(episode.get("incident_relevance", 0.0) or 0.0) >= 0.45
            and episode.get("lifecycle") != "clear"
        ]
        if not relevant:
            continue
        prize = max(float(item.get("incident_relevance", 0.0) or 0.0) for item in relevant)
        existing = target_scores.get(device_id)
        evidence_ids = sorted(
            {str(item.get("evidence_id")) for item in relevant if item.get("evidence_id")}
        )
        if existing:
            existing["target_type"] = "endpoint_and_event"
            existing["target_prize"] = round(max(existing["target_prize"], prize), 6)
            existing["evidence_ids"] = evidence_ids
        else:
            target_scores[device_id] = {
                "device_id": device_id,
                "target_type": "incident_event",
                "target_prize": round(prize, 6),
                "evidence_ids": evidence_ids,
            }
    return sorted(
        target_scores.values(),
        key=lambda item: (-float(item["target_prize"]), item["device_id"]),
    )[: config.max_targets]


def build_candidate_graph(
    node_list: Sequence[Mapping[str, Any]],
    info: Mapping[str, Any],
    topology_context: Mapping[str, Any],
    episodes: Sequence[Mapping[str, Any]],
    *,
    config: PropagationConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    cfg = normalize_config(config)
    adjacency = physical_adjacency(topology_context)
    node_by_id = {
        get_device_ip(dict(node)): dict(node)
        for node in node_list
        if get_device_ip(dict(node)) not in ("", "unknown")
    }
    context_nodes = {
        str(node.get("device_id")): dict(node)
        for node in topology_context.get("nodes", [])
        if isinstance(node, Mapping) and node.get("device_id")
    }
    for device_id in node_by_id:
        adjacency.setdefault(device_id, set())

    episode_by_device = _episode_index(episodes)
    source_anchors = [
        str(value) for value in topology_context.get("source_anchors", []) if value in adjacency
    ]
    sink_anchors = [
        str(value) for value in topology_context.get("sink_anchors", []) if value in adjacency
    ]
    endpoint_anchors = sorted(set(source_anchors + sink_anchors))
    corridor, source_distance, sink_distance, endpoint_shortest = _corridor_nodes(
        adjacency,
        source_anchors,
        sink_anchors,
        cfg.corridor_slack_hops,
    )
    targets = _select_targets(episode_by_device, endpoint_anchors, cfg)
    target_set = {item["device_id"] for item in targets}
    relevant_event_devices = {
        device_id
        for device_id, values in episode_by_device.items()
        if any(float(item.get("incident_relevance", 0.0) or 0.0) >= 0.45 for item in values)
    }
    incident_seeds = set(endpoint_anchors) | target_set | relevant_event_devices
    incident_distance = shortest_distances(adjacency, incident_seeds)
    incident_neighborhood = {
        node
        for node, distance in incident_distance.items()
        if distance <= cfg.incident_neighborhood_hops
    }

    # Connect the observed incident terminals without consulting any root
    # candidate. This keeps M1 invariant to Stage 1 rankings.
    connector_nodes: Set[str] = set()
    terminals = sorted(incident_seeds)
    if terminals:
        anchor = terminals[0]
        for terminal in terminals[1:]:
            connector_nodes.update(shortest_path(adjacency, anchor, terminal))

    proposed = (
        corridor
        | incident_neighborhood
        | relevant_event_devices
        | set(endpoint_anchors)
        | target_set
        | connector_nodes
    )
    proposed &= set(adjacency)

    def node_priority(device_id: str) -> Tuple[float, str]:
        priority = 0.0
        if device_id in target_set:
            priority += 90.0
        if device_id in endpoint_anchors:
            priority += 80.0
        if device_id in relevant_event_devices:
            priority += 60.0 + max(
                (float(item.get("incident_relevance", 0.0) or 0.0) for item in episode_by_device[device_id]),
                default=0.0,
            )
        if device_id in connector_nodes:
            priority += 50.0
        if device_id in corridor:
            priority += 40.0
        if device_id in incident_neighborhood:
            priority += 30.0 - float(
                incident_distance.get(device_id, cfg.incident_neighborhood_hops)
            )
        return -priority, device_id

    required = target_set | set(endpoint_anchors) | connector_nodes
    effective_cap = max(cfg.max_candidate_nodes, len(required))
    selected = set(sorted(proposed, key=node_priority)[:effective_cap]) | required

    node_rows = []
    for device_id in sorted(selected):
        events = episode_by_device.get(device_id, [])
        node = node_by_id.get(device_id, {})
        context_node = context_nodes.get(device_id, {})
        node_rows.append(
            {
                "device_id": device_id,
                "role": str(node.get("role", context_node.get("role", "")) or ""),
                "in_corridor": device_id in corridor,
                "source_distance": source_distance.get(device_id),
                "sink_distance": sink_distance.get(device_id),
                "is_target": device_id in target_set,
                "evidence_ids": sorted(
                    {str(item.get("evidence_id")) for item in events if item.get("evidence_id")}
                ),
            }
        )

    edge_rows: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for a in sorted(selected):
        for b in sorted(adjacency.get(a, set())):
            if b not in selected or a >= b:
                continue
            source_edges = topology_edges_between(topology_context, a, b)
            edge_rows[(a, b, "physical")] = {
                "endpoint_a": a,
                "endpoint_b": b,
                "edge_type": "physical",
                "topology_edge_ids": [str(item.get("edge_id")) for item in source_edges],
                "group_ids": sorted(
                    {
                        str(group_id)
                        for item in source_edges
                        for group_id in item.get("group_ids", [])
                    }
                ),
                "ports": [
                    {
                        "endpoint_a_port": item.get("endpoint_a_port", ""),
                        "endpoint_b_port": item.get("endpoint_b_port", ""),
                    }
                    for item in source_edges
                ],
                "in_corridor": a in corridor and b in corridor,
                "direct_relation_evidence_ids": [],
            }

    for episode in episodes:
        a = str(episode.get("device_id", "") or "")
        b = str(episode.get("peer_device", "") or "")
        if not a or not b or a == b or a not in selected or b not in selected:
            continue
        pair = tuple(sorted((a, b)))
        row = edge_rows.get((pair[0], pair[1], "physical"))
        if row is None:
            # M1 evaluates propagation states only between physically adjacent
            # devices. A textual peer mention cannot create a topology edge.
            continue
        evidence_id = episode.get("evidence_id")
        if evidence_id and evidence_id not in row["direct_relation_evidence_ids"]:
            row["direct_relation_evidence_ids"].append(evidence_id)

    return {
        "nodes": node_rows,
        "edges": [edge_rows[key] for key in sorted(edge_rows)],
        "targets": targets,
        "source_anchors": source_anchors,
        "sink_anchors": sink_anchors,
        "corridor_nodes": sorted(corridor & selected),
        "diagnostics": {
            "topology_context_source": topology_context.get("diagnostics", {}).get("source", "unknown"),
            "full_device_count": len(adjacency),
            "proposed_device_count": len(proposed),
            "candidate_device_count": len(selected),
            "candidate_edge_count": len(edge_rows),
            "dropped_candidate_devices": max(0, len(proposed) - len(selected)),
            "endpoint_shortest_hops": endpoint_shortest,
            "source_anchor_count": len(source_anchors),
            "sink_anchor_count": len(sink_anchors),
            "target_count": len(targets),
            "connector_node_count": len(connector_nodes),
            "root_independent": True,
        },
    }
