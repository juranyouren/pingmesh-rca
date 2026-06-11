SKILL_META = {
    "skill_id": "2",
    "skill_name": "co_occurrence_alarm_check",
    "target_error": """模型有时无法区分海量告警中哪些是具有决定性意义的底层告警，且面对多个关联告警时容易产生单因谬误，导致漏报或误判。""",
    "python_executor": "co_occurrence_alarm_check",
    "trigger_conditions": {
        "logic": """当需要评估 Nodes 列表中各个节点的告警严重程度，以及识别全局是否存在特定的高危【告警组合】时触发。""",
        "rules": ["node_list 数据不为空"],
        "negative_rules": ["如果节点间发生的告警类型完全相同（无法通过权重区分），则不应该依赖此技能"]
    },
    "execution_instructions": """1. 读取告警权重文件，提取节点的最大优先级分数并输出 Top 5。2. 提取 Top 5 节点的全局告警集合，对比告警共现经验库，一旦命中特定组合，强制提取带有该组合告警的涉事节点（最多10个）并输出专家防坑警告。"""
}

import os
import json

def co_occurrence_alarm_check(
    node_list: list, 
    info: dict = {}, 
    dirpath="/home/sbp/lixinyang/pingmesh/data/weights/classified_alarms/all_alarms.json",
    co_occur_path="/home/sbp/lixinyang/pingmesh/SkillBank/alarm_co_occurrence_rules.json"  # 经验库路径
) -> str:
    
    # ================= 1. 计算节点告警权重 =================
    default_weights = {
        "stachg_todwn": 100,
        "trunkdown": 100,
        "vlan接口down(dcn)": 100
    }

    if os.path.exists(dirpath):
        try:
            with open(dirpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    if "alarm_name" in item and "alarm_priority" in item:
                        default_weights[str(item["alarm_name"]).lower()] = int(item["alarm_priority"])
        except Exception:
            pass

    node_results = []
    for node in node_list:
        node_ip = node.get("mgmt_ip", "Unknown_Node")
        all_events = node.get("alarms", []) + node.get("logs", [])
        
        max_weight = 0
        triggered_alarms = []

        for event in all_events:
            name = ""
            if isinstance(event, str):
                name = event
            elif isinstance(event, dict):
                name = event.get("alarm_name", event.get("name", ""))
            
            if not name: continue

            name_lower = str(name).lower()
            if name_lower in default_weights:
                weight = default_weights[name_lower]
                if weight > max_weight:
                    max_weight = weight
                if name not in triggered_alarms:
                    triggered_alarms.append(name)

        if max_weight > 0:
            node_results.append({
                "ip": node_ip,
                "weight": max_weight,
                "alarms_str": ", ".join(triggered_alarms),
                "raw_alarms": triggered_alarms  # 保留原始列表，供后面求交集使用
            })

    if not node_results:
        return "【自动化事实提取：节点权重诊断】未能从节点列表中提取出有效数据或未命中任何高优告警"

    # 全局按权重排序
    node_results.sort(key=lambda x: x["weight"], reverse=True)
    top_nodes = node_results[:5]

    # ================= 2. 核心新增：告警共现经验匹配与实体显化 =================
    # 提取 Top5 节点的全局告警集合
    global_triggered_alarms_lower = set()
    for item in top_nodes:
        for alarm_name in item["raw_alarms"]:
            global_triggered_alarms_lower.add(str(alarm_name).lower())

    warnings_to_inject = []
    
    if os.path.exists(co_occur_path):
        try:
            with open(co_occur_path, 'r', encoding='utf-8') as f:
                co_occur_rules = json.load(f)
                
            for rule in co_occur_rules:
                # 获取规则中的告警集合，并转为小写
                original_rule_alarms = rule.get("alarm_set", [])
                rule_alarm_set_lower = set([str(a).lower() for a in original_rule_alarms])
                
                # 如果命中组合技！
                if rule_alarm_set_lower and rule_alarm_set_lower.issubset(global_triggered_alarms_lower):
                    
                    # --- 改进点：提取含有这些告警的“涉事节点” ---
                    involved_nodes_info = []
                    for node in node_results: # 从全量排序好的 node_results 里找
                        node_alarms_lower = set([str(a).lower() for a in node["raw_alarms"]])
                        # 求交集：该节点是否包含该规则中的哪怕一个告警？
                        intersect = node_alarms_lower.intersection(rule_alarm_set_lower)
                        
                        if intersect:
                            # 找出该节点具体命中了规则中的哪些告警（恢复原始大小写便于展示）
                            matched_alarms = [a for a in original_rule_alarms if str(a).lower() in intersect]
                            involved_nodes_info.append(
                                f"    - [IP: {node['ip']}] (权重:{node['weight']}) 携带了: {matched_alarms}"
                            )
                    
                    # 截取前10个，防 Token 爆炸
                    involved_nodes_info = involved_nodes_info[:10]
                    involved_text = "\n  🎯 [涉嫌触发该组合的重点节点清单]:\n" + "\n".join(involved_nodes_info) + "\n"
                    # ----------------------------------------------

                    warnings_to_inject.append(
                        f"⚠️ 【专家指令 - {rule.get('rule_id')}】检测到高危组合爆发：{original_rule_alarms} \n"
                        f"{involved_text}"
                        f"👉 避坑指南: {rule.get('expert_warning')}"
                    )
        except Exception as e:
            pass # 读取规则库失败不阻断主流程

    # ================= 3. 组装终极 Prompt 文本 =================
    newline = chr(10)
    result_lines = [
        f"节点 {item['ip']} 匹配到权重告警 [{item['alarms_str']}]，最高权重为: {item['weight']}" 
        for item in top_nodes
    ]
    
    base_res = f"【自动化事实提取：节点权重诊断（Top 5 权重排序）】{newline}" + newline.join(result_lines)

    # 如果命中了共现规则，把警告及涉事节点名单拼接到末尾
    if warnings_to_inject:
        base_res += f"{newline}{newline}=================================================="
        base_res += f"{newline}🚨 【系统级高危告警组合拦截 (由历史错案反思生成)】 🚨"
        base_res += f"{newline}（说明：以下节点触发了历史惨痛教训，大模型必须严格遵守特权指令，否则会导致严重误判！）{newline}"
        base_res += f"{newline}".join(warnings_to_inject)
        base_res += f"=================================================="

    return base_res

EXECUTORS = {
    "co_occurrence_alarm_check": co_occurrence_alarm_check
}