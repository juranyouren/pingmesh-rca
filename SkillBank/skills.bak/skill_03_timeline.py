SKILL_META = {
    "skill_id": "3",
    "skill_name": "告警时间序列绝对排序 (找First-Blood)",
    "target_error": "因果关系误判，将结果告警（风暴）误认为根源告警",
    "python_executor": "extract_timeline_root",
    "trigger_conditions": {
      "logic": "ALWAYS",
      "rules": []
    },
    "execution_instructions": "执行 Python 时间戳排序脚本，将所有设备的日志和告警按毫秒级/秒级时间线进行全局排序，精准提取出网络风暴发生前的‘第一条告警（First-Blood）’。"
}

def extract_timeline_root(node_list) -> str:
    all_events = []
    
    for n in node_list:
        node_ip = n.get("mgmt_ip", "Unknown_IP")
        
        for evt in n.get("alarms", []) + n.get("logs", []):
            if isinstance(evt, dict):
                timestamp = evt.get("alarm_time") or evt.get("time") 
                if timestamp is not None:
                    time_str = evt.get("alarm_time_str", str(timestamp))
                    content = evt.get("alarm_description") or evt.get("alarm_name") or str(evt)
                    all_events.append({
                        "node": node_ip,
                        "time_ms": timestamp,
                        "time_str": time_str,
                        "content": content
                    })
            
    if not all_events:
        return "【自动化事实3：时间序列】未提取到带明确时间戳的告警事件。"
        
    all_events.sort(key=lambda x: x["time_ms"])
    first_events = all_events[:3]
    result_lines = [f"- [{e['time_str']}] {e['node']}:\n  日志详情: {e['content']}" for e in first_events]
    
    return "【自动化事实3：时间序列 (风暴源头探测)】\n全局时间轴上最早发生的前 3 条事件（首因嫌疑极大）：\n" + "\n".join(result_lines)

EXECUTORS = {
    "extract_timeline_root": extract_timeline_root
}