SKILL_META = {
    "skill_id": "30",
    "skill_name": "物理层故障检测",
    "target_error": "纠正大模型在物理层DOWN节点上的误判",
    "python_executor": "check_physical_layer_status",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "节点状态为DOWN",
            "存在物理层相关告警"
        ]
    },
    "execution_instructions": "必须立即将物理层DOWN的节点作为首要排查对象，优先检查这些节点的连接状态和硬件健康状况。"
}

def check_physical_layer_status(node_list) -> str:
    down_nodes = []
    for node in node_list:
        if node.get('mgmt_ip') and node.get('logs'):
            for log in node['logs']:
                if 'DOWN' in log.get('desc', '') or 'DOWN' in log.get('name', ''):
                    down_nodes.append(node)
    if not down_nodes:
        return "【自动化事实1：物理层检查】未发现异常。"
    result = []
    for node in down_nodes:
        result.append(f"- 节点 {node['mgmt_ip']} 检出底层故障关键字: DOWN")
    return "【自动化事实1：物理层检查】\n" + "\n".join(result)

EXECUTORS = {
    "check_physical_layer_status": check_physical_layer_status
}