# skills/skill_05_timeline_first_blood.py

# ==========================================
# 1. 技能元数据配置 (喂给大语言模型看的 JSON)
# ==========================================
SKILL_META = {
    "skill_id": "5",
    "skill_name": "告警时间序列绝对排序 (找First-Blood)",
    "target_error": "因果关系误判，将结果告警（风暴）误认为根源告警",
    "python_executor": "extract_timeline_root",
    "trigger_conditions": {
        "logic": "ALWAYS",
        "rules": []
    },
    "execution_instructions": "请重点参考时间戳最早的 Top 3 告警，这极有可能是雪崩效应的源头（First-Blood）。"
}

# ==========================================
# 2. 具体的 Python 执行逻辑 (硬规则计算)
# ==========================================
def extract_timeline_root(node_list) -> str:
    """
    入参 node_list: 经过统一处理的节点字典列表列表 (List[Dict])
    出参 str: 带有强引导语气的【自动化事实】字符串
    """
    all_events = []
    
    for n in node_list:
        node = n.get("node", n)
        ip = node.get("mgmt_ip", "Unknown_IP")
        
        for evt in node.get("alarms", []) + node.get("logs", []):
            if isinstance(evt, dict):
                timestamp = evt.get("alarm_time") or evt.get("time")
                if timestamp:
                    all_events.append({
                        "node": ip,
                        "time_ms": timestamp,
                        "time_str": evt.get("alarm_time_str", str(timestamp)),
                        "content": evt.get("desc_summary", evt.get("desc", evt.get("name", str(evt))))
                    })
            
    if not all_events:
        return "【自动化事实5：时间序列】未提取到带明确时间戳的告警事件。"
        
    # 按时间戳排序取前3条
    all_events.sort(key=lambda x: x["time_ms"])
    first_events = all_events[:3]
    
    result_lines = [f"- [{e['time_str']}] {e['node']}: {e['content']}" for e in first_events]
    return "【自动化事实5：时间序列 (First-Blood 探测)】\n全局时间轴上最早发生的前 3 条事件：\n" + "\n".join(result_lines)

# ==========================================
# 3. 注册暴露给主程序的执行器映射
# ==========================================
EXECUTORS = {
    "extract_timeline_root": extract_timeline_root
}