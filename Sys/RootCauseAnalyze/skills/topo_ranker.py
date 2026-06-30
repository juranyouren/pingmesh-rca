from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from Sys.RootCauseAnalyze.trust_trees.topo_tree import assess_topo_tree
from Sys.utils.alarm_utils import load_alarm_weights, node_alarm_weight, node_events, event_name
from Sys.utils.case_utils import get_device_ip
from Sys.utils.ranking_utils import sorted_score_items

try:
    import networkx as nx
except ImportError:  # pragma: no cover - optional dependency on servers only
    nx = None

try:
    from Sys.config import config as _cfg

    _DEFAULT_PAGERANK_ALPHA = _cfg.pagerank.alpha
except Exception:
    _DEFAULT_PAGERANK_ALPHA = 0.85


SKILL_META = {
    "skill_id": "1",
    "skill_name": "topology_pagerank_rank",
    "python_executor": "score_topo",
    "target_error": "Topology/PageRank ranking with alarm weights, cross count, and endpoint proximity.",
}


def parse_endpoint_ips(info: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    source_ips, sink_ips = [], []
    if not isinstance(info, dict):
        return source_ips, sink_ips
    try:
        src_val = info.get("source_ip", "[]")
        snk_val = info.get("sink_ip", "[]")
        source_ips = json.loads(src_val) if isinstance(src_val, str) else src_val
        sink_ips = json.loads(snk_val) if isinstance(snk_val, str) else snk_val
    except Exception:
        source_ips, sink_ips = [], []
    return (
        source_ips if isinstance(source_ips, list) else [],
        sink_ips if isinstance(sink_ips, list) else [],
    )


def source_sink_related(ip: str, node: Dict[str, Any], source_ips: List[str], sink_ips: List[str]) -> bool:
    endpoints = set(source_ips + sink_ips)
    if ip in endpoints:
        return True
    neighbors = set(node.get("linked_to", []) + node.get("linked_from", []))
    return bool(neighbors & endpoints)


def seed_type(node: Dict[str, Any], max_weight: int, related: bool) -> str:
    if max_weight > 0:
        return "alarm_weight"
    if node.get("alarms"):
        return "alarm_count"
    if node.get("logs"):
        return "log"
    if related:
        return "endpoint"
    return "baseline"


def score_topo(
    node_list: List[Dict[str, Any]],
    info: Dict[str, Any],
    *,
    weight_path: str | None = None,
    directed: bool = True,
) -> Dict[str, float]:
    if nx is None:
        return {}

    weights = load_alarm_weights(weight_path)
    source_ips, sink_ips = parse_endpoint_ips(info)
    ip_set = set()
    node_by_ip: Dict[str, Dict[str, Any]] = {}
    personalization: Dict[str, float] = {}

    for node in node_list:
        ip = get_device_ip(node)
        if not ip or ip == "unknown":
            continue
        ip_set.add(ip)
        node_by_ip[ip] = node
        try:
            cross_count = int(node.get("cross", 0))
        except Exception:
            cross_count = 0

        max_weight = 0
        for evt in node_events(node):
            name = event_name(evt)
            weight = weights.get(str(name).lower(), 0) if name else 0
            max_weight = max(max_weight, weight)

        entity_score = 0.0
        if max_weight > 0:
            entity_score += float(max_weight)
        elif node.get("alarms"):
            entity_score += len(node["alarms"]) * 2.0
        elif node.get("logs"):
            entity_score += 0.5
        if entity_score > 0 and cross_count > 0:
            entity_score += entity_score * cross_count * 0.5

        personalization[ip] = 0.1 + entity_score + (0.5 if ip in source_ips or ip in sink_ips else 0.0)

    if not ip_set:
        return {}

    graph = nx.DiGraph() if directed else nx.Graph()
    for ip, node in node_by_ip.items():
        graph.add_node(ip)
        if directed:
            for upstream in node.get("linked_from", []):
                if upstream in ip_set:
                    graph.add_edge(ip, upstream)
            for downstream in node.get("linked_to", []):
                if downstream in ip_set:
                    graph.add_edge(downstream, ip)
        else:
            for neighbor in node.get("linked_to", []) + node.get("linked_from", []):
                graph.add_edge(ip, neighbor)

    for node_id in graph.nodes:
        personalization.setdefault(node_id, 0.1)

    try:
        raw_scores = nx.pagerank(graph, alpha=_DEFAULT_PAGERANK_ALPHA, personalization=personalization)
    except Exception:
        return {}
    if not raw_scores:
        return {}
    max_score = max(raw_scores.values())
    return {ip: score / max_score for ip, score in raw_scores.items()} if max_score > 0 else {}


def topo_details(
    node_list: List[Dict[str, Any]],
    info: Dict[str, Any],
    scores: Dict[str, float],
    *,
    weight_path: str | None,
    directed: bool,
    top_k: int,
) -> Dict[str, Any]:
    weights = load_alarm_weights(weight_path)
    source_ips, sink_ips = parse_endpoint_ips(info)
    node_by_ip = {get_device_ip(node): node for node in node_list if get_device_ip(node) != "unknown"}

    fallback_scores = {}
    for ip, node in node_by_ip.items():
        max_weight, _hit_names = node_alarm_weight(node, weights)
        related = source_sink_related(ip, node, source_ips, sink_ips)
        try:
            cross = float(node.get("cross", 0) or 0)
        except (TypeError, ValueError):
            cross = 0.0
        fallback_scores[ip] = (
            max_weight
            + cross
            + len(node.get("alarms", [])) * 2.0
            + len(node.get("logs", [])) * 0.5
            + (0.5 if related else 0.0)
        )

    ranking_scores = scores or fallback_scores
    directed_scores = scores if directed else score_topo(node_list, info, weight_path=weight_path, directed=True)
    undirected_scores = score_topo(node_list, info, weight_path=weight_path, directed=False) if scores else {}
    directed_top3 = [ip for ip, _ in sorted_score_items(directed_scores or {}, 3)]
    undirected_top3 = [ip for ip, _ in sorted_score_items(undirected_scores or {}, 3)]

    rankings = []
    for rank, (ip, score) in enumerate(sorted_score_items(ranking_scores or {}, top_k), 1):
        node = node_by_ip.get(ip, {})
        max_weight, hit_names = node_alarm_weight(node, weights)
        related = source_sink_related(ip, node, source_ips, sink_ips)
        rankings.append(
            {
                "rank": rank,
                "ip": ip,
                "pr_score": round(score, 6),
                "cross": node.get("cross", 0),
                "max_alarm_weight": max_weight,
                "high_weight_alarm_hit": max_weight > 0,
                "high_weight_alarms": hit_names[:10],
                "source_sink_related": related,
                "seed_type": seed_type(node, max_weight, related),
            }
        )

    block = {
        "num_devices_scored": len(scores or {}),
        "top3": rankings[:3],
        "topk": rankings,
        "rankings": rankings,
        "diagnostics": {
            "pagerank_available": bool(scores),
            "directed_top3": directed_top3,
            "undirected_top3": undirected_top3,
        },
    }
    block["trust_tree"] = assess_topo_tree(block)
    return block
