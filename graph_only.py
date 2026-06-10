import os
import json
import time
try:
    import networkx as nx
except ImportError:
    print("请先执行: pip install networkx")
    nx = None

def run_pure_graph_algorithm(node_list: list, infodta: dict, weight_dirpath="/home/sbp/lixinyang/pingmesh/data/weights/classified_alarms/all_alarms.json") -> list:
    """
    纯图算法：直接返回按综合嫌疑度排序的 IP 列表 (List[str])
    """
    if nx is None: return []
    
    # 1. 加载告警权重字典
    default_weights = {
        "stachg_todwn": 100,
        "trunkdown": 100,
        "vlan接口down(dcn)": 100
    }
    if os.path.exists(weight_dirpath):
        try:
            with open(weight_dirpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    if "alarm_name" in item and "alarm_priority" in item:
                        default_weights[str(item["alarm_name"]).lower()] = int(item["alarm_priority"])
        except Exception:
            pass

    # 2. 解析源和目的 IP
    source_ips, sink_ips = [], []
    if infodta and isinstance(infodta, dict):
        try:
            src_val = infodta.get("source_ip", "[]")
            snk_val = infodta.get("sink_ip", "[]")
            source_ips = json.loads(src_val) if isinstance(src_val, str) else src_val
            sink_ips = json.loads(snk_val) if isinstance(snk_val, str) else snk_val
            if not isinstance(source_ips, list): source_ips = []
            if not isinstance(sink_ips, list): sink_ips = []
        except Exception:
            pass

    # 3. 构建无向图与计算初始得分
    G = nx.Graph()
    personalization = {}

    for node in node_list:
        ip = node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))
        if ip == "unknown": continue
            
        G.add_node(ip, role=node.get("role", "UNKNOWN"))
        
        for neighbor in node.get("linked_to", []) + node.get("linked_from", []):
            G.add_edge(ip, neighbor)
            
        try: cross_count = int(node.get("cross", 0))
        except: cross_count = 0

        max_weight = 0
        all_events = node.get("alarms", []) + node.get("logs", [])
        for event in all_events:
            name = event if isinstance(event, str) else event.get("alarm_name", event.get("name", ""))
            if not name: continue
            
            name_lower = str(name).lower()
            if name_lower in default_weights:
                weight = default_weights[name_lower]
                if weight > max_weight: max_weight = weight
        
        entity_score = 0.0
        if max_weight > 0:
            entity_score += float(max_weight)
        elif node.get("alarms"):
            entity_score += len(node.get("alarms")) * 2.0
        elif node.get("logs"):
            entity_score += 0.5
            
        # 交叉点放大机制
        if entity_score > 0 and cross_count > 0:
            entity_score += entity_score * cross_count * 0.5
            
        initial_score = 0.1 + entity_score
        
        if ip in source_ips or ip in sink_ips:
            initial_score += 0.5
            
        personalization[ip] = initial_score

    if len(G.nodes) == 0: return []

    for n in G.nodes:
        if n not in personalization:
            personalization[n] = 0.1

    # 4. 执行图收敛
    try:
        rwr_scores = nx.pagerank(G, alpha=0.85, personalization=personalization)
    except Exception:
        return []

    # 5. 返回排序后的纯 IP 列表
    sorted_nodes = sorted(rwr_scores.items(), key=lambda x: x[1], reverse=True)
    return [ip for ip, score in sorted_nodes]

def run_ablation_experiment(root_path: str, output_dir: str):
    """
    遍历数据集，兼容全链路动态文件名，只跑图算法
    """
    print(f"🚀 开始执行纯图算法消融实验，扫描目录: {root_path}")
    start_time = time.time()
    
    results = []
    case_count = 0
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        node_file = None
        info_file = None
        
        # 动态识别 node 数据文件和 info 数据文件
        for f in filenames:
            if f == "info.json":
                info_file = f
            # 兼容你提到的 merged_pingmesh-xxx-全链路.json 或老版本的 nodes.json
            elif ("pingmesh" in f and "全链路.json" in f):
                node_file = f
                
        # 只要同时找到了节点数据和告警 info，就执行诊断
        if node_file and info_file:
            node_path = os.path.join(dirpath, node_file)
            info_path = os.path.join(dirpath, info_file)
            
            try:
                # 读取并解析数据
                nodes_raw = json.load(open(node_path, 'r', encoding='utf-8'))
                # 如果最外层是 dict，取 values；如果是 list，直接用
                node_list = list(nodes_raw.values()) if isinstance(nodes_raw, dict) else nodes_raw
                info_data = json.load(open(info_path, 'r', encoding='utf-8'))
                
                # 核心：纯图算法推理！没有任何大模型参与！
                top_ips = run_pure_graph_algorithm(node_list, info_data)
                
                # 取前 5 个 IP 作为预测结果
                predicted_ips = top_ips[:5]
                
                # 伪造大模型的输出格式
                mock_json_response = {
                    "reasoning": "纯图算法 (RWR + Alarm Weights) 推导，无大模型干预。",
                    "ip": predicted_ips,
                    "propagation_path": {} 
                }
                mock_response_str = f"```json\n{json.dumps(mock_json_response, ensure_ascii=False, indent=2)}\n```"
                
                results.append({
                    "dir": dirpath,
                    "prompt": "GRAPH_ONLY_ABLATION_EXPERIMENT",
                    "draft_response": mock_response_str, 
                    "response": mock_response_str        
                })
                
                case_count += 1
                
            except Exception as e:
                print(f"[Error] 处理目录 {dirpath} 失败: {e}")

    # 保存伪造的 res.json
    os.makedirs(output_dir, exist_ok=True)
    res_file = os.path.join(output_dir, "res.json")
    with open(res_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
        
    print(f"✅ 纯图算法推理完成！共处理 {case_count} 个 Case，耗时: {time.time() - start_time:.2f} 秒")
    print(f"📂 实验结果已保存至: {res_file}")
    
    return res_file

if __name__ == "__main__":
    # 1. 配置路径
    DATA_ROOT = "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"
    timenow = int(time.time())
    OUTPUT_DIR = f"/home/sbp/lixinyang/pingmesh/data/res/graph_only_{timenow}"
    
    # 2. 运行纯图算法实验并生成 res.json
    res_file_path = run_ablation_experiment(DATA_ROOT, OUTPUT_DIR)
    
