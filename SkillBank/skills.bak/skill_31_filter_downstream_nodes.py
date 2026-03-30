SKILL_META = {
    "skill_id": "31",
    "skill_name": "下游节点误判排除",
    "target_error": "下游节点误判为根因设备",
    "python_executor": "filter_downstream_nodes",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "node.role == 'LEAF' and len(node.alarms) > 0"
        ]
    },
    "execution_instructions": "必须将这些下游节点排除，优先排查上游核心节点"
}

def filter_downstream_nodes(node_list) -> str:
    result_lines = []
    for node in node_list:
        if (
            node.get('type') == 'DEVICE' and 
            node.get('role') == 'LEAF' and 
            len(node.get('alarms', [])) > 0
        ):
            ip = node.get('mgmt_ip')
            result_lines.append(f"警告：下游节点 {ip} 存在告警，但可能为爆炸半径受害者")
    
    if not result_lines:
        return "【自动化事实X：下游节点误判排除】未发现异常。"
    return "【自动化事实X：下游节点误判排除】\n" + "\n".join(result_lines)

EXECUTORS = {
    "filter_downstream_nodes": filter_downstream_nodes
}