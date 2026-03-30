SKILL_META = {
    "skill_id": "11",
    "skill_name": "物理层故障检测",
    "target_error": "纠正大模型将物理层问题误判为核心节点问题的错误",
    "python_executor": "detect_physical_layer_issues",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "是否存在CRC错误日志",
            "是否存在IP地址冲突告警"
        ]
    },
    "execution_instructions": "必须优先检查物理层状态，将检测到的物理层故障设备列为最高嫌疑"
}

def detect_physical_layer_issues(node_list) -> str:
    result_lines = []
    
    for node in node_list:
        # 检查日志中的CRC错误
        crc_errors = any("CRC error" in log.get("desc", "") for log in node.get("logs", []))
        # 检查告警中的IP地址冲突
        ip_conflicts = any("IP address collision" in log.get("desc", "") for log in node.get("logs", []))
        
        if crc_errors or ip_conflicts:
            issue_type = ""
            if crc_errors and ip_conflicts:
                issue_type = "CRC错误和IP地址冲突"
            elif crc_errors:
                issue_type = "CRC错误"
            else:
                issue_type = "IP地址冲突"
            
            result_lines.append(
                f"- 节点 [{node.get('mgmt_ip', '')}] 检出物理层故障关键字: {issue_type}"
            )
    
    if not result_lines:
        return "【自动化事实：物理层检查】未发现异常。"
    
    return "【自动化事实：物理层检查】\n" + "\n".join(result_lines)

EXECUTORS = {
    "detect_physical_layer_issues": detect_physical_layer_issues
}