SKILL_META = {
    "skill_id": "2",
    "skill_name": "unified_topology_alarm_rank",
    "target_error": """大模型面对多个独立的诊断结果时容易产生逻辑冲突和幻觉缝合。此工具解决了孤立看告警或孤立看拓扑的局限性。""",
    "python_executor": "unified_topology_alarm_rank",
    "trigger_conditions": {
        "logic": """此工具为全局最高优先级诊断！每次根因分析时均应默认触发。它已经融合了【底层告警权重】和【全局物理拓扑连通性】。大模型必须基于此工具的输出排名作为最核心的依据。""",
        "rules": ["存在 nodes.json 和 info.json 数据"],
        "negative_rules": ["无"]
    },
    "execution_instructions": """读取全局环境中的告警权重文件，提取每个节点的最高告警权重。将该权重作为 RWR (PageRank) 图算法的初始异常概率（Personalization）。同时结合 pingmesh 源/目的 IP 以及跨路径交汇次数（cross）进行乘数放大，最后通过物理图网络进行稳态收敛，输出最终的综合拓扑嫌疑度排名。"""
}

import os
import json
try:
    import networkx as nx
except ImportError:
    nx = None

def unified_topology_alarm_rank(node_list: list, infodta: dict, weight_dirpath="/home/sbp/lixinyang/pingmesh/data/weights/classified_alarms/all_alarms.json") -> str:


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
            # 如果命中了权重表，直接使用该权重作为核心基数！
            entity_score += float(max_weight)
        elif node.get("alarms"):
            # 有告警但没命中权重表，给个底分
            entity_score += len(node.get("alarms")) * 2.0
        elif node.get("logs"):
            # 只有日志，给极其微弱的嫌疑分，防止彻底隐身
            entity_score += 0.5
            
        # ---- 乘数放大机制：结合拓扑咽喉 cross ----
        # 只有在设备本身存在异常(entity_score>0)时，作为交通枢纽(cross)才会放大其嫌疑
        if entity_score > 0 and cross_count > 0:
            # 例如：命中权重60，且交汇了2条失败路径，得分为 60 + 60*2*0.5 = 120分！
            entity_score += entity_score * cross_count * 0.5
            
        initial_score = 0.1 + entity_score
        
        # 源/目的 IP 仅作为受害者给予微弱加分 (不再喧宾夺主)
        if ip in source_ips or ip in sink_ips:
            initial_score += 0.5
            
        personalization[ip] = initial_score
        
        # 记录展示元数据，给大模型看
        alarm_str = f"[{', '.join(triggered_high_alarms)}](权重{max_weight})" if max_weight > 0 else "[无高优告警]"
        node_meta[ip] = {
            "role": role,
            "cross": cross_count,
            "alarm_summary": alarm_str
        }

    if len(G.nodes) == 0:
        return "【综合计算失败】未找到任何有效的网络节点数据。"

    # 补齐不在 node_list 中的隐式邻居
    for n in G.nodes:
        if n not in personalization:
            personalization[n] = 0.1

    # ================= 4. 执行图收敛 =================
    try:
        rwr_scores = nx.pagerank(G, alpha=0.85, personalization=personalization)
    except Exception as e:
        return f"【拓扑算法计算异常】图收敛失败: {str(e)}"

    # ================= 5. 格式化综合输出 =================
    sorted_nodes = sorted(rwr_scores.items(), key=lambda x: x[1], reverse=True)
    
    newline = chr(10)
    result_lines = [
        "【终极专家诊断：物理拓扑与告警权重综合排行榜 (Top 10)】",
        "（说明：此得分为图神经网络结合【节点真实告警权重】、【跨路径交汇枢纽度(cross)】与【物理连通性】计算得出的综合稳态概率。大模型必须严格以此排行榜作为根因定位的最高依据！）",
        "--------------------------------------------------"
    ]
    
    for rank, (ip, score) in enumerate(sorted_nodes[:10], 1):
        display_score = round(score * 100, 2)
        meta = node_meta.get(ip, {"role": "UNKNOWN", "cross": 0, "alarm_summary": "[未知]"})
        result_lines.append(
            f"Rank {rank}: [IP: {ip}] | [角色: {meta['role']}] | [Cross: {meta['cross']}] | 核心告警: {meta['alarm_summary']} | 综合嫌疑度: {display_score} 分"
        )
        
    return newline.join(result_lines)

EXECUTORS = {
    "unified_topology_alarm_rank": unified_topology_alarm_rank
}