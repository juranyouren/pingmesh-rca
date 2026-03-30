SKILL_META = {
    "skill_id": "19",
    "skill_name": "物理层DOWN告警检测",
    "target_error": "纠正因物理层DOWN或PACKET_DROP导致的误判",
    "python_executor": "detect_physical_layer_down",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "节点日志中包含'DOWN'关键字",
            "节点日志中包含'PACKET_DROP'关键字"
        ]
    },
    "execution_instructions": "必须将这些节点列为最高嫌疑，并优先排查其物理层状态"
}

def detect_physical_layer_down(node_list) -> str:
    result_lines = []
    for node in node_list:
        node_info = node.get("node_info", {})
        mgmt_ip = node_info.get("mgmt_ip")
        logs = node_info.get("logs", [])
        
        for log in logs:
            desc = log.get("desc", "")
            if "DOWN" in desc or "PACKET_DROP" in desc:
                result_lines.append(f"- 节点 [{mgmt_ip}] 检出物理层故障关键字: {desc.split('(')[0]}")
                break
    
    if not result_lines:
        return "【自动化事实6：物理层DOWN告警检测】未发现异常。"
    return "【自动化事实6：物理层DOWN告警检测】\n" + "\n".join(result_lines)

EXECUTORS = {
    "detect_physical_layer_down": detect_physical_layer_down
}