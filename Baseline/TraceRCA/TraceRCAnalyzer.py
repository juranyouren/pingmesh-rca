import os
import json
import sys
import time
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

class TraceRCAnalyzer:
    def __init__(self, method: int = 1):
        """
        初始化 TraceRCA 基线推理器 (纯数学与拓扑统计，无 LLM)
        :param method: 杰卡德计算方法 (0=基础版, 1=归一化版, 2=基于总度的变种)
        """
        self.method = method

    def _prepare_data(self, dirpath: str) -> tuple:
        """加载数据并转换为按 IP 索引的字典"""
        nodes_path = os.path.join(dirpath, "nodes.json")
        info_path = os.path.join(dirpath, "info.json")
        
        nodes_data = load_json(nodes_path) if os.path.exists(nodes_path) else {}
        info_data = load_json(info_path) if os.path.exists(info_path) else {}
        
        if "path_count" not in info_data:
            info_data["path_count"] = info_data.get("task_num", 1)
            
        ipindexed_nodes = {}
        node_list = list(nodes_data.values()) if isinstance(nodes_data, dict) else nodes_data
        for node in node_list:
            ip = node.get("mgmt_ip")
            if ip:
                ipindexed_nodes[ip] = node
                
        return ipindexed_nodes, info_data

    def _calculate_jaccard_index(self, ipindexed_nodes: dict, info: dict) -> list:
        """核心计算逻辑：基于拓扑度数与流量交汇度的类杰卡德指数"""
        if not ipindexed_nodes:
            return []

        jaccard_scores = []
        max_cross = 1
        for ip, node_data in ipindexed_nodes.items():
            if float(node_data.get('cross', 0)) > max_cross:
                max_cross = float(node_data.get('cross', 0))
                
        for ip, node_data in ipindexed_nodes.items():
            cross = float(node_data.get('cross', 0))
            in_degree = len(node_data.get('linked_from', []))
            out_degree = len(node_data.get('linked_to', []))
            total_degree = float(in_degree + out_degree)
            
            paths = 1
            alarm_count = len(node_data.get("alarms", []))
            log_count = len(node_data.get("logs", []))

            if total_degree == 0 and self.method == 2:
                p_x_y, p_y_x = 0.0, 0.0
            else:
                if self.method == 0:
                    p_x_y, p_y_x = cross, total_degree
                elif self.method == 1:
                    total = cross + total_degree
                    p_x_y = cross / total if total > 0 else 0
                    p_y_x = total_degree / total if total > 0 else 0
                elif self.method == 2:
                    p_x_y = cross / total_degree
                    p_y_x = (total_degree - cross) / total_degree if total_degree > 0 else 0
                elif self.method == 3:
                    p_x_y = cross
                    p_y_x = paths / float(info.get("path_count", 1))
                else:
                    p_x_y, p_y_x = 0.0, 0.0

            # 计算调和平均数 H
            sum_p = p_x_y + p_y_x
            h = (2.0 * p_x_y * p_y_x) / sum_p if sum_p > 0 else 0.0
            
            # 计算类杰卡德指数 J
            denominator = 2.0 - h
            j_index = float('inf') if abs(denominator) < 1e-6 else h / denominator
            
            if self.method == 4:
                j_index = alarm_count + log_count
                
            jaccard_scores.append({
                "ip": ip,
                "jaccard_index": j_index
            })
            
        sorted_nodes = sorted(jaccard_scores, key=lambda x: x['jaccard_index'], reverse=True)
        return sorted_nodes

    def process_cases(self, dirpaths: list) -> list:
        """执行 TraceRCA 流水线"""
        # 由于无需 LLM，处理速度极快，直接遍历计算
        results = []
        for dp in dirpaths:
            ipindexed_nodes, info_data = self._prepare_data(dp)
            sorted_nodes = self._calculate_jaccard_index(ipindexed_nodes, info_data)
            
            # 截取 Top 3 IP
            top_ips = [node["ip"] for node in sorted_nodes[:5]]
            
            # 伪装成大模型标准 JSON 输出格式，完美对齐评测脚本
            # fake_llm_response = {
            #     "reasoning": f"TraceRCA Baseline (Method={self.method}). 推导基于杰卡德指数 (Cross & Degree)，纯拓扑统计模型，未使用大模型语义分析。",
            #     "ip": top_ips
            # }
            fake_llm_response=f"""
            TraceRCA Baseline (Method={self.method}). 推导基于杰卡德指数 (Cross & Degree)，纯拓扑统计模型，未使用大模型语义分析。
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
    """扫描获取有效的 Case 目录"""
    dirpath_list = []
    print(f"开始扫描目录 {root_path} ...")
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        if "nodes.json" in filenames and "info.json" in filenames:
            dirpath_list.append(dirpath)
                
    return dirpath_list

def worker_process(worker_id: int, dirpaths_chunk: list, method: int) -> list:
    """纯 CPU Worker，无需绑定 NPU"""
    # print(f"[Worker {worker_id}] 开始处理 {len(dirpaths_chunk)} 个 Case...")
    analyzer = TraceRCAnalyzer(method=method)
    results = analyzer.process_cases(dirpaths_chunk)
    return results

def distribute_inference_tasks(dirpath_list: list, method: int) -> list:
    total_tasks = len(dirpath_list)
    if total_tasks == 0: return []

    # 纯 CPU 密集型计算，根据 CPU 核心数自动分配并发实例数
    num_instances = min(mp.cpu_count(), 32)
    print(f"检测到纯 CPU 计算任务，将启动 {num_instances} 个并行实例。")

    chunk_size = math.ceil(total_tasks / num_instances)
    dir_chunks = [dirpath_list[i:i + chunk_size] for i in range(0, total_tasks, chunk_size)]
    
    if len(dir_chunks) > num_instances:
        dir_chunks[num_instances - 1].extend(sum(dir_chunks[num_instances:], []))
        dir_chunks = dir_chunks[:num_instances]

    all_results = []
    ctx = mp.get_context('spawn')
    
    with ProcessPoolExecutor(max_workers=num_instances, mp_context=ctx) as executor:
        futures = []
        for i in range(num_instances):
            if i < len(dir_chunks) and len(dir_chunks[i]) > 0:
                future = executor.submit(
                    worker_process, 
                    worker_id=i+1, 
                    dirpaths_chunk=dir_chunks[i], 
                    method=method
                )
                futures.append(future)

        for future in as_completed(futures):
            try:
                res_ls = future.result()
                all_results.extend(res_ls)
            except Exception as exc:
                print(f"某个子进程执行过程中发生了异常: {exc}")

    return all_results

if __name__ == "__main__":
    # 配置资源
    # TraceRCA 不需要 NPU/GPU，这里直接省略 available_npus 配置
    
    # 指向你的测试集目录
    root_path = "/home/sbp/lixinyang/pingmesh/data/nodes"
    dirpaths = generate_prompts(root_path)
    
    # 选择 Jaccard 算法版本 (1 为归一化版)
    METHOD_VERSION = 1 
    
    if dirpaths:
        print(f"共发现 {len(dirpaths)} 个 Case 任务，开始分配 TraceRCA 并行推理...")
        
        start_time = time.time()
        final_results = distribute_inference_tasks(
            dirpath_list=dirpaths, 
            method=METHOD_VERSION
        )
        end_time = time.time()
        
        print(f"所有并行推理已完成！总耗时: {end_time - start_time:.2f} 秒")
        
        timenow = int(time.time())
        save_dir = f"/home/sbp/lixinyang/pingmesh/data/res/tracerca_baseline_{timenow}"
        os.makedirs(save_dir, exist_ok=True)
        
        if final_results:
            save_path = os.path.join(save_dir, "res.json")
            save_json(final_results, save_path)
            print(f"最终 TraceRCA Baseline 结果已保存至: {save_path}")
    else:
        print("没有找到需要推理的 Case 目录。")