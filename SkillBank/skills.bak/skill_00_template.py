# skills/skill_00_template.py

# ==========================================
# 1. 技能元数据配置 (喂给大语言模型看的 JSON)
# ==========================================
SKILL_META = {
    "skill_id": "0",  # 技能编号，用于排序
    "skill_name": "模板技能示例",
    "target_error": "描述大模型容易犯的错，说明为什么需要这个技能",
    "python_executor": "template_skill_function", # 必须与下方执行函数的名称严格一致
    "trigger_conditions": {
      "logic": "OR",
      "rules": ["触发条件1", "触发条件2"]
    },
    "execution_instructions": "用强烈的语气告诉大模型，执行这个脚本后必须怎么做。"
}

# ==========================================
# 2. 具体的 Python 执行逻辑 (硬规则计算)
# ==========================================
def template_skill_function(node_list) -> str:
    """
    入参 node_list: 经过统一处理的节点字典列表列表 (List[Dict])
    出参 str: 带有强引导语气的【自动化事实】字符串
    """
    result_lines = []
    
    for n in node_list:
        node_ip = n.get("mgmt_ip", "Unknown_IP")
        role = str(n.get("role", "")).upper()
        
        # --- 在这里编写你的判定逻辑 ---
        # if 满足某种条件:
        #     result_lines.append(f"- 发现异常: {node_ip}")
        pass
        
    if not result_lines:
        return "【自动化事实0：模板检查】未发现相关异常。"
        
    return "【自动化事实0：模板检查】\n" + "\n".join(result_lines)

# ==========================================
# 3. 注册暴露给主程序的执行器映射
# ==========================================
EXECUTORS = {
    "template_skill_function": template_skill_function
}