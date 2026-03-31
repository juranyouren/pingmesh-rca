SKILL_META = {
    "skill_id": "9",
    "skill_name": "CORE层设备优先检查",
    "target_error": "错误排除CORE层设备作为故障源",
    "python_executor": "check_core_devices",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "节点.role == 'CORE' and 节点.alert_status == 'active'",
            "节点.topo_distance <= 2"
        ]
    },
    "execution_instructions": "如果发现CORE层设备存在告警，必须将其列为最高嫌疑；如果未发现CORE层设备告警，但存在拓扑距离小于等于2的设备，请优先排查这些设备"
}

def check_core_devices(node_list) -> str:
    result_lines = []
    for node in node_list:
        if node.get("role") == "CORE" and node.get("alert_status") == "active":
            result_lines.append(f"强烈建议将CORE层设备 {node['id']} 列为最高嫌疑")
        elif node.get("topo_distance", 0) <= 2:
            result_lines.append(f"必须优先排查距离故障点较近的设备 {node['id']}")
    
    if not result_lines:
        return "【自动化事实1：CORE层设备优先检查】未发现异常。"
    return f"【自动化事实1：CORE层设备优先检查】{' '.join(result_lines)}"

EXECUTORS = {
    "check_core_devices": check_core_devices
}