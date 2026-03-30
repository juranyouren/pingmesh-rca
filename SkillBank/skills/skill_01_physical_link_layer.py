# skills/skill_01_physical_link_layer.py

# ==========================================
# 1. 技能元数据配置 (喂给大语言模型看的 JSON)
# ==========================================
SKILL_META = {
    "skill_id": "1",
    "skill_name": "物理与链路层综合诊断",
    "target_error": "大模型遗漏底层硬件故障，或在多个物理异常中丢失重点",
    "python_executor": "analyze_physical_and_link_layer",
    "trigger_conditions": {
        "logic": "ALWAYS",
        "rules": []
    },
    "execution_instructions": "请将检出严重物理层故障（DOWN/光模块异常/CRC）的设备作为最优先排查对象。如果存在多台设备异常，优先看骨干网络设备。"
}

# ==========================================
# 2. 具体的 Python 执行逻辑 (硬规则计算)
# ==========================================
def analyze_physical_and_link_layer(node_list) -> str:
    """
    入参 node_list: 经过统一处理的节点字典列表列表 (List[Dict])
    出参 str: 带有强引导语气的【自动化事实】字符串
    """
    critical_faults = []
    packet_drops = []
    
    # 定义关键字分类集合
    kw_critical = {"DOWN", "R_LOS", "OTUCN_LOF", "CRC", "OPTICAL MODULE EXCEPTION", "INVALID", "HARDWARE"}
    kw_drop = {"DISCARD", "PACKET_DROP", "QOS_PACKET_DROP"}
    
    for n in node_list:
        node = n.get("node", n) # 兼容可能存在的嵌套
        ip = node.get("mgmt_ip", "Unknown_IP")
        role = str(node.get("role", "")).upper()
        
        logs_and_alarms = node.get("alarms", []) + node.get("logs", [])
        if not logs_and_alarms:
            continue
            
        found_critical = set()
        found_drops = set()
        
        for item in logs_and_alarms:
            # 兼容 log 和 alarm 的不同字段提取
            content = str(item.get("desc_summary", item.get("desc", item.get("name", "")))).upper()
            
            for kw in kw_critical:
                if kw in content: found_critical.add(kw)
            for kw in kw_drop:
                if kw in content: found_drops.add(kw)
                
        if found_critical:
            critical_faults.append(f"- [{ip}] ({role}) 检出致命物理层故障: {', '.join(found_critical)}")
        elif found_drops:
            packet_drops.append(f"- [{ip}] ({role}) 检出数据面丢包/抛弃: {', '.join(found_drops)}")
            
    result = []
    if critical_faults:
        result.append("🔴 【严重物理层异常】(极高根因嫌疑)：\n" + "\n".join(critical_faults))
    if packet_drops:
        result.append("🟡 【链路拥塞/丢包现象】：\n" + "\n".join(packet_drops))
        
    if not result:
        return "【自动化事实1：物理层检查】未发现底层链路与硬件异常。"
        
    return "【自动化事实1：物理层检查】\n" + "\n".join(result)

# ==========================================
# 3. 注册暴露给主程序的执行器映射
# ==========================================
EXECUTORS = {
    "analyze_physical_and_link_layer": analyze_physical_and_link_layer
}