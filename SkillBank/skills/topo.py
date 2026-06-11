SKILL_META = {
    "skill_id": "1",
    "skill_name": "topology_pagerank_rank",
    "target_error": "纯拓扑 PageRank 忽略告警权重、跨路径交汇度和故障传播方向，导致根因设备排名偏低或被淹没在海量节点中。",
    "python_executor": "topology_pagerank_rank",
    "trigger_conditions": {
        "logic": "全局最高优先级诊断工具，每次根因分析默认触发。融合告警权重 + 物理拓扑连通性 + 有向/无向 PageRank，输出综合嫌疑度排名及 Top-10 节点完整档案。",
        "rules": ["node_list 不为空", "存在拓扑边 (linked_to / linked_from)"],
        "negative_rules": ["无"]
    },
    "execution_instructions": "1. 加载告警权重文件构建 personalization 向量。2. 结合 cross 交汇度和 source/sink IP 邻近度放大嫌疑分。3. 同时执行无向和有向 PageRank 并对比。4. 提取 Top-10 嫌疑节点的完整告警/日志档案供 LLM 最终裁决。"
}

import os
import json
try:
    import networkx as nx
except ImportError:
    nx = None


# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers (mirror graph_only.py)
# ══════════════════════════════════════════════════════════════════════════════

def _load_alarm_weights(weight_dirpath):
    """Load alarm weight dict from JSON array file, lowercased keys."""
    weights = {
        "stachg_todwn": 100,
        "trunkdown": 100,
        "vlan接口down(dcn)": 100
    }
    if weight_dirpath and os.path.exists(weight_dirpath):
        try:
            with open(weight_dirpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    if "alarm_name" in item and "alarm_priority" in item:
                        weights[str(item["alarm_name"]).lower()] = int(item["alarm_priority"])
        except Exception:
            pass
    return weights


def _parse_endpoint_ips(infodta):
    """Extract source_ips and sink_ips from info dict."""
    source_ips, sink_ips = [], []
    if infodta and isinstance(infodta, dict):
        try:
            src_val = infodta.get("source_ip", "[]")
            snk_val = infodta.get("sink_ip", "[]")
            source_ips = json.loads(src_val) if isinstance(src_val, str) else src_val
            sink_ips = json.loads(snk_val) if isinstance(snk_val, str) else snk_val
            if not isinstance(source_ips, list): source_ips = []
            if not isinstance(sink_ips, list): sink_ips = []
        except Exception:
            pass
    return source_ips, sink_ips


def _compute_personalization(node_list, weights_dict, source_ips, sink_ips):
    """Build per-device PageRank personalization vector from alarm weights,
       cross count, and endpoint proximity."""
    personalization = {}
    node_meta = {}

    for node in node_list:
        ip = node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))
        if ip == "unknown":
            continue

        role = node.get("role", "UNKNOWN")
        try:
            cross_count = int(node.get("cross", 0))
        except (ValueError, TypeError):
            cross_count = 0

        max_weight = 0
        triggered_alarms = []
        all_events = node.get("alarms", []) + node.get("logs", [])
        for event in all_events:
            name = event if isinstance(event, str) else event.get("alarm_name", event.get("name", ""))
            if not name:
                continue
            name_lower = str(name).lower()
            if name_lower in weights_dict:
                weight = weights_dict[name_lower]
                if weight > max_weight:
                    max_weight = weight
                if name not in triggered_alarms:
                    triggered_alarms.append(name)

        entity_score = 0.0
        if max_weight > 0:
            entity_score += float(max_weight)
        elif node.get("alarms"):
            entity_score += len(node.get("alarms")) * 2.0
        elif node.get("logs"):
            entity_score += 0.5

        if entity_score > 0 and cross_count > 0:
            entity_score += entity_score * cross_count * 0.5

        initial_score = 0.1 + entity_score
        if ip in source_ips or ip in sink_ips:
            initial_score += 0.5

        personalization[ip] = initial_score
        alarm_str = f"[{', '.join(triggered_alarms)}](权重{max_weight})" if max_weight > 0 else "[无高优告警]"
        node_meta[ip] = {"role": role, "cross": cross_count, "alarm_summary": alarm_str}

    return personalization, node_meta


# ══════════════════════════════════════════════════════════════════════════════
# PageRank variants
# ══════════════════════════════════════════════════════════════════════════════

def _run_undirected_pagerank(node_list, weights_dict, source_ips, sink_ips):
    """Undirected PageRank: nx.Graph with alarm-weighted personalization."""
    G = nx.Graph()
    for node in node_list:
        ip = node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))
        if ip == "unknown":
            continue
        G.add_node(ip, role=node.get("role", "UNKNOWN"))
        for neighbor in node.get("linked_to", []) + node.get("linked_from", []):
            G.add_edge(ip, neighbor)

    personalization, node_meta = _compute_personalization(node_list, weights_dict, source_ips, sink_ips)

    if len(G.nodes) == 0:
        return {}, {}, node_meta

    for n in G.nodes:
        if n not in personalization:
            personalization[n] = 0.1

    try:
        scores = nx.pagerank(G, alpha=0.85, personalization=personalization)
    except Exception:
        return {}, {}, node_meta

    return dict(scores), dict(G.nodes(data=True)), node_meta


