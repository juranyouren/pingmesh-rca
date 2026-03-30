SKILL_META = {
    "skill_id": "12",
    "skill_name": "下联LEAF节点链路异常检测",
    "target_error": "大模型错误地将网络故障原因归因于汇聚节点而非下联LEAF节点的情况",
    "python_executor": "detect_leaf_link_issues",
    "trigger_conditions": {
        "logic": "OR",
        "rules": [
            "node.role == 'LEAF' AND ('DISCARD' in log.desc OR 'DOWN' in log.desc)"
        ]
    },
    "execution_instructions": "必须将这些LEAF节点的链路异常作为最高优先级考虑，重新评估根因设备"
}

def detect_leaf_link_issues(node_list) -> str:
    leaf_issues = []
    for node in node_list:
        if node.get('role') == 'LEAF':
            for log in node.get('logs', []):
                if 'DISCARD' in log.get('desc', '') or 'DOWN' in log.get('desc', ''):
                    leaf_issues.append(f"节点 [{node['mgmt_ip']}] 检出底层故障关键字: DISCARD, DOWN")
                    break
    
    if not leaf_issues:
        return "【自动化事实X：下联LEAF节点链路异常检测】未发现异常。"
    
    return "【自动化事实X：下联LEAF节点链路异常检测】\n" + "\n".join(leaf_issues)

EXECUTORS = {
    "detect_leaf_link_issues": detect_leaf_link_issues
}