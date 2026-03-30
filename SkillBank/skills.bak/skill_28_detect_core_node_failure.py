SKILL_META = {
    "skill_id": "28",
    "skill_name": "核心节点故障检测",
    "target_error": "避免将下游节点误判为根因，而忽略上游核心节点的故障",
    "python_executor": "detect_core_node_failure",
    "trigger_conditions": {"logic": "ALWAYS", "rules": []},
    "execution_instructions": "必须优先考虑核心节点的入方向错误告警，禁止将下游节点列为根因"
}

def detect_core_node_failure(node_list) -> str:
    result_lines = []
    core_nodes = [node for node in node_list if node.get('role') == 'CORE']
    
    for node in core_nodes:
        alarms = node.get('alarms', [])
        for alarm in alarms:
            if '入方向错误报文数量异常' in alarm.get('name', ''):
                result_lines.append(f"警告：发现核心网络枢纽节点(SPINE/CORE)存在告警，极大可能为爆炸半径源头：{node['mgmt_ip']}")
                result_lines.append("必须优先将此节点作为根因输出，禁止将下游节点设为根因！")
                return f"【自动化事实X：核心节点故障检测】\n" + "\n".join(result_lines)
    
    return "【自动化事实X：核心节点故障检测】未发现异常。"

EXECUTORS = {
    "detect_core_node_failure": detect_core_node_failure
}