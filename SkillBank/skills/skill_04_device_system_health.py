# skills/skill_04_device_system_health.py

# ==========================================
# 1. 技能元数据配置 (喂给大语言模型看的 JSON)
# ==========================================
SKILL_META = {
    "skill_id": "4",
    "skill_name": "设备系统健康度评估",
    "target_error": "遗漏设备自身 OS 异常（如日志溢出、CPU满载）",
    "python_executor": "check_device_system_health",
    "trigger_conditions": {
        "logic": "ALWAYS",
        "rules": []
    },
    "execution_instructions": "若出现核心设备日志溢出或CPU过载，优先判定为设备性能瓶颈导致的非预期网络风暴。"
}

# ==========================================
# 2. 具体的 Python 执行逻辑 (硬规则计算)
# ==========================================
def check_device_system_health(node_list) -> str:
    """
    入参 node_list: 经过统一处理的节点字典列表列表 (List[Dict])
    出参 str: 带有强引导语气的【自动化事实】字符串
    """
    health_issues = []
    
    for n in node_list:
        node = n.get("node", n)
        ip = node.get("mgmt_ip", "Unknown_IP")
        
        for log in node.get("logs", []):
            desc = str(log.get("desc", "")).lower()
            if "logfile number is more than 90 percent" in desc:
                health_issues.append(f"- [{ip}] 严重系统异常：日志磁盘空间溢出 (Logfile > 90%)")
            if "cpu overload" in desc:
                health_issues.append(f"- [{ip}] 严重系统异常：CPU 处理过载")
                
    if not health_issues:
        return "【自动化事实4：系统健康度】未发现设备级别 OS/CPU 异常。"
        
    return "【自动化事实4：系统健康度】\n" + "\n".join(health_issues)

# ==========================================
# 3. 注册暴露给主程序的执行器映射
# ==========================================
EXECUTORS = {
    "check_device_system_health": check_device_system_health
}