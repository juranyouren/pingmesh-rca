from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from Sys_v1.RootCauseAnalyze.trust_trees.topo_tree import assess_topo_tree
from Sys_v1.utils.case_utils import get_device_ip
from Sys_v1.utils.ranking_utils import sorted_score_items

try:
    import networkx as nx
except ImportError:  # pragma: no cover - optional dependency on servers only
    nx = None

try:
    from Sys_v1.config import config as _cfg

    _DEFAULT_PAGERANK_ALPHA = _cfg.pagerank.alpha
except Exception:
    _DEFAULT_PAGERANK_ALPHA = 0.85


SKILL_META = {
    "skill_id": "1",
    "skill_name": "topology_pagerank_rank",
    "python_executor": "score_topo",
    "target_error": "Topology-only PageRank ranking using graph structure, path crossing, and endpoint proximity.",
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


def source_sink_related(
    ip: str,
    node: Dict[str, Any],
    source_ips: List[str],
    sink_ips: List[str],
) -> bool:
    endpoints = set(source_ips + sink_ips)
    if ip in endpoints:
        return True
    neighbors = set((node.get("linked_to", []) or []) + (node.get("linked_from", []) or []))
    return bool(neighbors & endpoints)


def _cross_count(node: Dict[str, Any]) -> float:
    try:
        return max(0.0, float(node.get("cross", 0) or 0))
    except (TypeError, ValueError):
        return 0.0


def _topology_seed(node: Dict[str, Any], related: bool) -> Tuple[float, str]:
    """Build an M1 seed without consulting alarms, logs, or their weights."""
    cross = _cross_count(node)
    score = 0.1 + cross + (0.5 if related else 0.0)
    if cross > 0:
        seed_type = "path_crossing"
    elif related:
        seed_type = "endpoint_proximity"
    else:
        seed_type = "baseline"
    return score, seed_type


def score_topo(
    node_list: List[Dict[str, Any]],
    info: Dict[str, Any],
    *,
    weight_path: str | None = None,
    directed: bool = True,
) -> Dict[str, float]:
    """Score devices from topology information only.

    ``weight_path`` remains in the signature for compatibility with ``Sys``;
    it is intentionally ignored so M1 cannot leak M2 alarm evidence.
    """
    del weight_path
    if nx is None:
        return {}

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
        related = source_sink_related(ip, node, source_ips, sink_ips)
        personalization[ip] = _topology_seed(node, related)[0]

    if not ip_set:
        return {}

    graph = nx.DiGraph() if directed else nx.Graph()
    graph.add_nodes_from(ip_set)
    for ip, node in node_by_ip.items():
        if directed:
            for upstream in node.get("linked_from", []) or []:
                if upstream in ip_set:
                    graph.add_edge(ip, upstream)
            for downstream in node.get("linked_to", []) or []:
                if downstream in ip_set:
                    graph.add_edge(downstream, ip)
        else:
            for neighbor in (node.get("linked_to", []) or []) + (node.get("linked_from", []) or []):
                if neighbor in ip_set:
                    graph.add_edge(ip, neighbor)

    try:
        raw_scores = nx.pagerank(
            graph,
            alpha=_DEFAULT_PAGERANK_ALPHA,
            personalization=personalization,
        )
    except Exception:
        return {}
    if not raw_scores:
        return {}
    max_score = max(raw_scores.values())
    return (
        {ip: score / max_score for ip, score in raw_scores.items()}
        if max_score > 0
        else {}
    )


def topo_details(
    node_list: List[Dict[str, Any]],
    info: Dict[str, Any],
    scores: Dict[str, float],
    *,
    weight_path: str | None,
    directed: bool,
    top_k: int,
) -> Dict[str, Any]:
    del weight_path
    source_ips, sink_ips = parse_endpoint_ips(info)
    node_by_ip = {
        get_device_ip(node): node
        for node in node_list
        if get_device_ip(node) != "unknown"
    }

    fallback_scores = {}
    for ip, node in node_by_ip.items():
        related = source_sink_related(ip, node, source_ips, sink_ips)
        fallback_scores[ip] = _topology_seed(node, related)[0]
    fallback_max = max(fallback_scores.values(), default=0.0)
    if fallback_max > 0:
        fallback_scores = {
            ip: score / fallback_max for ip, score in fallback_scores.items()
        }

    ranking_scores = scores or fallback_scores
    directed_scores = (
        scores
        if directed
        else score_topo(node_list, info, directed=True)
    )
    undirected_scores = score_topo(node_list, info, directed=False) if scores else {}
    directed_top3 = [ip for ip, _ in sorted_score_items(directed_scores or {}, 3)]
    undirected_top3 = [ip for ip, _ in sorted_score_items(undirected_scores or {}, 3)]

    rankings = []
    for rank, (ip, score) in enumerate(sorted_score_items(ranking_scores, top_k), 1):
        node = node_by_ip.get(ip, {})
        related = source_sink_related(ip, node, source_ips, sink_ips)
        _seed_score, seed_type = _topology_seed(node, related)
        rankings.append(
            {
                "rank": rank,
                "ip": ip,
                "pr_score": round(score, 6),
                "cross": node.get("cross", 0),
                "source_sink_related": related,
                "seed_type": seed_type,
                # Retained as explicit neutral values for trust-tree schema
                # compatibility; alarms never participate in the M1 score.
                "max_alarm_weight": 0,
                "high_weight_alarm_hit": False,
                "high_weight_alarms": [],
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
            "alarm_evidence_used": False,
        },
    }
    block["trust_tree"] = assess_topo_tree(block)
    return block
