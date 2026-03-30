SKILL_META = {
    "skill_id": "18",
    "skill_name": "物理层故障优先级调整",
    "target_error": "纠正因物理层故障导致的根因定位误判",
    "python_executor": "adjust_physical_layer_priority",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "告警中包含'DOWN'关键字",
            "告警中包含'DISCARD'关键字",
            "告警中包含'PACKET_DROP'关键字"
        ]
    },
    "execution_instructions": "必须立即将检测到物理层故障的节点列为最高嫌疑，并优先进行故障隔离和修复"
}

def adjust_physical_layer_priority(node_list) -> str:
    result_lines = []
    for node in node_list:
        if node.get('alarms'):
            for alarm in node['alarms']:
                if 'DOWN' in alarm['desc_summary'] or 'DISCARD' in alarm['desc_summary'] or 'PACKET_DROP' in alarm['desc_summary']:
                    result_lines.append(f"- 节点 [{node['mgmt_ip']}] 检出物理层故障关键字: {', '.join([k for k in ['DOWN','DISCARD','PACKET_DROP'] if k in alarm['desc_summary']])}")
    
    if not result_lines:
        return "【自动化事实2：物理层故障优先级调整】未发现异常。"
    else:
        return "【自动化事实2：物理层故障优先级调整】检测到物理层故障，请立即排查以下节点:\n" + "\n".join(result_lines)

EXECUTORS = {
    "adjust_physical_layer_priority": adjust_physical_layer_priority
}