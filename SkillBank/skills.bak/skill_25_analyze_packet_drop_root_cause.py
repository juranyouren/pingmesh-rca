SKILL_META = {
    "skill_id": "25",
    "skill_name": "Packet Drop Root Cause Analysis",
    "target_error": "Misdiagnosis in network fault scenarios with packet drop and discard events",
    "python_executor": "analyze_packet_drop_root_cause",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "node.alarms contains 'PACKET_DROP'",
            "node.alarms contains 'DISCARD'"
        ]
    },
    "execution_instructions": "Must prioritize these nodes as top suspects for root cause analysis"
}

def analyze_packet_drop_root_cause(node_list) -> str:
    result_lines = []
    packet_drop_nodes = []
    
    for node_info in node_list:
        ip = node_info.get('mgmt_ip', '')
        alarms = node_info.get('alarms', [])
        logs = node_info.get('logs', [])
        
        # Check for packet drop related issues
        has_packet_drop = any('PACKET_DROP' in log.get('name', '') or 
                             'DISCARD' in log.get('desc', '') for log in logs)
        
        if has_packet_drop:
            # Extract timestamp and details
            earliest_log = min(logs, key=lambda x: x['time'])
            timestamp = earliest_log['time']
            desc = earliest_log['desc']
            packet_drop_nodes.append((timestamp, ip, desc))
    
    if not packet_drop_nodes:
        return "【自动化事实2：Packet Drop Root Cause Analysis】未发现异常。"
    
    # Sort by timestamp to find root cause
    packet_drop_nodes.sort()
    for timestamp, ip, desc in packet_drop_nodes:
        result_lines.append(f"- 节点 [{ip}] 检出底层故障关键字: PACKET_DROP, DISCARD (时间: {timestamp}, 描述: {desc})")
    
    return "【自动化事实2：Packet Drop Root Cause Analysis】\n" + "\n".join(result_lines)

EXECUTORS = {
    "analyze_packet_drop_root_cause": analyze_packet_drop_root_cause
}