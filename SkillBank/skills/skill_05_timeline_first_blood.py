# skills/skill_05_timeline_first_blood.py

import time
from datetime import datetime

# ==========================================
# 1. 技能元数据配置 (喂给大语言模型看的 JSON)
# ==========================================
SKILL_META = {
    "skill_id": "5",
    "skill_name": "核心故障时间序列提取 (First-Blood)",
    "target_error": "因果关系误判，被常规日志锚定或将结果告警误认为根源",
    "python_executor": "extract_timeline_root",
    "trigger_conditions": {
        "logic": "ALWAYS",
        "rules": []
    },
    "execution_instructions": "请严格按照以下提取出的 Top 3 最早异常事件的时间顺序来推导故障传播路径（Propagation Path）。切忌使用拓扑层级（如核心到边缘）来主观臆断因果，必须遵循时间先后的客观事实。"
}

# ==========================================
# 2. 具体的 Python 执行逻辑 (硬规则计算)
# ==========================================
def extract_timeline_root(node_list) -> str:
    """
    入参 node_list: 经过统一处理的节点字典列表 (List[Dict])
    出参 str: 带有强引导语气的【自动化事实】字符串
    """
    all_events = []
    
    # 定义需要过滤的噪音关键词（转小写），过滤掉正常的用户行为、探测和心跳日志
    # 注意：包含了拼写错误的 "sucess" 以兼容原日志
    NOISE_KEYWORDS = [
        "sucess", "success", "log_out", "logged out", 
        "login", "succeeded", "grpc", "telemetry_probe"
    ]
    
    def parse_timestamp(evt_dict):
        """统一解析时间戳，返回毫秒级整数以供精确排序"""
        # 1. 尝试直接获取数字格式的 ms 时间戳
        ts = evt_dict.get("alarm_time")
        if isinstance(ts, (int, float)) and ts > 0:
            return int(ts)
            
        # 2. 尝试解析字符串格式的时间
        time_str = evt_dict.get("time") or evt_dict.get("alarm_time_str")
        if time_str and isinstance(time_str, str):
            try:
                # 兼容格式如 "2025/10/30 21:18:19" 或 "2025-10-31 00:07:11.477"
                time_str_clean = time_str.replace("-", "/").split(".")[0] 
                dt_obj = datetime.strptime(time_str_clean, "%Y/%m/%d %H:%M:%S")
                return int(dt_obj.timestamp() * 1000)
            except ValueError:
                pass
        return float('inf') # 解析失败的放到最后

    for n in node_list:
        # 兼容不同的数据结构封包
        node = n.get("node", n) if isinstance(n, dict) else n
        ip = node.get("mgmt_ip", "Unknown_IP")
        
        events = node.get("alarms", []) + node.get("logs", [])
        
        for evt in events:
            if isinstance(evt, dict):
                content = evt.get("desc_summary", evt.get("desc", evt.get("name", str(evt))))
                content_lower = content.lower()
                
                # 【关键增强】：跳过包含噪音关键词的正常事件
                if any(noise in content_lower for noise in NOISE_KEYWORDS):
                    continue
                    
                time_ms = parse_timestamp(evt)
                
                # 只收集解析出有效时间的事件
                if time_ms != float('inf'):
                    time_display = evt.get("time") or evt.get("alarm_time_str") or str(time_ms)
                    all_events.append({
                        "node": ip,
                        "time_ms": time_ms,
                        "time_str": time_display,
                        "content": content
                    })
            
    if not all_events:
        return "【自动化事实5：时间序列】已过滤常规探测与登录日志，未提取到带明确时间戳的异常告警事件。"
        
    # 按绝对时间戳升序排序 (找 First-Blood)
    all_events.sort(key=lambda x: x["time_ms"])
    
    # 提取排重后的前 3 条核心事件（防止同一秒内同一设备的重复报错霸占槽位）
    first_events = []
    seen = set()
    for e in all_events:
        unique_key = f"{e['node']}_{e['content']}"
        if unique_key not in seen:
            seen.add(unique_key)
            first_events.append(e)
        if len(first_events) >= 3:
            break
    
    result_lines = [f"- [{e['time_str']}] {e['node']}: {e['content']}" for e in first_events]
    return "【自动化事实5：异常时间序列 (First-Blood 探测)】\n(已滤除 GRPC/Login 等常规交互日志)\n全局时间轴上最早发生的前 3 条核心异常事件：\n" + "\n".join(result_lines)

# ==========================================
# 3. 注册暴露给主程序的执行器映射
# ==========================================
EXECUTORS = {
    "extract_timeline_root": extract_timeline_root
}