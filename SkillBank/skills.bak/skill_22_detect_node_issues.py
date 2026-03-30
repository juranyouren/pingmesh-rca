SKILL_META = {
    "skill_id": "22",
    "skill_name": "节点状态异常检测",
    "target_error": "检测网络节点中是否存在DOWN状态或PACKET_DROP丢包现象",
    "python_executor": "detect_node_issues",
    "trigger_conditions": {
        "logic": "ALWAYS",
        "rules": ["any node with alarm status DOWN or PACKET_DROP"]
    },
    "execution_instructions": "必须将检测到的异常节点作为首要排查对象"
}

def detect_node_issues(node_list) -> str:
    down_nodes = []
    drop_nodes = []
    
    for node in node_list:
        node_info = node_list[node]
        alarms = node_info.get("alarms", [])
        logs = node_info.get("logs", [])
        
        # 检查告警信息中的DOWN状态
        for alarm in alarms:
            if 'DOWN' in alarm.get('desc_summary', '') or 'DOWN' in alarm.get('name', ''):
                down_nodes.append(node_info['mgmt_ip'])
                break
        
        # 检查日志中的丢包信息
        for log in logs:
            if 'PACKET_DROP' in log.get('desc', '') or 'DISCARD' in log.get('desc', ''):
                drop_nodes.append(node_info['mgmt_ip'])
                break
    
    # 去重并按严重性排序（DOWN状态优先）
    issue_nodes = list(set(down_nodes + drop_nodes))
    issue_nodes.sort(key=lambda x: x in down_nodes, reverse=True)
    
    if not issue_nodes:
        return "【自动化事实X：节点状态异常检测】未发现异常。"
    
    result_lines = [
        f"检测到以下异常节点：{', '.join(issue_nodes)}",
        "建议优先排查以下设备："
    ]
    
    for ip in issue_nodes:
        status = "DOWN" if ip in down_nodes else "PACKET_DROP"
        result_lines.append(f"- {ip}: {status}状态异常")
    
    return "【自动化事实X：节点状态异常检测】\n" + "\n".join(result_lines)

EXECUTORS = {
    "detect_node_issues": detect_node_issues
}