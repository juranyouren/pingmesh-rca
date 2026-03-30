SKILL_META = {
    "skill_id": "27",
    "skill_name": "核心节点优先排查",
    "target_error": "纠正大模型将下游节点误判为根因的情况",
    "python_executor": "prioritize_core_nodes",
    "trigger_conditions": {
        "logic": "AND",
        "rules": [
            "存在物理层DOWN告警",
            "包含CORE角色的节点有告警"
        ]
    },
    "execution_instructions": "必须将CORE层节点列为最高嫌疑，禁止将下游节点设为根因！"
}

def prioritize_core_nodes(node_list) -> str:
    core_nodes = [node for node in node_list if node.get('role') == 'CORE' and node.get('alarms')]
    if not core_nodes:
        return "【自动化事实X：核心节点优先排查】未发现CORE层异常。"
    
    result_lines = []
    for node in core_nodes:
        ip = node['mgmt_ip']
        alarm_desc = node['alarms'][0]['desc_summary'] if node['alarms'] else "未知异常"
        result_lines.append(f"检测到CORE层节点 {ip} 存在严重异常：{alarm_desc}")
    
    return "【自动化事实X：核心节点优先排查】\n" + "\n".join(result_lines)

EXECUTORS = {
    "prioritize_core_nodes": prioritize_core_nodes
}