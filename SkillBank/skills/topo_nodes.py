SKILL_META = {
    "skill_id": "3",
    "skill_name": "extract_top_suspect_nodes_data",
    "target_error": """大模型面对海量节点数据时容易发生Token超载和注意力丢失，导致错过隐蔽的告警或日志。此工具作为核心检索器（Retriever），过滤掉无关背景，只提供高危节点。""",
    "python_executor": "extract_top_suspect_nodes_data",
    "trigger_conditions": {
        "logic": """此工具为全局最高优先级诊断！每次根因分析时均应默认触发。它不仅计算图算法嫌疑度，还会自动提取 Top 10 高危节点的全部原始状态数据（告警和日志），作为大模型最终裁决的唯一核心数据源。""",
        "rules": ["存在 nodes.json 和 info.json 数据"],
        "negative_rules": ["无"]
    },
    "execution_instructions": """计算 RWR 物理拓扑嫌疑度得分，选出前 10 名嫌疑最高的节点 IP。然后遍历原始节点数据源，将这 10 个节点的完整档案（包含 role, alarms, logs, cross 等）提取出来，与排行榜合并输出。"""
}

import os
import json
try:
    import networkx as nx
except ImportError:
    nx = None

def extract_top_suspect_nodes_data(node_list: list, infodta: dict, weight_dirpath="/home/sbp/lixinyang/pingmesh/data/weights/classified_alarms/all_alarms.json") -> str:
    if nx is None:
        return "【图算法执行失败】缺少 networkx 依赖，请执行 pip install networkx。"

    # ================= 1. 加载告警权重字典 =================
    default_weights = {
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
                        default_weights[str(item["alarm_name"]).lower()] = int(item["alarm_priority"])
        except Exception:
            pass

    # ================= 2. 解析源和目的 IP =================
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

    # ================= 3. 构建无向图与计算初始得分 =================
    G = nx.Graph()
    personalization = {}
    node_meta = {} # 记录展示用的元数据

    for node in node_list:
        ip = node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))
        if ip == "unknown":
            continue
            
        role = node.get("role", "UNKNOWN")
        G.add_node(ip, role=role)
        
        # 添加边
        for neighbor in node.get("linked_to", []) + node.get("linked_from", []):
            G.add_edge(ip, neighbor)
            
        # 提取 cross 属性
        try:
            cross_count = int(node.get("cross", 0))
        except (ValueError, TypeError):
            cross_count = 0

        # ---- 计算节点的告警实体得分 (基于真实权重文件) ----
        max_weight = 0
        triggered_high_alarms = []
        
        all_events = node.get("alarms", []) + node.get("logs", [])
        for event in all_events:
            name = event if isinstance(event, str) else event.get("alarm_name", event.get("name", ""))
            if not name: continue
            
            name_lower = str(name).lower()
            if name_lower in default_weights:
                weight = default_weights[name_lower]
                if weight > max_weight:
                    max_weight = weight
                if name not in triggered_high_alarms:
                    triggered_high_alarms.append(name)
        
        # 实体初始基准分计算
        entity_score = 0.0
        
        if max_weight > 0:
            entity_score += float(max_weight)
        elif node.get("alarms"):
            entity_score += len(node.get("alarms")) * 2.0
        elif node.get("logs"):
            entity_score += 0.5
            
        # ---- 乘数放大机制：结合拓扑咽喉 cross ----
        if entity_score > 0 and cross_count > 0:
            entity_score += entity_score * cross_count * 0.5
            
        initial_score = 0.1 + entity_score
        
        # 源/目的 IP 仅作为受害者给予微弱加分
        if ip in source_ips or ip in sink_ips:
            initial_score += 0.5
            
        personalization[ip] = initial_score
        
        # 记录展示元数据
        alarm_str = f"[{', '.join(triggered_high_alarms)}](权重{max_weight})" if max_weight > 0 else "[无高优告警]"
        node_meta[ip] = {
            "role": role,
            "cross": cross_count,
            "alarm_summary": alarm_str
        }

    if len(G.nodes) == 0:
        return "【综合计算失败】未找到任何有效的网络节点数据。"

    for n in G.nodes:
        if n not in personalization:
            personalization[n] = 0.1

    # ================= 4. 执行图收敛 =================
    try:
        rwr_scores = nx.pagerank(G, alpha=0.85, personalization=personalization)
    except Exception as e:
        return f"【拓扑算法计算异常】图收敛失败: {str(e)}"

    # ================= 5. 格式化输出榜单 =================
    sorted_nodes = sorted(rwr_scores.items(), key=lambda x: x[1], reverse=True)
    top_10_nodes = sorted_nodes[:10]
    top_10_ips = [ip for ip, score in top_10_nodes]
    
    newline = chr(10)
    result_lines = [
        "【终极专家诊断：物理拓扑与告警权重综合排行榜 (Top 10)】",
        "（说明：此得分为图神经网络计算得出的客观数学概率。大模型必须以此作为定海神针！）",
        "--------------------------------------------------"
    ]
    
    for rank, (ip, score) in enumerate(top_10_nodes, 1):
        display_score = round(score * 100, 2)
        meta = node_meta.get(ip, {"role": "UNKNOWN", "cross": 0, "alarm_summary": "[未知]"})
        result_lines.append(
            f"Rank {rank}: [IP: {ip}] | [角色: {meta['role']}] | [Cross: {meta['cross']}] | 核心告警: {meta['alarm_summary']} | 综合嫌疑度: {display_score} 分"
        )
        
    # ================= 6. ✨核心修改：提取 Top 10 节点的完整原始数据 =================
    top_10_full_data = {}
    for node in node_list:
        ip = node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))
        if ip in top_10_ips:
            # 清理一些在大模型推理时毫无用处的冗余字段，进一步节省 Token
            clean_node = {}
            for k, v in node.items():
                if k not in ["node_sign", "type", "devicetype", "verified_hops_to"]: 
                    clean_node[k] = v
            top_10_full_data[ip] = clean_node

    result_lines.append("\n==================================================")
    result_lines.append("【🔍 Top 10 嫌疑节点完整状态提取 (含告警与日志详情)】")
    result_lines.append("（说明：请大模型仔细阅读以下 10 个节点的真实 Log 和 Alarms，结合上方的排行榜，做出最终裁决，排除没有异常日志支撑的伪根因。）")
    result_lines.append(json.dumps(top_10_full_data, ensure_ascii=False, indent=2))
        
    return newline.join(result_lines)

EXECUTORS = {
    "extract_top_suspect_nodes_data": extract_top_suspect_nodes_data
}