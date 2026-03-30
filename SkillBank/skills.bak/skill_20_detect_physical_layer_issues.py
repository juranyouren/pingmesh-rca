SKILL_META = {
    "skill_id": "20",
    "skill_name": "物理层异常检测",
    "target_error": "纠正将汇聚节点误判为根因设备的错误，准确识别物理层故障源头",
    "python_executor": "detect_physical_layer_issues",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "节点状态为DOWN",
            "存在BGP状态变化告警",
            "存在链路震荡告警"
        ]
    },
    "execution_instructions": "必须将检测到的物理层故障节点作为最高优先级排查对象，这些节点是网络故障的真正源头！"
}

def detect_physical_layer_issues(node_list) -> str:
    result_lines = []
    suspect_devices = []
    
    for node_info in node_list:
        node_data = node_info.get('data', {})
        alarms = node_data.get('alarms', [])
        
        # 检查DOWN状态
        if any('DOWN' in alarm.get('name', '') for alarm in alarms):
            suspect_devices.append(node_data.get('mgmt_ip'))
            continue
            
        # 检查BGP状态变化
        if any('BGP邻接状态改变' in alarm.get('name', '') for alarm in alarms):
            suspect_devices.append(node_data.get('mgmt_ip'))
            continue
            
        # 检查链路震荡
        if any('linkflapping' in alarm.get('name', '') for alarm in alarms):
            suspect_devices.append(node_data.get('mgmt_ip'))
            continue
    
    if not suspect_devices:
        return "【自动化事实1：物理层检查】\n未发现物理层异常。"
    
    # 生成结果
    result_lines.append(f"节点 [{'、'.join(suspect_devices)}] 检出物理层故障关键字：DOWN")
    return "【自动化事实1：物理层检查】\n" + "\n".join(result_lines)

EXECUTORS = {
    "detect_physical_layer_issues": detect_physical_layer_issues
}