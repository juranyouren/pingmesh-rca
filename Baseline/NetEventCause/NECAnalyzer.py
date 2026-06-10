import os
import json
import time
import math
import multiprocessing as mp
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed

def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

class NetEventCauseAnalyzer:
    def __init__(self, decay_rate=0.01, base_weight=1.0):
        """
        初始化时序点过程 (TPP) 基线分析器
        :param decay_rate: 霍克斯过程的时间衰减率 (beta)，值越大，越早发生的事件权重越低
        :param base_weight: 基础事件激发强度 (alpha)
        """
        self.decay_rate = decay_rate
        self.base_weight = base_weight

    def _parse_timestamp(self, time_str) -> float:
        """解析日志中的时间字符串为时间戳"""
        if not time_str:
            return 0.0
        try:
            # 兼容 "2025/10/27 19:36:08" 格式
            dt = datetime.strptime(str(time_str), "%Y/%m/%d %H:%M:%S")
            return dt.timestamp()
        except Exception:
            return 0.0

    def _extract_temporal_events(self, dirpath: str) -> tuple:
        """将 JSON 降维拍平为纯时间序列 [(timestamp, ip, event_name)]"""
        nodes_path = os.path.join(dirpath, "nodes.json")
        info_path = os.path.join(dirpath, "info.json")
        
        nodes_data = load_json(nodes_path) if os.path.exists(nodes_path) else {}
        info_data = load_json(info_path) if os.path.exists(info_path) else {}
        
        # 获取 Pingmesh 失败的目标时间 (Target Time)
        # 假设 info 中有 alarm_time 毫秒级时间戳，转为秒
        target_time = info_data.get("alarm_time", 0) / 1000.0  
        
        events_sequence = []
        node_list = list(nodes_data.values()) if isinstance(nodes_data, dict) else nodes_data
        
        for node in node_list:
            ip = node.get("mgmt_ip")
            if not ip: continue
            
            # 合并 alarms 和 logs
            all_events = node.get("alarms", []) + node.get("logs", [])
            for evt in all_events:
                if isinstance(evt, dict):
                    name = evt.get("name", evt.get("alarm_name", "UnknownEvent"))
                    # 尝试获取发生时间，如果没有则默认比 target_time 早 10 秒
                    evt_time = self._parse_timestamp(evt.get("time"))
                    if evt_time == 0.0 and target_time > 0:
                        evt_time = target_time - 10.0 
                        
                    events_sequence.append({
                        "time": evt_time,
                        "ip": ip,
                        "name": name
                    })
                    
        # 按时间发生顺序排序（模拟真实的告警事件流）
        events_sequence.sort(key=lambda x: x["time"])
        
        # 如果 target_time 提取失败，用最后一个事件的时间作为靶点时间
        if target_time == 0.0 and events_sequence:
            target_time = events_sequence[-1]["time"] + 1.0
            
        return events_sequence, target_time

    def _tpp_attribution(self, events_sequence: list, target_time: float) -> list:
        """
        核心逻辑：计算历史告警对最终 Pingmesh 故障的归因分数 (Attribution Score)
        采用类似 Hawkes Process 的指数衰减核函数
        """
        ip_scores = {}
        
        for evt in events_sequence:
            ip = evt["ip"]
            evt_time = evt["time"]
            
            # 计算时间差 (delta t)
            delta_t = target_time - evt_time
            if delta_t < 0: 
                delta_t = 0 # 忽略发生在报障后的事件
                
            # 霍克斯过程核函数： Intensity = alpha * exp(-beta * delta_t)
            intensity_score = self.base_weight * math.exp(-self.decay_rate * delta_t)
            
            if ip not in ip_scores:
                ip_scores[ip] = 0.0
            # 聚合该 IP 产生的所有历史事件的归因分数
            ip_scores[ip] += intensity_score
            
        # 排序并格式化输出
        ranked_ips = sorted(ip_scores.items(), key=lambda x: x[1], reverse=True)
        return ranked_ips

    def process_cases(self, dirpaths: list) -> list:
        """执行 NetEventCause 流水线"""
        results = []
        for dp in dirpaths:
            # 1. 降维：构建时间序列
            events_sequence, target_time = self._extract_temporal_events(dp)
            
            # 2. 归因：计算 TPP 分数
            ranked_ips_with_scores = self._tpp_attribution(events_sequence, target_time)
            
            # 3. 截断 Top 3
            top_ips = [ip for ip, score in ranked_ips_with_scores[:3]]
            
            # 伪装成大模型标准 JSON 输出
            
            fake_llm_response=f"""
            NetEventCause Baseline: 基于时间点过程 (Temporal Point Process) 与指数衰减核函数进行归因。无拓扑数据输入，纯依赖事件发生的时间紧凑度与频次。
            ```json
            {{
                "ip":{top_ips}
            }}
            ```
            """
            results.append({
                "dir": dp,
                "prompt": "TRACE_RCA_BASELINE_NO_PROMPT",
                "draft_response": fake_llm_response
            })
            
        return results

def generate_prompts(root_path: str) -> list:
    """扫描测试集"""
    dirpath_list = []
    print(f"开始扫描目录 {root_path} ...")
    for dirpath, dirnames, filenames in os.walk(root_path):
        if "nodes.json" in filenames and "info.json" in filenames:
            dirpath_list.append(dirpath)
    return dirpath_list

def worker_process(dirpaths_chunk: list) -> list:
    """纯 CPU 计算进程"""
    analyzer = NetEventCauseAnalyzer(decay_rate=0.05) # 衰减率可调
    return analyzer.process_cases(dirpaths_chunk)

def distribute_inference_tasks(dirpath_list: list) -> list:
    num_instances = min(mp.cpu_count(), 32)
    print(f"检测到纯 CPU TPP 计算任务，启动 {num_instances} 个并行实例。")

    chunk_size = math.ceil(len(dirpath_list) / num_instances)
    dir_chunks = [dirpath_list[i:i + chunk_size] for i in range(0, len(dirpath_list), chunk_size)]
    
    all_results = []
    ctx = mp.get_context('spawn')
    
    with ProcessPoolExecutor(max_workers=num_instances, mp_context=ctx) as executor:
        futures = [executor.submit(worker_process, chunk) for chunk in dir_chunks if chunk]
        for future in as_completed(futures):
            all_results.extend(future.result())

    return all_results

if __name__ == "__main__":
    # 指向你的测试集目录
    ROOT_PATH = "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"
    
    dirpaths = generate_prompts(ROOT_PATH)
    
    if dirpaths:
        print(f"共发现 {len(dirpaths)} 个 Case 任务，开始执行 NetEventCause 时序基线...")
        
        start_time = time.time()
        final_results = distribute_inference_tasks(dirpaths)
        end_time = time.time()
        
        print(f"所有计算已完成！总耗时: {end_time - start_time:.2f} 秒")
        
        save_dir = f"/home/sbp/lixinyang/pingmesh/data/res/neteventcause_baseline_{int(time.time())}"
        os.makedirs(save_dir, exist_ok=True)
        
        save_path = os.path.join(save_dir, "res.json")
        save_json(final_results, save_path)
        print(f"NetEventCause 基线结果已保存至: {save_path}")