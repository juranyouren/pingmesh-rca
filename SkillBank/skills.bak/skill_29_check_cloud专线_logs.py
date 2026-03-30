SKILL_META = {
    "skill_id": "29",
    "skill_name": "云专线速率与MAC抑制检查",
    "target_error": "误判云专线接口速率过高及源MAC地址抑制日志对网络故障的影响",
    "python_executor": "check_cloud专线_logs",
    "trigger_conditions": {"logic": "ALWAYS", "rules": []},
    "execution_instructions": "必须立即将检测到的节点列为最高嫌疑设备，并在根因分析中优先考虑其影响"
}

def check_cloud专线_logs(node_list) -> str:
    result_lines = []
    detected_ips = set()
    
    for node in node_list:
        node_ip = node.get("mgmt_ip")
        if not node_ip:
            continue
            
        # 检查告警中的云专线速率问题
        for alarm in node.get("alarms", []):
            if "云专线-接口速率超" in alarm.get("name", ""):
                if node_ip not in detected_ips:
                    detected_ips.add(node_ip)
                    result_lines.append(f"检测到云专线接口速率过高告警，涉及设备IP：{node_ip}")
        
        # 检查日志中的源MAC地址抑制问题
        for log in node.get("logs", []):
            if "LDM_STRACK_SRCMAC" in log.get("desc", ""):
                if node_ip not in detected_ips:
                    detected_ips.add(node_ip)
                    result_lines.append(f"检测到源MAC地址抑制日志，涉及设备IP：{node_ip}")
    
    if not result_lines:
        return "【自动化事实X：云专线速率与MAC抑制检查】未发现云专线速率过高或源MAC地址抑制问题。"
    
    return "【自动化事实X：云专线速率与MAC抑制检查】\n" + "\n".join(result_lines)

EXECUTORS = {
    "check_cloud专线_logs": check_cloud专线_logs
}