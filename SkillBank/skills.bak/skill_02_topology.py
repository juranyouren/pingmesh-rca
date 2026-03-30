SKILL_META = {
    "skill_id": "2",
    "skill_name": "拓扑汇聚点与关键节点(CORE/SPINE)定位",
    "target_error": "拓扑依赖关系解析错误，未能发现共同上游或忽视了核心交换机",
    "python_executor": "analyze_topology_intersection",
    "trigger_conditions": {
      "logic": "OR",
      "rules": ["存在多个节点(如Pod/CNA)同时上报告警"]
    },
    "execution_instructions": "执行 Python 拓扑遍历算法，找出所有告警叶子节点的共同上游设备。同时检索拓扑，若发现异常节点角色为 CORE 或 SPINE，进行高优标记。"
}

def analyze_topology_intersection(node_list) -> str:
    result_lines = []
    critical_nodes_with_alerts = []
    upstream_counts = {}
    
    for n in node_list:
        role = str(n.get("role", "")).upper()
        node_ip = n.get("mgmt_ip", "Unknown_IP")
        has_issues = bool(n.get("alarms") or n.get("logs"))
        
        if ("SPINE" in role or "CORE" in role or "DSW" in role) and has_issues:
            critical_nodes_with_alerts.append(node_ip)
            
        if has_issues:
            links = n.get("linked_to", [])
            for link in links:
                upstream_counts[link] = upstream_counts.get(link, 0) + 1
    
    if critical_nodes_with_alerts:
        result_lines.append(f"警告：发现核心网络枢纽节点(SPINE/CORE)存在告警，极大可能为爆炸半径源头：{', '.join(critical_nodes_with_alerts)}")
            
    if upstream_counts:
        max_hits = max(upstream_counts.values())
        if max_hits > 1:
            common_upstreams = [k for k, v in upstream_counts.items() if v == max_hits]
            result_lines.append(f"拓扑计算事实：多个告警节点在拓扑上共同汇聚于上游设备: {', '.join(common_upstreams)} (汇聚度: {max_hits})。请重点排查这些汇聚节点。")
            
    if not result_lines:
        return "【自动化事实2：拓扑分析】未发现明显的关键核心节点告警或共同上游汇聚特征。"
        
    return "【自动化事实2：拓扑分析】\n" + "\n".join(result_lines)

EXECUTORS = {
    "analyze_topology_intersection": analyze_topology_intersection
}