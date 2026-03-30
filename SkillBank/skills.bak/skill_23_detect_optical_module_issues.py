SKILL_META = {
    "skill_id": "23",
    "skill_name": "光模块异常检测",
    "target_error": "纠正大模型对物理层光模块异常导致的误判",
    "python_executor": "detect_optical_module_issues",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "node['logs'] contains 'Optical module exception'",
            "node['logs'] contains 'Optical Module is invalid'"
        ]
    },
    "execution_instructions": "必须将检测到的异常设备作为首要排查对象，并优先考虑光模块更换或温度调节方案"
}

def detect_optical_module_issues(node_list) -> str:
    result_lines = []
    for node in node_list:
        logs = node.get('logs', [])
        for log in logs:
            desc = log.get('desc', '')
            if "Optical module exception" in desc or "Optical Module is invalid" in desc:
                result_lines.append(f"- 节点 [{node['mgmt_ip']}] 检出光模块异常: {log['desc']}")
    
    if not result_lines:
        return "【自动化事实X：光模块异常检测】未发现异常。"
    return "【自动化事实X：光模块异常检测】强烈建议将以下节点作为首要排查对象：" + "\n".join(result_lines)

EXECUTORS = {
    "detect_optical_module_issues": detect_optical_module_issues
}