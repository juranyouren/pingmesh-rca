SKILL_META = {
    "skill_id": "17",
    "skill_name": "CORE层告警过滤",
    "target_error": "防止下游节点在CORE层告警时被误判为根因",
    "python_executor": "check_core_alerts",
    "trigger_conditions": {
        "logic": "ANY",
        "rules": [
            "node.role == 'CORE' and len(node.alarms) > 0"
        ]
    },
    "execution_instructions": "必须优先将CORE层节点作为根因，禁止将下游节点设为根因！"
}

def check_core_alerts(node_list) -> str:
    result_lines = []
    for node in node_list:
        if node.get('role') == 'CORE' and len(node.get('alarms', [])) > 0:
            result_lines.append(f"必须优先将CORE层节点({node['mgmt_ip']})作为根因，禁止将下游节点设为根因！")
    
    if not result_lines:
        return "【自动化事实X：CORE层告警过滤】未发现异常。"
    return "【自动化事实X：CORE层告警过滤】\n" + "\n".join(result_lines)

EXECUTORS = {
    "check_core_alerts": check_core_alerts
}