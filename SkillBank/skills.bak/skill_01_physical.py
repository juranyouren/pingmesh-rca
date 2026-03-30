SKILL_META = {
    "skill_id": "1",
    "skill_name": "物理层与链路故障精确扫描",
    "target_error": "未能识别底层物理链路故障（如CRC、端口DOWN）",
    "python_executor": "check_physical_errors",
    "trigger_conditions": {
      "logic": "OR",
      "rules": ["告警现象涉及丢包、Ping异常或连通性问题"]
    },
    "execution_instructions": "执行 Python 脚本，扫描所有节点的底层日志，精确匹配 CRC、DOWN、光模块异常等物理层关键字，并输出确切的故障设备名单。"
}

def check_physical_errors(node_list) -> str:
    faults = []
    physical_keywords = ["CRC", "DOWN", "R_LOS", "OTUCN_LOF", "光模块异常", "硬件故障", "PACKET_DROP", "DISCARD"]
    
    for n in node_list:
        node_ip = n.get("mgmt_ip", "Unknown_IP")
        logs = n.get("logs", []) + n.get("alarms", [])
        
        node_faults = set()
        for log in logs:
            log_text = str(log).upper()
            for kw in physical_keywords:
                if kw.upper() in log_text:
                    node_faults.add(kw)
        
        if node_faults:
            faults.append(f"- 节点 [{node_ip}] 检出底层故障关键字: {', '.join(node_faults)}")
            
    if faults:
        return "【自动化事实1：物理层检查】\n" + "\n".join(faults)
    return "【自动化事实1：物理层检查】未发现明确的 CRC/DOWN 等底层物理硬件报错。"

EXECUTORS = {
    "check_physical_errors": check_physical_errors
}