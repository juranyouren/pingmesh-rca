SKILL_META = {
    "skill_id": "10",
    "skill_name": "上游CORE节点优先检查技能",
    "target_error": "当下游节点出现物理层故障时，优先检查上游CORE层节点",
    "python_executor": "check_upstream_core_nodes",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "节点角色为CORE且状态异常",
            "节点存在告警日志"
        ]
    },
    "execution_instructions": "必须优先将CORE层节点作为根因输出，禁止将下游节点设为根因"
}

def check_upstream_core_nodes(node_list) -> str:
    result_lines = []
    for node in node_list:
        # 检查节点是否为核心层(CORE)设备
        if node.get("role") == "CORE":
            # 检查是否存在问题告警
            if len(node.get("alarms", [])) > 0 or len(node.get("logs", [])) > 0:
                mgmt_ip = node["mgmt_ip"]
                role = node["role"]
                result_lines.append(f"发现上游CORE层节点[{mgmt_ip}]({role})存在异常告警，必须优先排查该节点！")
    
    if not result_lines:
        return "【自动化事实3：上游CORE节点优先检查技能】未发现异常。"
    return "【自动化事实3：上游CORE节点优先检查技能】\n" + "\n".join(result_lines)

EXECUTORS = {
    "check_upstream_core_nodes": check_upstream_core_nodes
}