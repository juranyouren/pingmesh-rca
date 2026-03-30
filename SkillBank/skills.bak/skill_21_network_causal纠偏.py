SKILL_META = {
    "skill_id": "21",
    "skill_name": "网络设备因果纠偏",
    "target_error": "纠正将下游设备误判为根因的问题，强制将SPINE层设备作为根因",
    "python_executor": "network_causal纠偏",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "节点角色为SPINE且存在'物理网交换机接口流量突降智能告警'",
            "节点角色为LEAF且存在PACKET_DROP或DISCARD日志"
        ]
    },
    "execution_instructions": "必须优先将SPINE层设备列为根因！严禁将LEAF层或其他下游设备作为根因！"
}

def network_causal纠偏(node_list) -> str:
    spine_nodes = []
    for node in node_list:
        if node.get('role') == 'SPINE':
            for alarm in node.get('alarms', []):
                if '物理网交换机接口流量突降智能告警' in alarm.get('name', ''):
                    spine_nodes.append(node['mgmt_ip'])
                    break
    
    if not spine_nodes:
        return "【自动化事实X：网络设备因果纠偏】未发现SPINE层故障源。"
    
    result_lines = []
    result_lines.append(f"必须优先将以下SPINE层设备列为根因:")
    result_lines.extend([f"- 节点 [{ip}] 是SPINE层设备且检出流量突降告警" for ip in spine_nodes])
    result_lines.append("严禁将LEAF层或其他下游设备作为根因！")
    
    return "【自动化事实X：网络设备因果纠偏】\n" + "\n".join(result_lines)

EXECUTORS = {
    "network_causal纠偏": network_causal纠偏
}