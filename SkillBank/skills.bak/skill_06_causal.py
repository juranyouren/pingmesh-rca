SKILL_META = {
    "skill_id": "6",
    "skill_name": "设备角色与因果倒置纠偏",
    "target_error": "大模型在拓扑汇聚场景下，容易将受害端服务器（如OBS/VM等）的连带告警误判为导致上游网络设备（LEAF/TOR交换机）端口DOWN/DISCARD的根因。",
    "python_executor": "check_device_role_causality",
    "trigger_conditions": {
        "logic": "AND",
        "rules": [
            "告警链路中同时包含网络设备（DEVICE）和终端存储/计算节点（OBS/HOST/VM）",
            "网络设备存在底层链路/协议级异常日志（如 LACP, MSTP, DISCARD）"
        ]
    },
    "execution_instructions": "务必严格遵循网络基础设施因果律：物理网络设备（交换机/路由器）的底层链路阻断（如端口DISCARD、LACP失败），必然导致其下挂的终端服务器（OBS等）发生Pingmesh拨测失败或节点重启。当你看到本事实输出时，绝对不能将终端服务器判定为根因设备，它们仅仅是爆炸半径内的受害者（Impact）。请立即将最高嫌疑锁定在抛出底层日志的物理网络交换机上！"
}

def check_device_role_causality(node_list) -> str:
    faulty_network_devices = []
    victim_endpoints = []
    
    for node in node_list:
        ip = node.get("mgmt_ip", "Unknown_IP")
        node_type = str(node.get("type", "")).upper()
        role = str(node.get("role", "")).upper()
        node_sign = str(node.get("node_sign", "")).lower()
        
        logs_alarms_content = str(node.get("logs", [])) + str(node.get("alarms", []))
        
        # 判定是否为基础设施层网络设备
        is_network_infra = (node_type == "DEVICE") or (role in ["LEAF", "SPINE", "CORE", "TOR"])
        # 判定是否为端侧业务节点
        is_endpoint = (node_type in ["OBS", "VM", "HOST", "SERVER"]) or (node_sign == "target")
        
        if is_network_infra:
            # 检查底层协议或链路故障关键字
            fault_keywords = ["DISCARD", "LACP", "MSTP", "LLDP", "DOWN", "NEGOTIATEFAILED"]
            if any(keyword in logs_alarms_content.upper() for keyword in fault_keywords):
                faulty_network_devices.append(f"{ip}({role})")
                
        if is_endpoint:
            victim_endpoints.append(f"{ip}({node_type})")

    if not faulty_network_devices or not victim_endpoints:
        return "【自动化事实6：设备角色与因果倒置纠偏】未发现明显的网络设备与终端服务器混淆特征。"
        
    result_lines = [
        "🚨 【致命防错指令触发】：检测到网络基础设施与终端节点的因果倒置风险！",
        f"➡️ 确诊底层链路/协议故障的网络设备：{', '.join(faulty_network_devices)}",
        f"➡️ 确诊处于拓扑末端的受害节点：{', '.join(victim_endpoints)}",
        "🛑 强制约束：严禁将上述受害节点（OBS等业务端）列为根因！服务器无法导致上游交换机端口进入DISCARD或LACP失败状态。必须将根因锁定在上述网络设备，并将服务器的异常归类为传播路径受影响的结果（Impact）。"
    ]
    
    return "【自动化事实6：设备角色与因果倒置纠偏】\n" + "\n".join(result_lines)

EXECUTORS = {
    "check_device_role_causality": check_device_role_causality
}