SKILL_META = {
    "skill_id": "16",
    "skill_name": "网络丢包根因分析",
    "target_error": "纠正大模型在多个节点同时出现PACKET_DROP误判的情况",
    "python_executor": "analyze_packet_drop",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "节点日志中包含'QOS_PACKET_DROP'",
            "节点日志中包含'DISCARD'"
        ]
    },
    "execution_instructions": "必须将这些节点列为最高嫌疑，并进一步排查其上游设备"
}

def analyze_packet_drop(node_list) -> str:
    packet_drop_nodes = []
    for node in node_list:
        if node.get('logs'):
            for log in node['logs']:
                if log['name'] == 'QOS_PACKET_DROP' or ('discard' in log['desc'].lower()):
                    packet_drop_nodes.append(node['mgmt_ip'])
    
    if not packet_drop_nodes:
        return "【自动化事实1：网络丢包根因分析】未发现异常。"
    
    result_lines = ["强烈建议将以下节点列为最高嫌疑并优先排查："]
    result_lines.extend(packet_drop_nodes)
    return "【自动化事实1：网络丢包根因分析】\n" + "\n".join(result_lines)

EXECUTORS = {
    "analyze_packet_drop": analyze_packet_drop
}