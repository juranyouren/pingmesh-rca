SKILL_META = {
    "skill_id": "4",
    "skill_name": "协议层(BGP/OSPF)断连精准匹配",
    "target_error": "未能正确关联协议层告警与业务中断",
    "python_executor": "check_protocol_state",
    "trigger_conditions": {
      "logic": "OR",
      "rules": ["存在跨域网络问题", "日志中提及路由、邻居、BGP等字眼"]
    },
    "execution_instructions": "执行 Python 脚本，定向检索 BGP 邻居状态变化、OSPF 邻居丢失等协议层关键事件，并输出中断的具体协议对端 IP。"
}

def check_protocol_state(node_list) -> str:
    protocol_issues = []
    protocol_keywords = ["BGP", "OSPF", "VRRP", "邻居断开", "STATE CHANGE"]
    
    for n in node_list:
        node_ip = n.get("mgmt_ip", "Unknown_IP")
        
        for log in n.get("logs", []) + n.get("alarms", []):
            log_str = str(log).upper()
            if any(kw in log_str for kw in protocol_keywords):
                desc = log.get("alarm_description", str(log)) if isinstance(log, dict) else log
                protocol_issues.append(f"- [{node_ip}] 协议状态异常: {desc}")
                
    if protocol_issues:
        return "【自动化事实4：路由与协议层状态】\n" + "\n".join(protocol_issues)
    return "【自动化事实4：路由与协议层状态】未发现 BGP/OSPF 等协议层状态变更日志。"

EXECUTORS = {
    "check_protocol_state": check_protocol_state
}