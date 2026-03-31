SKILL_META = {
    "skill_id": "8",
    "skill_name": "拓扑结构分析",
    "target_error": "纠正大模型在网络故障中对多级节点影响的误判",
    "python_executor": "topology_analysis",
    "trigger_conditions": {
        "logic": "AND",
        "rules": [
            "node_list contains multiple hierarchical levels",
            "存在关键节点状态异常"
        ]
    },
    "execution_instructions": "必须重新分析这些节点的影响，并调整推理路径。"
}

def topology_analysis(node_list) -> str:
    result_lines = []
    max_level = 0
    problematic_nodes = []
    
    for node in node_list:
        level = node.get("level", 0)
        status = node.get("status", "")
        if level > max_level:
            max_level = level
        if status.lower() == "error":
            problematic_nodes.append(node["id"])
    
    if max_level >= 2 and problematic_nodes:
        result_lines.append(f"检测到多层次拓扑结构，最高层级为{max_level}级。")
        result_lines.append("强烈建议重新分析以下关键节点的影响：")
        result_lines.append(", ".join(problematic_nodes))
        result_lines.append("这些节点的异常可能对整体网络造成连锁反应。")
        return "【自动化事实X：拓扑结构分析】".join(result_lines)
    else:
        return "【自动化事实X：拓扑结构分析】未发现异常。"

EXECUTORS = {
    "topology_analysis": topology_analysis
}