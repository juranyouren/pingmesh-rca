SKILL_META = {
    "skill_id": "7",
    "skill_name": "核心层节点告警检查",
    "target_error": "纠正将下游节点错误地作为根因设备的误判",
    "python_executor": "check_core_node_alerts",
    "trigger_conditions": {
        "logic": "ALWAYS",
        "rules": []
    },
    "execution_instructions": "必须优先将发现的核心层告警节点作为根因设备，禁止将下游节点列为根因！"
}

def check_core_node_alerts(node_list) -> str:
    result_lines = []
    core_nodes = [node for node in node_list if node.get('role') == 'CORE' and (node.get('alarms') or any(log['name'] == 'ospfMaxAgeLsa' for log in node.get('logs', [])))]
    
    if core_nodes:
        sorted_cores = sorted(core_nodes, key=lambda x: x['mgmt_ip'])
        for node in sorted_cores:
            alert_desc = f"核心层节点 {node['mgmt_ip']} 存在告警或关键日志:"
            if node.get('alarms'):
                alert_desc += " 存在未处理的告警信息"
            if any(log['name'] == 'ospfMaxAgeLsa' for log in node.get('logs', [])):
                alert_desc += " 且检测到OSPF路由老化现象"
            result_lines.append(alert_desc)
        return "【自动化事实5：核心层节点告警检查】\n" + "\n".join(result_lines)
    else:
        return "【自动化事实5：核心层节点告警检查】未发现核心层节点存在告警或异常日志。"

EXECUTORS = {
    "check_core_node_alerts": check_core_node_alerts
}