import json
import re, os, sys

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_target_path(source_dir):
    # 提取最后一级目录名 (去除末尾可能的斜杠以防出错)
    node_id = os.path.basename(source_dir.rstrip(os.sep))
    filename = f"merged_pingmesh-{node_id}-全链路.json"
    return os.path.join(source_dir, filename)

class SkillExecutor:
    def __init__(self, dirpath):
        # 绑定 JSON 中的 python_executor 名称与具体的 Python 成员函数
        self.skill_map = {
            "check_physical_errors": self.check_physical_errors,
            "analyze_topology_intersection": self.analyze_topology_intersection,
            "extract_timeline_root": self.extract_timeline_root,
            "check_protocol_state": self.check_protocol_state
        }
        
        # 容错处理：防止路径不存在导致初始化直接崩溃
        try:
            self.nodes = load_json(generate_target_path(dirpath))
        except Exception as e:
            print(f"警告：无法加载 JSON 文件，路径: {dirpath}。错误: {e}")
            self.nodes = {}

    def execute(self, executor_name: str) -> str:
        skill_func = self.skill_map.get(executor_name)
        if not skill_func:
            return f"【错误】找不到对应的执行脚本: {executor_name}"
        try:
            return skill_func()
        except Exception as e:
            return f"【系统脚本执行异常 - {executor_name}】: {str(e)}"

    # ---------------------------------------------------------
    # 辅助工具：统一节点列表提取
    # ---------------------------------------------------------
    def _get_node_list(self):
        if isinstance(self.nodes, list):
            return self.nodes
        elif isinstance(self.nodes, dict):
            return list(self.nodes.values())
        return []

    # ---------------------------------------------------------
    # Skill 1: 物理层与链路故障精确扫描
    # ---------------------------------------------------------
    def check_physical_errors(self) -> str:
        faults = []
        # 定义物理层致命错误关键字 (根据提供的 JSON 追加丢包关键字)
        physical_keywords = ["CRC", "DOWN", "R_LOS", "OTUCN_LOF", "光模块异常", "硬件故障", "PACKET_DROP", "DISCARD"]
        
        for n in self._get_node_list():
            # 使用 mgmt_ip 替代 name
            node_ip = n.get("mgmt_ip", "Unknown_IP")
            logs = n.get("logs", []) + n.get("alarms", [])
            
            node_faults = set()
            for log in logs:
                log_text = str(log).upper()
                for kw in physical_keywords:
                    if kw.upper() in log_text:
                        node_faults.add(kw)
            
            if node_faults:
                faults.append(f"- 节点 [{node_ip}] 检出底层故障关键字: {', '.join(node_faults)}")
                
        if faults:
            return "【自动化事实1：物理层检查】\n" + "\n".join(faults)
        return "【自动化事实1：物理层检查】未发现明确的 CRC/DOWN 等底层物理硬件报错。"

    # ---------------------------------------------------------
    # Skill 2: 拓扑汇聚点与关键节点(CORE/SPINE)定位
    # ---------------------------------------------------------
    def analyze_topology_intersection(self) -> str:
        result_lines = []
        critical_nodes_with_alerts = []
        upstream_counts = {}
        
        for n in self._get_node_list():
            # 提取角色和管理IP
            role = str(n.get("role", "")).upper()
            node_ip = n.get("mgmt_ip", "Unknown_IP")
            has_issues = bool(n.get("alarms") or n.get("logs"))
            
            # 1. 检查是否存在关键节点告警 (基于 role 字段)
            if ("SPINE" in role or "CORE" in role or "DSW" in role) and has_issues:
                critical_nodes_with_alerts.append(node_ip)
                
            # 2. 简易拓扑汇聚分析
            if has_issues:
                links = n.get("linked_to", [])
                for link in links:
                    upstream_counts[link] = upstream_counts.get(link, 0) + 1
        
        if critical_nodes_with_alerts:
            result_lines.append(f"警告：发现核心网络枢纽节点(SPINE/CORE)存在告警，极大可能为爆炸半径源头：{', '.join(critical_nodes_with_alerts)}")
                
        if upstream_counts:
            # 找到被指向最多的上游设备
            max_hits = max(upstream_counts.values())
            if max_hits > 1:
                common_upstreams = [k for k, v in upstream_counts.items() if v == max_hits]
                result_lines.append(f"拓扑计算事实：多个告警节点在拓扑上共同汇聚于上游设备: {', '.join(common_upstreams)} (汇聚度: {max_hits})。请重点排查这些汇聚节点。")
                
        if not result_lines:
            return "【自动化事实2：拓扑分析】未发现明显的关键核心节点告警或共同上游汇聚特征。"
            
        return "【自动化事实2：拓扑分析】\n" + "\n".join(result_lines)

    # ---------------------------------------------------------
    # Skill 3: 告警时间序列绝对排序 (提取最早告警)
    # ---------------------------------------------------------
    def extract_timeline_root(self) -> str:
        all_events = []
        
        for n in self._get_node_list():
            # 使用 mgmt_ip 替代 name
            node_ip = n.get("mgmt_ip", "Unknown_IP")
            
            for evt in n.get("alarms", []) + n.get("logs", []):
                if isinstance(evt, dict):
                    # 兼容不同日志格式的时间戳字段
                    timestamp = evt.get("alarm_time") or evt.get("time") 
                    if timestamp is not None:
                        # 优先取格式化时间，便于人类阅读；优先取 description 作为内容
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
            
        # 按照绝对时间戳排序
        all_events.sort(key=lambda x: x["time_ms"])
        
        # 提取最早的 3 条告警
        first_events = all_events[:3]
        result_lines = [f"- [{e['time_str']}] {e['node']}:\n  日志详情: {e['content']}" for e in first_events]
        
        return "【自动化事实3：时间序列 (风暴源头探测)】\n全局时间轴上最早发生的前 3 条事件（首因嫌疑极大）：\n" + "\n".join(result_lines)

    # ---------------------------------------------------------
    # Skill 4: 协议层(BGP/OSPF)断连精准匹配
    # ---------------------------------------------------------
    def check_protocol_state(self) -> str:
        protocol_issues = []
        protocol_keywords = ["BGP", "OSPF", "VRRP", "邻居断开", "STATE CHANGE"]
        
        for n in self._get_node_list():
            # 使用 mgmt_ip 替代 name
            node_ip = n.get("mgmt_ip", "Unknown_IP")
            
            for log in n.get("logs", []) + n.get("alarms", []):
                log_str = str(log).upper()
                if any(kw in log_str for kw in protocol_keywords):
                    # 提取具体的描述信息而不是一长串JSON格式
                    desc = log.get("alarm_description", str(log)) if isinstance(log, dict) else log
                    protocol_issues.append(f"- [{node_ip}] 协议状态异常: {desc}")
                    
        if protocol_issues:
            return "【自动化事实4：路由与协议层状态】\n" + "\n".join(protocol_issues)
        return "【自动化事实4：路由与协议层状态】未发现 BGP/OSPF 等协议层状态变更日志。"