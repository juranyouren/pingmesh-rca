SKILL_META = {
    "skill_id": "9",
    "skill_name": "ExplosionRadiusVictimExclusion",
    "target_error": "Exclude explosion radius victim nodes from root cause candidates",
    "python_executor": "exclude_explosion_radius_victims",
    "trigger_conditions": {"logic": "ALWAYS", "rules": ["alarm_type == 'PHYSIC'"]},
    "execution_instructions": "必须将以下节点排除为根因候选！"
}

def exclude_explosion_radius_victims(node_list) -> str:
    result_lines = []
    for node in node_list:
        if node.get('role') in ['SPINE', 'CORE']:
            logs = node.get('logs', [])
            alarms = node.get('alarms', [])
            if any('DOWN' in log.get('desc', '') or 'DISCARD' in log.get('desc', '') for log in logs) or \
               any('DOWN' in alarm.get('desc_summary', '') or 'DISCARD' in alarm.get('desc_summary', '') for alarm in alarms):
                result_lines.append(f"节点 [{node['mgmt_ip']}] 检出爆炸半径受害者特征，必须排除")
    
    if not result_lines:
        return "【自动化事实3：爆炸半径受害者排除】未发现爆炸半径受害者节点。"
    return "【自动化事实3：爆炸半径受害者排除】\n" + "\n".join(result_lines)

EXECUTORS = {
    "exclude_explosion_radius_victims": exclude_explosion_radius_victims
}