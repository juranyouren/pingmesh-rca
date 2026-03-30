SKILL_META = {
    "skill_id": "13",
    "skill_name": "核心层异常检测",
    "target_error": "纠正将下游节点误判为根因的问题，优先识别核心层异常",
    "python_executor": "core_layer_exception_detection",
    "trigger_conditions": {"logic": "ALWAYS", "rules": []},
    "execution_instructions": "必须将核心层异常设备列为最高嫌疑，禁止将下游节点作为根因"
}

def core_layer_exception_detection(node_list) -> str:
    result_lines = []
    core_nodes = []
    
    for node in node_list:
        if node.get("role") == "CORE":
            if node.get("alarms") or node.get("logs"):
                core_nodes.append(node["mgmt_ip"])
    
    if core_nodes:
        result_lines.append(f"检测到核心层设备存在异常：{core_nodes}")
        result_lines.append("强烈建议必须优先排查这些核心层设备")
        result_lines.append("禁止将下游节点作为根因设备")
        return f"【自动化事实X：核心层异常检测】\n- " + "\n- ".join(result_lines)
    
    return "【自动化事实X：核心层异常检测】未发现核心层异常。"

EXECUTORS = {
    "core_layer_exception_detection": core_layer_exception_detection
}