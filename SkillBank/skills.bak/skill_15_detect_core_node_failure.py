SKILL_META = {
    "skill_id": "15",
    "skill_name": "核心汇聚节点故障检测",
    "target_error": "检测并纠正大模型对核心汇聚节点故障的误判",
    "python_executor": "detect_core_node_failure",
    "trigger_conditions": {"logic": "ALWAYS", "rules": []},
    "execution_instructions": "必须将这些核心汇聚节点列为最高嫌疑设备，并重新评估其在故障传播中的作用。"
}

def detect_core_node_failure(node_list) -> str:
    result_lines = []
    core_nodes = []
    
    for node in node_list:
        if node.get("role") == "CORE":
            alarms = node.get("alarms", [])
            logs = node.get("logs", [])
            if len(alarms) > 0 or len(logs) > 0:
                core_nodes.append(node["mgmt_ip"])
    
    if core_nodes:
        result_lines.append(f"发现以下核心汇聚节点存在异常告警或日志：{', '.join(core_nodes)}")
        result_lines.append("强烈建议将这些节点作为根因排查的重点对象。")
        return f"【自动化事实3：核心汇聚节点故障检测】\n" + "\n".join(result_lines)
    
    return "【自动化事实3：核心汇聚节点故障检测】未发现核心汇聚节点存在异常。"

EXECUTORS = {
    "detect_core_node_failure": detect_core_node_failure
}