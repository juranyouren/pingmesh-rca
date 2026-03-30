SKILL_META = {
    "skill_id": "8",
    "skill_name": "Core OSPF LSA Age Detection",
    "target_error": "Misdiagnosis of downstream nodes as root cause when upstream CORE layer has OSPF issues",
    "python_executor": "detect_core_ospf_issues",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "node.role == 'CORE'",
            "log.name == 'ospfMaxAgeLsa'"
        ]
    },
    "execution_instructions": "Must prioritize these CORE nodes as root cause candidates and exclude downstream nodes from consideration"
}

def detect_core_ospf_issues(node_list) -> str:
    core_nodes = []
    for node in node_list:
        if node.get('role') == 'CORE':
            for log in node.get('logs', []):
                if log.get('name') == 'ospfMaxAgeLsa':
                    core_nodes.append(node['mgmt_ip'])
                    break
    
    if not core_nodes:
        return "【自动化事实X：Core OSPF LSA Age Detection】未发现CORE层节点存在OSPF LSA老化问题。"
    
    result_lines = [
        f"强烈建议将CORE层节点 {', '.join(core_nodes)} 作为首要怀疑对象。",
        "这些节点的OSPFLSA老化问题可能是网络异常的根本原因。",
        "必须将其列为最高嫌疑，禁止将下游节点列为根因！"
    ]
    
    return "【自动化事实X：Core OSPF LSA Age Detection】\n" + "\n".join(result_lines)

EXECUTORS = {
    "detect_core_ospf_issues": detect_core_ospf_issues
}