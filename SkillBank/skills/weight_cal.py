SKILL_META = {
    "skill_id": "1",
    "skill_name": "calculate_node_alarm_weights",
    "target_error": """模型有时无法区分海量告警中哪些是具有决定性意义的底层/物理层告警，导致将只触发了低权重告警的受害者节点误判为根因节点。""",
    "python_executor": "calculate_node_alarm_weights",
    "trigger_conditions": {
        "logic": """当需要评估 Nodes 列表中各个节点的告警严重程度，以辅助判断谁更有可能是根因时触发。""",
        "rules": ["node_list 数据不为空"],
        "negative_rules": ["如果节点间发生的告警类型完全相同（无法通过权重区分），则不应该依赖此技能"]
    },
    "execution_instructions": """读取全局环境中的告警权重文件（或内置的默认高优告警权重），提取 Nodes 列表中每个节点关联的所有告警名称。对比权重表，找出每个节点身上发生的最大优先级分数（alarm_priority），并将其作为该节点的‘最大告警权重’进行输出。"""
}

import os
import json

def calculate_node_alarm_weights(node_list: list, info:dict={},dirpath="/home/sbp/lixinyang/pingmesh/data/weights/classified_alarms/all_alarms.json") -> str:
    # 1. 内置核心权重表作为兜底
    default_weights = {
        "stachg_todwn": 100,
        "trunkdown": 100,
        "vlan接口down(dcn)": 100
    }

    # 2. 尝试动态加载权重文件
    if os.path.exists(dirpath):
        try:
            with open(dirpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    if "alarm_name" in item and "alarm_priority" in item:
                        default_weights[str(item["alarm_name"]).lower()] = int(item["alarm_priority"])
        except Exception:
            pass

    # 3. 遍历节点计算权重
    node_results = []
    for node in node_list:
        node_ip = node.get("mgmt_ip", "Unknown_Node")
        # 合并告警和日志进行扫描
        all_events = node.get("alarms", []) + node.get("logs", [])
        
        max_weight = 0
        triggered_alarms = []

        for event in all_events:
            name = ""
            if isinstance(event, str):
                name = event
            elif isinstance(event, dict):
                name = event.get("alarm_name", event.get("name", ""))
            
            if not name: continue

            name_lower = str(name).lower()
            if name_lower in default_weights:
                weight = default_weights[name_lower]
                if weight > max_weight:
                    max_weight = weight
                if name not in triggered_alarms:
                    triggered_alarms.append(name)

        if max_weight > 0:
            node_results.append({
                "ip": node_ip,
                "weight": max_weight,
                "alarms": ", ".join(triggered_alarms)
            })

    if not node_results:
        return "【自动化事实提取：节点权重诊断】未能从节点列表中提取出有效数据或未命中任何高优告警"

    # --- 核心修改：按权重从大到小排序，并取前五个 ---
    node_results.sort(key=lambda x: x["weight"], reverse=True)
    top_nodes = node_results[:5]
    # ------------------------------------------

    result_lines = [
        f"节点 {item['ip']} 匹配到权重告警 [{item['alarms']}]，最高权重为: {item['weight']}" 
        for item in top_nodes
    ]

    newline = chr(10)
    return f"【自动化事实提取：节点权重诊断（Top 5 权重排序）】{newline}" + newline.join(result_lines)

EXECUTORS = {
    "calculate_node_alarm_weights": calculate_node_alarm_weights
}