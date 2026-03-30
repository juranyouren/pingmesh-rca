SKILL_META = {
    "skill_id": "26",
    "skill_name": "物理层故障关联分析",
    "target_error": "纠正大模型对物理层DOWN状态的误判，特别是在拓扑分析中的汇聚节点判断错误",
    "python_executor": "analyze_physical_layer_issues",
    "trigger_conditions": {"logic": "ALWAYS", "rules": []},
    "execution_instructions": "必须将此事实作为首要分析依据，重新评估所有物理层DOWN节点的关联性"
}

def analyze_physical_layer_issues(node_list) -> str:
    result_lines = []
    core_nodes = []
    spine_nodes = []
    for node_info in node_list:
        node = node_info.get("node", {})
        mgmt_ip = node.get("mgmt_ip")
        role = node.get("role")
        alarms = node.get("alarms", [])
        logs = node.get("logs", [])
        
        if not mgmt_ip:
            continue
            
        # 检查物理层DOWN状态
        if any("DOWN" in log.get("desc", "") for log in logs):
            if role == "CORE":
                core_nodes.append(mgmt_ip)
            elif role == "SPINE":
                spine_nodes.append(mgmt_ip)
        
        # 检查关键告警
        if any("LACP_STATE_DOWN" in alarm.get("name", "") for alarm in alarms):
            result_lines.append(f"- 节点 [{mgmt_ip}] 发现LACP状态DOWN告警")
        if any("packet drop" in log.get("desc", "").lower() for log in logs):
            result_lines.append(f"- 节点 [{mgmt_ip}] 发现数据包丢失现象")
        if any("CPU overload" in log.get("desc", "").lower() for log in logs):
            result_lines.append(f"- 节点 [{mgmt_ip}] 发现CPU过载问题")
    
    if core_nodes:
        result_lines.insert(0, f"警告：发现核心网络节点存在物理层DOWN状态：{', '.join(core_nodes)}")
    if spine_nodes:
        result_lines.insert(0, f"警告：发现骨干网络节点存在物理层DOWN状态：{', '.join(spine_nodes)}")
    
    if not result_lines:
        return "【自动化事实1：物理层故障关联分析】未发现异常。"
    
    return "【自动化事实1：物理层故障关联分析】\n" + "\n".join(result_lines)

EXECUTORS = {
    "analyze_physical_layer_issues": analyze_physical_layer_issues
}