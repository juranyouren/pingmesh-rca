import os
import json
import time
try:
    import networkx as nx
except ImportError:
    print("请先执行: pip install networkx")
    nx = None

def _load_alarm_weights(weight_dirpath):
    """Load alarm weight dict from JSON array file, lowercased keys."""
    weights = {
        "stachg_todwn": 100,
        "trunkdown": 100,
        "vlan接口down(dcn)": 100
    }
    if os.path.exists(weight_dirpath):
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
    """
    Build per-device PageRank personalization vector from alarm weights,
    cross count, and endpoint proximity.  Shared by undirected and directed variants.
    """
    personalization = {}
    for node in node_list:
        ip = node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))
        if ip == "unknown":
            continue

        try:
            cross_count = int(node.get("cross", 0))
        except Exception:
            cross_count = 0

        max_weight = 0
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
    return personalization


def run_pure_graph_algorithm(node_list: list, infodta: dict,
                              weight_dirpath="/home/sbp/lixinyang/pingmesh/data/weights/classified_alarms/all_alarms.json") -> list:
    """
    Undirected PageRank baseline: nx.Graph + alarm-weighted personalization.
    Returns device IPs sorted by PageRank score (descending).
    """
    if nx is None:
        return []

    weights_dict = _load_alarm_weights(weight_dirpath)
    source_ips, sink_ips = _parse_endpoint_ips(infodta)

    G = nx.Graph()
    personalization = {}
    for node in node_list:
        ip = node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))
        if ip == "unknown":
            continue
        G.add_node(ip, role=node.get("role", "UNKNOWN"))
        for neighbor in node.get("linked_to", []) + node.get("linked_from", []):
            G.add_edge(ip, neighbor)

    personalization = _compute_personalization(node_list, weights_dict, source_ips, sink_ips)

    if len(G.nodes) == 0:
        return []

    for n in G.nodes:
        if n not in personalization:
            personalization[n] = 0.1

    try:
        rwr_scores = nx.pagerank(G, alpha=0.85, personalization=personalization)
    except Exception:
        return []

    sorted_nodes = sorted(rwr_scores.items(), key=lambda x: x[1], reverse=True)
    return [ip for ip, _score in sorted_nodes]


def run_directed_pagerank(node_list: list, infodta: dict,
                           weight_dirpath="/home/sbp/lixinyang/pingmesh/data/weights/classified_alarms/all_alarms.json") -> list:
    """
    Directed PageRank for RCA.

    Fault propagation direction:  linked_from → device → linked_to   (upstream→downstream)
    For RCA we reverse edges so score flows FROM affected endpoints TO upstream root causes:
       device → linked_from  (trace upstream)
       linked_to → device    (from downstream back to this device)

    This means we add edge (A, B) whenever B is upstream of A in the fault propagation DAG.
    PageRank personalization is biased toward source_ips / sink_ips (the observed endpoints),
    so random walks flow backward along the fault propagation path toward the root cause.
    """
    if nx is None:
        return []

    weights_dict = _load_alarm_weights(weight_dirpath)
    source_ips, sink_ips = _parse_endpoint_ips(infodta)

    G = nx.DiGraph()
    for node in node_list:
        ip = node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))
        if ip == "unknown":
            continue
        G.add_node(ip, role=node.get("role", "UNKNOWN"))
        # Edge points upstream (reverse of fault propagation)
        for upstream_neighbor in node.get("linked_from", []):
            G.add_edge(ip, upstream_neighbor)
        # Downstream neighbours point back to this device
        for downstream_neighbor in node.get("linked_to", []):
            G.add_edge(downstream_neighbor, ip)

    personalization = _compute_personalization(node_list, weights_dict, source_ips, sink_ips)

    if len(G.nodes) == 0:
        return []

    for n in G.nodes:
        if n not in personalization:
            personalization[n] = 0.1

    try:
        rwr_scores = nx.pagerank(G, alpha=0.85, personalization=personalization)
    except Exception:
        return []

    sorted_nodes = sorted(rwr_scores.items(), key=lambda x: x[1], reverse=True)
    return [ip for ip, _score in sorted_nodes]

def run_ablation_experiment(root_path: str, output_dir: str, directed: bool = False):
    """
    遍历数据集，只跑图算法（无向 PageRank 或有向 PageRank）。
    """
    mode_name = "有向 PageRank" if directed else "无向 PageRank"
    algo_func = run_directed_pagerank if directed else run_pure_graph_algorithm
    print(f"开始执行纯图算法消融实验 ({mode_name})，扫描目录: {root_path}")
    start_time = time.time()

    results = []
    case_count = 0

    for dirpath, dirnames, filenames in os.walk(root_path):
        node_file = None
        info_file = None

        for f in filenames:
            if f == "info.json":
                info_file = f
            elif ("pingmesh" in f and "全链路.json" in f):
                node_file = f

        if node_file and info_file:
            node_path = os.path.join(dirpath, node_file)
            info_path = os.path.join(dirpath, info_file)

            try:
                nodes_raw = json.load(open(node_path, 'r', encoding='utf-8'))
                node_list = list(nodes_raw.values()) if isinstance(nodes_raw, dict) else nodes_raw
                info_data = json.load(open(info_path, 'r', encoding='utf-8'))

                top_ips = algo_func(node_list, info_data)
                predicted_ips = top_ips[:5]

                mock_json_response = {
                    "reasoning": f"纯图算法 ({mode_name}) 推导，无大模型干预。",
                    "ip": predicted_ips,
                    "propagation_path": {}
                }
                mock_response_str = f"```json\n{json.dumps(mock_json_response, ensure_ascii=False, indent=2)}\n```"

                results.append({
                    "dir": dirpath,
                    "prompt": "GRAPH_ONLY_ABLATION_EXPERIMENT_DIRECTED" if directed else "GRAPH_ONLY_ABLATION_EXPERIMENT",
                    "draft_response": mock_response_str,
                    "response": mock_response_str
                })

                case_count += 1

            except Exception as e:
                print(f"[Error] 处理目录 {dirpath} 失败: {e}")

    os.makedirs(output_dir, exist_ok=True)
    res_file = os.path.join(output_dir, "res.json")
    with open(res_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    print(f"纯图算法 ({mode_name}) 推理完成！共处理 {case_count} 个 Case，耗时: {time.time() - start_time:.2f} 秒")
    print(f"实验结果已保存至: {res_file}")

    return res_file


if __name__ == "__main__":
    import sys
    DATA_ROOT = "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"
    timenow = int(time.time())

    directed = "--directed" in sys.argv
    variant = "directed" if directed else "undirected"
    OUTPUT_DIR = f"/home/sbp/lixinyang/pingmesh/data/res/graph_only_{variant}_{timenow}"

    res_file_path = run_ablation_experiment(DATA_ROOT, OUTPUT_DIR, directed=directed)
    
