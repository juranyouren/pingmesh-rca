SKILL_META = {
    "skill_id": "7",
    "skill_name": "网络连通性校验",
    "target_error": "下游节点被误判为根因",
    "python_executor": "check_network_connectivity",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "node.type in ['router', 'switch', 'firewall']",
            "node.metric_value >= 80"
        ]
    },
    "execution_instructions": "必须严格按照以下规则进行判断：如果发现网络设备性能指标异常，必须将其列为最高嫌疑；如果设备状态正常，强烈建议将此节点排除。"
}

def check_network_connectivity(node_list) -> str:
    result_lines = []
    for node in node_list:
        if node.get("type") in ["router", "switch", "firewall"]:
            if node.get("metric_value", 0) >= 80:
                result_lines.append(f"节点 {node.get('name')} 性能指标({node.get('metric_value')})异常，必须将其列为最高嫌疑！")
            else:
                result_lines.append(f"节点 {node.get('name')} 状态正常，建议排除此节点！")
    if not result_lines:
        return "【自动化事实X：网络连通性校验】未发现异常。"
    return "【自动化事实X：网络连通性校验】" + "\n".join(result_lines)

EXECUTORS = {
    "check_network_connectivity": check_network_connectivity
}