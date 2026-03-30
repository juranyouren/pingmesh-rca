# skills/skill_03_protocol_cloud_lines.py

# ==========================================
# 1. 技能元数据配置 (喂给大语言模型看的 JSON)
# ==========================================
SKILL_META = {
    "skill_id": "3",
    "skill_name": "协议层与专线控制面检查",
    "target_error": "忽略 OSPF/BGP 等路由协议震荡或专线限速策略",
    "python_executor": "check_protocol_and_cloud_lines",
    "trigger_conditions": {
        "logic": "ALWAYS",
        "rules": []
    },
    "execution_instructions": "提取BGP断连、OSPF老化、云专线超速等逻辑面故障并关联到具体设备。"
}

# ==========================================
# 2. 具体的 Python 执行逻辑 (硬规则计算)
# ==========================================
def check_protocol_and_cloud_lines(node_list) -> str:
    """
    入参 node_list: 经过统一处理的节点字典列表列表 (List[Dict])
    出参 str: 带有强引导语气的【自动化事实】字符串
    """
    issues = []
    protocol_kws = ["BGP", "OSPF", "VRRP", "邻居断开", "STATE CHANGE", "OSPFMAXAGELSA"]
    cloud_kws = ["云专线-接口速率超", "LDM_STRACK_SRCMAC"] # 专线超速与MAC抑制
    
    for n in node_list:
        node = n.get("node", n)
        ip = node.get("mgmt_ip", "Unknown_IP")
        
        for item in node.get("alarms", []) + node.get("logs", []):
            content = str(item.get("desc_summary", item.get("desc", item.get("name", "")))).upper()
            
            if any(kw.upper() in content for kw in protocol_kws):
                issues.append(f"- [{ip}] 协议状态异常: {content}")
            if any(kw.upper() in content for kw in cloud_kws):
                issues.append(f"- [{ip}] 专线/转发面限制: {content}")
                
    if not issues:
        return "【自动化事实3：协议层与专线】未发现 BGP/OSPF 等控制面异常或专线受限。"
        
    # 使用 set 去重并保持格式
    unique_issues = list(set(issues))
    unique_issues.sort()
    return "【自动化事实3：协议层与专线】\n" + "\n".join(unique_issues)

# ==========================================
# 3. 注册暴露给主程序的执行器映射
# ==========================================
EXECUTORS = {
    "check_protocol_and_cloud_lines": check_protocol_and_cloud_lines
}