def _run_directed_pagerank(node_list, weights_dict, source_ips, sink_ips):
    """Directed PageRank: edges reversed from fault propagation direction.
       Fault propagates upstream→device→downstream, RCA traces downstream→device→upstream."""
    G = nx.DiGraph()
    for node in node_list:
        ip = node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))
        if ip == "unknown":
            continue
        G.add_node(ip, role=node.get("role", "UNKNOWN"))
        # Edge points upstream (reverse of fault propagation)
        for upstream_neighbor in node.get("linked_from", []):
            G.add_edge(ip, upstream_neighbor)
        for downstream_neighbor in node.get("linked_to", []):
            G.add_edge(downstream_neighbor, ip)

    personalization, node_meta = _compute_personalization(node_list, weights_dict, source_ips, sink_ips)

    if len(G.nodes) == 0:
        return {}, {}, node_meta

    for n in G.nodes:
        if n not in personalization:
            personalization[n] = 0.1

    try:
        scores = nx.pagerank(G, alpha=0.85, personalization=personalization)
    except Exception:
        return {}, {}, node_meta

    return dict(scores), dict(G.nodes(data=True)), node_meta


def _extract_top_nodes_full_data(node_list, top_ips):
    """Extract cleaned full data for top-ranked IPs from node_list."""
    top_data = {}
    for node in node_list:
        ip = node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))
        if ip in top_ips:
            clean_node = {}
            for k, v in node.items():
                if k not in ("node_sign", "type", "devicetype", "verified_hops_to"):
                    clean_node[k] = v
            top_data[ip] = clean_node
    return top_data


# ══════════════════════════════════════════════════════════════════════════════
# Main executor
# ══════════════════════════════════════════════════════════════════════════════

def topology_pagerank_rank(
    node_list: list,
    infodta: dict = {},
    weight_dirpath: str = "/home/sbp/lixinyang/pingmesh/data/weights/classified_alarms/all_alarms.json",
    directed: bool = True,
    top_k: int = 10
) -> str:
    """
    Unified topology PageRank ranking with alarm weights, cross multiplier,
    and endpoint proximity. Supports both undirected and directed variants.

    Returns JSON string with rankings, scores, and full data for top-K suspects.
    """
    if nx is None:
        return json.dumps({"error": "networkx 未安装"}, ensure_ascii=False)

    weights_dict = _load_alarm_weights(weight_dirpath)
    source_ips, sink_ips = _parse_endpoint_ips(infodta)

    # Run both variants for comparison
    undir_scores, undir_graph, node_meta = _run_undirected_pagerank(
        node_list, weights_dict, source_ips, sink_ips)
    dir_scores, dir_graph, _ = _run_directed_pagerank(
        node_list, weights_dict, source_ips, sink_ips)

    # Use directed scores as primary when directed=True
    primary_scores = dir_scores if directed else undir_scores
    primary_label = "有向 PageRank" if directed else "无向 PageRank"

    if not primary_scores:
        return json.dumps({"error": "图收敛失败或无有效节点"}, ensure_ascii=False)

    # Sort and pick top-K
    sorted_primary = sorted(primary_scores.items(), key=lambda x: x[1], reverse=True)
    top_ips = [ip for ip, _ in sorted_primary[:top_k]]

    # Build ranking table
    ranking = []
    for rank, (ip, score) in enumerate(sorted_primary[:top_k], 1):
        meta = node_meta.get(ip, {"role": "UNKNOWN", "cross": 0, "alarm_summary": "[未知]"})
        ranking.append({
            "rank": rank,
            "ip": ip,
            "score": round(score * 100, 2),
            "role": meta["role"],
            "cross": meta["cross"],
            "alarm_summary": meta["alarm_summary"],
            "score_undirected": round(undir_scores.get(ip, 0) * 100, 2),
            "score_directed": round(dir_scores.get(ip, 0) * 100, 2)
        })

    # Extract full data for top suspects
    top_full_data = _extract_top_nodes_full_data(node_list, top_ips)

    # Build comparison summary
    if undir_scores and dir_scores:
        undir_sorted = sorted(undir_scores.items(), key=lambda x: x[1], reverse=True)
        dir_sorted = sorted(dir_scores.items(), key=lambda x: x[1], reverse=True)
        undir_top3 = [ip for ip, _ in undir_sorted[:3]]
        dir_top3 = [ip for ip, _ in dir_sorted[:3]]
        agreement = len(set(undir_top3) & set(dir_top3)) / 3
    else:
        undir_top3, dir_top3, agreement = [], [], 0

    result = {
        "algorithm": primary_label,
        "top_k": top_k,
        "ranking": ranking,
        "top_suspects_full_data": top_full_data,
        "comparison": {
            "undirected_top3": undir_top3,
            "directed_top3": dir_top3,
            "top3_agreement": round(agreement, 2)
        },
        "total_nodes": len(primary_scores),
        "total_edges": sum(1 for _ in (
            undir_graph if directed else dir_graph
        ))
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


EXECUTORS = {
    "topology_pagerank_rank": topology_pagerank_rank
}
