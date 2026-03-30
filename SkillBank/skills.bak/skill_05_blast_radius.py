SKILL_META = {
    "skill_id": "5",
    "skill_name": "拓扑层级与爆炸半径受害者过滤",
    "target_error": "颠倒故障传播的因果关系，将受下游网络汇聚影响的受害节点（或端侧源头拨测节点）误判为根因，忽视了上游核心设备。",
    "python_executor": "identify_blast_radius_root",
    "trigger_conditions": {
      "logic": "OR",
      "rules": ["拓扑中存在多个层级的设备告警", "Pingmesh出现大面积/多IP组告警"]
    },
    "execution_instructions": "执行 Python 脚本，按照数据中心网络拓扑层级 (CORE > SPINE > LEAF > POD) 严格评估告警权重。若扫描到上游核心设备存在告警，强制将下游节点(如汇聚点、拨测源IP)标记为‘受害者’，防止模型因果倒置。"
}

def identify_blast_radius_root(node_list) -> str:
    tier_map = {"CORE": [], "SPINE": [], "LEAF": [], "POD": [], "OTHER": []}
    
    for n in node_list:
        node_ip = n.get("mgmt_ip", "Unknown_IP")
        role = str(n.get("role", "")).upper()
        has_issues = bool(n.get("alarms") or n.get("logs"))
        
        if has_issues:
            if "CORE" in role or "DSW" in role:
                tier_map["CORE"].append(node_ip)
            elif "SPINE" in role:
                tier_map["SPINE"].append(node_ip)
            elif "LEAF" in role or "TOR" in role:
                tier_map["LEAF"].append(node_ip)
            elif "POD" in role or "SERVER" in role or "CNA" in role:
                tier_map["POD"].append(node_ip)
            else:
                tier_map["OTHER"].append(node_ip)
                
    result_lines = []
    highest_tier = None
    
    for tier in ["CORE", "SPINE", "LEAF", "POD"]:
        if tier_map[tier]:
            highest_tier = tier
            result_lines.append(f"📌 发现最高权重故障层级: {tier}，相关节点: {', '.join(tier_map[tier])}")
            break
            
    if highest_tier in ["CORE", "SPINE"]:
        victims = tier_map["LEAF"] + tier_map["POD"] + tier_map["OTHER"]
        if victims:
            result_lines.append(f"🚫 【强规则阻断】由于上游核心层 ({highest_tier}) 存在告警，以下下游节点 {', '.join(victims)} 极大概率属于【爆炸半径受害者】(例如路由被撤销、流量被动拥塞)！")
            result_lines.append(f"⚠️ 必须优先将最高权重层级 ({highest_tier}) 的节点作为根因输出，禁止将上述下游节点设为根因！")
            
    if not result_lines:
        return "【自动化事实5：层级与爆炸半径受害者过滤】未发现明确的跨层级故障传播。"
        
    return "【自动化事实5：层级与爆炸半径受害者过滤】\n" + "\n".join(result_lines)

EXECUTORS = {
    "identify_blast_radius_root": identify_blast_radius_root
}