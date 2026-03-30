# skills/skill_02_topology_causality.py

# ==========================================
# 1. 技能元数据配置 (喂给大语言模型看的 JSON)
# ==========================================
SKILL_META = {
    "skill_id": "2",
    "skill_name": "拓扑层级与因果倒置纠偏",
    "target_error": "模型容易颠倒因果，将下游受害节点（如服务器VM/LEAF）误判为导致上游核心故障的原因",
    "python_executor": "enforce_topology_causality",
    "trigger_conditions": {
        "logic": "ALWAYS",
        "rules": []
    },
    "execution_instructions": "必须严格遵守网络拓扑因果律：强制将检出的最高层级设备设为根因候选，严禁将端侧服务器或下游叶子节点判定为导致上游故障的根因（它们仅是爆炸半径内的受害者）。"
}

# ==========================================
# 2. 具体的 Python 执行逻辑 (硬规则计算)
# ==========================================
def enforce_topology_causality(node_list) -> str:
    """
    入参 node_list: 经过统一处理的节点字典列表列表 (List[Dict])
    出参 str: 带有强引导语气的【自动化事实】字符串
    """
    tier_map = {"CORE": [], "SPINE": [], "LEAF": [], "ENDPOINT": []}
    
    for n in node_list:
        node = n.get("node", n)
        ip = node.get("mgmt_ip", "Unknown_IP")
        role = str(node.get("role", "")).upper()
        node_type = str(node.get("type", "")).upper()
        
        has_issues = bool(node.get("alarms", []) or node.get("logs", []))
        if not has_issues:
            continue
            
        if "CORE" in role or "DSW" in role:
            tier_map["CORE"].append(ip)
        elif "SPINE" in role:
            tier_map["SPINE"].append(ip)
        elif "LEAF" in role or "TOR" in role:
            tier_map["LEAF"].append(ip)
        elif node_type in ["OBS", "VM", "HOST", "SERVER"] or node.get("node_sign") == "target":
            tier_map["ENDPOINT"].append(ip)
            
    highest_tier = next((tier for tier in ["CORE", "SPINE", "LEAF"] if tier_map[tier]), None)
    
    if not highest_tier:
        return "【自动化事实2：拓扑与爆炸半径】未发现明确的跨层级故障传播。"
        
    result_lines = [f"📌 发现存在告警的最高网络层级为: {highest_tier}，相关节点: {', '.join(tier_map[highest_tier])}"]
    
    # 如果核心层存在故障，强力排除下游
    if highest_tier in ["CORE", "SPINE"]:
        victims = tier_map.get("LEAF", []) + tier_map.get("ENDPOINT", [])
        if victims:
            result_lines.append(f"🚫 【强规则阻断】：由于上游 {highest_tier} 层存在故障，以下下游/端侧节点极大概率属于【爆炸半径受害者】：{', '.join(victims)}")
            result_lines.append(f"⚠️ 强制约束：禁止将上述下游节点判定为根因，服务器无法导致上游交换机底层 DOWN 或丢包！必须优先排查 {highest_tier} 节点！")
            
    return "【自动化事实2：拓扑与因果纠偏】\n" + "\n".join(result_lines)

# ==========================================
# 3. 注册暴露给主程序的执行器映射
# ==========================================
EXECUTORS = {
    "enforce_topology_causality": enforce_topology_causality
}