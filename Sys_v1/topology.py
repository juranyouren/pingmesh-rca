from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from Sys.utils.case_utils import get_device_ip


def _as_ip_list(value: Any) -> List[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            value = [value]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def endpoint_ips(info: Mapping[str, Any]) -> List[str]:
    values = [
        *_as_ip_list(info.get("source_ip")),
        *_as_ip_list(info.get("sink_ip")),
        *_as_ip_list(info.get("src_tunnel_ip")),
        *_as_ip_list(info.get("dst_tunnel_ip")),
    ]
    return list(dict.fromkeys(values))


def _node_map(node_list: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        ip: node
        for node in node_list
        if (ip := get_device_ip(node)) and ip != "unknown"
    }


def _adjacency(
    nodes: Mapping[str, Dict[str, Any]],
    *,
    directed: bool,
) -> Dict[str, set[str]]:
    graph = {ip: set() for ip in nodes}
    for ip, node in nodes.items():
        upstream = [value for value in node.get("linked_from", []) if value in nodes]
        downstream = [value for value in node.get("linked_to", []) if value in nodes]
        if directed:
            # Match the historical root-facing PageRank direction without using
            # its alarm/log personalization.
            graph[ip].update(upstream)
            for child in downstream:
                graph[child].add(ip)
        else:
            for neighbor in [*upstream, *downstream]:
                graph[ip].add(neighbor)
                graph[neighbor].add(ip)
    return graph


def _personalization(
    nodes: Mapping[str, Dict[str, Any]],
    endpoints: Iterable[str],
    *,
    endpoint_bonus: float,
    cross_weight: float,
) -> Dict[str, float]:
    endpoint_set = set(endpoints)
    raw: Dict[str, float] = {}
    for ip, node in nodes.items():
        neighbors = set(node.get("linked_from", [])) | set(node.get("linked_to", []))
        try:
            cross = max(0.0, float(node.get("cross", 0) or 0))
        except (TypeError, ValueError):
            cross = 0.0
        related = ip in endpoint_set or bool(neighbors & endpoint_set)
        raw[ip] = 1.0 + cross_weight * cross + (endpoint_bonus if related else 0.0)
    total = sum(raw.values())
    if total <= 0:
        uniform = 1.0 / max(len(raw), 1)
        return {ip: uniform for ip in raw}
    return {ip: value / total for ip, value in raw.items()}


def _pagerank(
    graph: Mapping[str, set[str]],
    personalization: Mapping[str, float],
    *,
    alpha: float,
    max_iter: int,
    tolerance: float,
) -> Dict[str, float]:
    if not graph:
        return {}
    nodes = sorted(graph)
    rank = {ip: 1.0 / len(nodes) for ip in nodes}
    incoming = {ip: set() for ip in nodes}
    for source, targets in graph.items():
        for target in targets:
            if target in incoming:
                incoming[target].add(source)

    for _iteration in range(max_iter):
        dangling = sum(rank[ip] for ip in nodes if not graph[ip])
        updated: Dict[str, float] = {}
        for ip in nodes:
            link_mass = sum(rank[source] / len(graph[source]) for source in incoming[ip])
            updated[ip] = (
                (1.0 - alpha) * personalization[ip]
                + alpha * link_mass
                + alpha * dangling * personalization[ip]
            )
        delta = sum(abs(updated[ip] - rank[ip]) for ip in nodes)
        rank = updated
        if delta < tolerance:
            break
    return rank


def score_topology(
    node_list: Sequence[Dict[str, Any]],
    info: Mapping[str, Any],
    *,
    directed: bool = True,
    alpha: float = 0.85,
    endpoint_bonus: float = 1.0,
    cross_weight: float = 0.5,
    max_iter: int = 100,
    tolerance: float = 1e-10,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Return a topology-only score and auditable diagnostics.

    No alarm count, alarm weight, log count, event timestamp, semantic model,
    or ground-truth label is read here.
    """

    nodes = _node_map(node_list)
    if not nodes:
        return {}, {"available": False, "reason": "no_devices"}
    endpoints = endpoint_ips(info)
    graph = _adjacency(nodes, directed=directed)
    personalization = _personalization(
        nodes,
        endpoints,
        endpoint_bonus=endpoint_bonus,
        cross_weight=cross_weight,
    )
    raw_scores = _pagerank(
        graph,
        personalization,
        alpha=alpha,
        max_iter=max_iter,
        tolerance=tolerance,
    )
    max_score = max(raw_scores.values(), default=0.0)
    scores = {
        ip: (value / max_score if max_score > 0 else 0.0)
        for ip, value in raw_scores.items()
    }
    diagnostics = {
        "available": bool(scores),
        "algorithm": "pure_topology_personalized_pagerank_v1",
        "directed": directed,
        "device_count": len(nodes),
        "edge_count": sum(len(targets) for targets in graph.values()),
        "endpoint_ips": endpoints,
        "uses_alarm_or_log_evidence": False,
        "uses_ground_truth": False,
    }
    return scores, diagnostics


def ranked_score_rows(
    scores: Mapping[str, float],
    *,
    limit: int | None = None,
    score_key: str = "score",
) -> List[Dict[str, Any]]:
    items = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    if limit is not None:
        items = items[:limit]
    return [
        {"rank": index, "ip": ip, score_key: round(float(score), 6)}
        for index, (ip, score) in enumerate(items, 1)
    ]
