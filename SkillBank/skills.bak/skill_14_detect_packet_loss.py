SKILL_META = {
    "skill_id": "14",
    "skill_name": "物理层丢包检测",
    "target_error": "纠正将汇聚节点误判为根因的错误",
    "python_executor": "detect_packet_loss",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "节点包含PACKET_DROP关键字",
            "节点包含DISCARD关键字",
            "节点包含DOWN关键字"
        ]
    },
    "execution_instructions": "必须优先检查这些物理层问题节点，不能直接将汇聚节点作为根因"
}

def detect_packet_loss(node_list) -> str:
    packet_loss_nodes = []
    for node in node_list:
        mgmt_ip = node.get('mgmt_ip', '')
        alarms = node.get('alarms', [])
        logs = node.get('logs', [])
        
        # 检查告警和日志中的关键字
        has_packet_loss = any(
            'PACKET_DROP' in a.get('name', '') or 
            'DISCARD' in a.get('desc_summary', '') or 
            'DOWN' in a.get('name', '') 
            for a in alarms
        )
        
        if not has_packet_loss:
            has_packet_loss = any(
                'PACKET_DROP' in l.get('name', '') or 
                'DISCARD' in l.get('desc', '') or 
                'DOWN' in l.get('name', '') 
                for l in logs
            )
        
        if has_packet_loss:
            packet_loss_nodes.append(f"节点 [{mgmt_ip}] 检出物理层故障关键字")
    
    if not packet_loss_nodes:
        return "【自动化事实1：物理层丢包检测】未发现物理层丢包或DOWN状态节点。"
    
    result_lines = [
        "【自动化事实1：物理层丢包检测】",
        "\n".join(packet_loss_nodes),
        "\n强烈建议优先检查这些物理层问题节点，而不是直接将汇聚节点作为根因。"
    ]
    return "\n".join(result_lines)

EXECUTORS = {
    "detect_packet_loss": detect_packet_loss
}