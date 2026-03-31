SKILL_META = {
    "skill_id": "6",
    "skill_name": "设备IP排序校验",
    "target_error": "网络故障场景中设备IP排序错误",
    "python_executor": "validate_node_order",
    "trigger_conditions": {"logic": "ALWAYS", "rules": []},
    "execution_instructions": "必须严格按照设备嫌疑程度对IP地址进行排序，并确保propagation_path字段完整"
}

def validate_node_order(node_list) -> str:
    result_lines = []
    nodes_with_path = [node for node in node_list if "propagation_path" in node]
    
    # 检查每个节点的propagation_path字段完整性
    for node in node_list:
        if "propagation_path" not in node:
            result_lines.append(f"节点缺少propagation_path字段：{node}")
        else:
            for path_item in node["propagation_path"]:
                if "device_ip" not in path_item or "suspect_level" not in path_item:
                    result_lines.append(f"节点propagation_path字段不完整：{node}")

    # 检查排序逻辑
    if len(nodes_with_path) > 1:
        try:
            sorted_nodes = sorted(nodes_with_path, key=lambda x: x["propagation_path"][0]["suspect_level"], reverse=True)
            if sorted_nodes != node_list:
                result_lines.append("设备IP排序错误，必须按嫌疑程度降序排列")
        except (KeyError, TypeError):
            result_lines.append("无法按嫌疑程度排序，请检查设备IP数据")

    if not result_lines:
        return "【自动化事实X：设备IP排序校验】未发现异常。"
    return f"【自动化事实X：设备IP排序校验】" + "\n".join(result_lines)

EXECUTORS = {
    "validate_node_order": validate_node_order
}