SKILL_META = {
    "skill_id": "24",
    "skill_name": "核心层日志溢出检测",
    "target_error": "误将下游叶子节点判断为根因，而忽略核心层日志溢出问题",
    "python_executor": "core_log_overflow_detection",
    "trigger_conditions": {"logic": "ALWAYS", "rules": []},
    "execution_instructions": "必须将检测到日志溢出的核心节点列为最高嫌疑，并优先进行故障排查！"
}

def core_log_overflow_detection(node_list) -> str:
    result_lines = []
    for node in node_list:
        if node.get("role") == "CORE":
            for log in node.get("logs", []):
                if "logfile number is more than 90 percent" in log.get("desc", "").lower():
                    result_lines.append(f"检测到核心节点 [{node['mgmt_ip']}] 存在严重日志溢出问题！")
    if not result_lines:
        return "【自动化事实4：核心层日志溢出检测】未发现核心节点的日志溢出问题。"
    return "【自动化事实4：核心层日志溢出检测】\n" + "\n".join(result_lines)

EXECUTORS = {
    "core_log_overflow_detection": core_log_overflow_detection
}