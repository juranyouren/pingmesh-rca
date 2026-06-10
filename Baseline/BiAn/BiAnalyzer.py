import os
import json
import sys
import time
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

# ----------------- BiAn 专属 Prompt 定义 -----------------
BIAN_SUMMARY_PROMPT = """你是一个专业的网络排障助手。请对以下网络设备节点上的告警和日志进行简要总结。
提取出最核心的故障事件（如物理端口Down、BGP断连、丢包、光模块异常等），忽略常规状态信息。
请用 1-2 句话输出摘要，不要有废话。

节点IP: {IP}
角色: {ROLE}
告警数据:
{ALARMS}
日志数据:
{LOGS}

【你的摘要】:"""

BIAN_RCA_PROMPT = """# 角色设定
你是一名资深的 AIOps 与数据中心网络专家。你的任务是根据宏观的 Pingmesh 拨测异常现象，以及底层各个网络设备节点的【状态摘要】，进行故障根因定位。

# 1. 宏观故障现象 (Info)
{INFO}

# 2. 设备状态摘要 (Node Summaries)
以下是经过分层提炼的各个节点的状态摘要：
{SUMMARIES}

# 任务要求
请根据上述摘要信息，推导导致 Pingmesh 拨测失败的根因设备（可能是单点故障，也可能是 ECMP 双上联并发故障）。
以严格的 JSON 格式输出分析过程和设备 IP：
```json
{{
    "reasoning": "<在此简述推导过程：哪些节点的摘要异常导致了全局故障>",
    "ip": [
        "<确诊根因的设备IP列表，根据嫌疑程度排序，如果没有告警请不要瞎猜>"
    ]
}}
```"""
# --------------------------------------------------------

def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

class BiAnAnalyzer:
    def __init__(self, model_path="/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B", ASCEND_RT_VISIBLE_DEVICES="0,1"):
        """
        初始化基于 vllm.LLM 的 BiAn Baseline 推理器
        """
        print(f"[{os.getpid()}] 正在初始化 vLLM 引擎，使用的 NPU 卡号为: {ASCEND_RT_VISIBLE_DEVICES}")
        self.model_path = model_path
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = ASCEND_RT_VISIBLE_DEVICES
        
        from vllm import LLM, SamplingParams
        
        self.llm = LLM(
            model=self.model_path,
            tensor_parallel_size=2,  
            gpu_memory_utilization=0.85,
            max_model_len=int(65536/4),
            trust_remote_code=True
        )
        
        self.sampling_params = SamplingParams(
            temperature=0.3, # 降低温度，摘要和 RCA 需要更确定的事实
            max_tokens=2048,
            repetition_penalty=1.05
        )
        self.tokenizer = self.llm.get_tokenizer()

    def _safe_truncate(self, text: str, max_tokens: int = 2000) -> str:
        """防止单个节点的告警文本过长导致爆显存"""
        tokens = self.tokenizer.encode(text)
        if len(tokens) > max_tokens:
            return self.tokenizer.decode(tokens[:max_tokens]) + "\n...[数据因超长被截断]"
        return text

    def _vllm_invoke(self, prompts: list, desc: str, batch_size: int = 16) -> list:
        """通用的 LLM 批量调用器"""
        from tqdm import tqdm
        all_responses = []
        for i in tqdm(range(0, len(prompts), batch_size), desc=desc):
            batch_inputs = prompts[i:i + batch_size]
            applied_prompts = [[{'role': 'user', 'content': p}] for p in batch_inputs]
            outputs = self.llm.chat(applied_prompts, self.sampling_params)
            all_responses.extend([item.outputs[0].text.strip() for item in outputs])
        return all_responses

    def process_cases(self, dirpaths: list, batch_size: int = 16) -> list:
        """执行 BiAn 的两阶段推理流水线"""
        print(f"[{os.getpid()}] 启动 BiAn 分层推理 Pipeline (处理 {len(dirpaths)} 个 Case)...")
        
        # ---------------- Stage 1: 构建并执行节点摘要任务 ----------------
        all_cases_data = []      # 存储每个 case 解析后的基础数据
        summary_prompts = []     # 存放所有需要给大模型做摘要的 Prompt
        summary_mapping = []     # 记录大模型返回的摘要属于哪个 case、哪个 ip: (case_idx, ip)
        
        for i, dp in enumerate(dirpaths):
            nodes_path = os.path.join(dp, "nodes.json")
            info_path = os.path.join(dp, "info.json")
            
            nodes_data = load_json(nodes_path) if os.path.exists(nodes_path) else {}
            info_data = load_json(info_path) if os.path.exists(info_path) else {}
            
            node_list = list(nodes_data.values()) if isinstance(nodes_data, dict) else nodes_data
            
            case_info = {
                "dirpath": dp,
                "info": info_data,
                "node_summaries": {} # { "10.0.0.1": "摘要文本", ... }
            }
            
            for node in node_list:
                ip = node.get("mgmt_ip", "Unknown")
                role = node.get("role", "Unknown")
                alarms = node.get("alarms", [])
                logs = node.get("logs", [])
                
                # BiAn 核心逻辑：空节点自动化生成摘要，非空节点调用大模型
                if not alarms and not logs:
                    case_info["node_summaries"][ip] = f"[节点 {ip} | {role}] 状态正常，无相关告警与日志。"
                else:
                    alarms_str = self._safe_truncate(json.dumps(alarms, ensure_ascii=False))
                    logs_str = self._safe_truncate(json.dumps(logs, ensure_ascii=False))
                    
                    prompt = BIAN_SUMMARY_PROMPT.format(IP=ip, ROLE=role, ALARMS=alarms_str, LOGS=logs_str)
                    summary_prompts.append(prompt)
                    summary_mapping.append((i, ip))
                    case_info["node_summaries"][ip] = None # 占位符，等大模型返回
                    
            all_cases_data.append(case_info)

        # 批量请求大模型生成非空节点摘要
        if summary_prompts:
            print(f"[{os.getpid()}] 收集到 {len(summary_prompts)} 个需要 LLM 摘要的异常节点。")
            summary_responses = self._vllm_invoke(summary_prompts, desc="Stage 1: Node Summarization", batch_size=batch_size)
            
            # 将大模型的摘要结果回填到对应的 case 中
            for (case_idx, ip), resp in zip(summary_mapping, summary_responses):
                role = "Device" # 简单回显
                all_cases_data[case_idx]["node_summaries"][ip] = f"[节点 {ip}] 异常摘要: {resp}"

        # ---------------- Stage 2: 构建并执行全局 RCA 推理 ----------------
        rca_prompts = []
        for case in all_cases_data:
            info_str = json.dumps(case["info"], ensure_ascii=False)
            
            # 拼接该 case 下所有节点的摘要
            summaries_list = [v for v in case["node_summaries"].values()]
            summaries_str = "\n".join(summaries_list)
            
            final_p = BIAN_RCA_PROMPT.format(INFO=info_str, SUMMARIES=summaries_str)
            rca_prompts.append(final_p)
            
        # 批量请求大模型进行最终的根因定位
        print(f"[{os.getpid()}] 准备进行全局 RCA 推理 ({len(rca_prompts)} 个 Case)...")
        rca_responses = self._vllm_invoke(rca_prompts, desc="Stage 2: Global RCA", batch_size=batch_size)
        
        # 组装返回结果
        results = []
        for case, pmt, res in zip(all_cases_data, rca_prompts, rca_responses):
            results.append({
                "dir": case["dirpath"],
                "prompt": pmt,
                "response": res,
                "biAn_summaries_count": len(case["node_summaries"]) # 记录一下摘要数量
            })
            
        return results


def generate_prompts(root_path: str) -> list:
    """仅扫描获取有效的 Case 目录，Prompt 构造由 Analyzer 内部完成"""
    dirpath_list = []
    print(f"开始扫描目录 {root_path} ...")
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        if "nodes.json" in filenames and "info.json" in filenames:
            dirpath_list.append(dirpath)
                
    return dirpath_list

def worker_process(worker_id: int, npus: str, dirpaths_chunk: list, batch_size: int = 16) -> list:
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    print(f"[Worker {worker_id}] 环境变量已设置 ASCEND_RT_VISIBLE_DEVICES={npus}")
    time.sleep((worker_id - 1) * 30) # 错峰初始化
    
    analyzer = BiAnAnalyzer(ASCEND_RT_VISIBLE_DEVICES=npus)
    # 调用 BiAn 的 Pipeline
    results = analyzer.process_cases(dirpaths_chunk, batch_size=batch_size)
    
    return results

def distribute_inference_tasks(dirpath_list: list, npu_list: list, batch_size: int = 16) -> list:
    total_tasks = len(dirpath_list)
    if total_tasks == 0: return []

    num_instances = len(npu_list) // 2
    if num_instances == 0:
        raise ValueError("卡数不足！每个实例至少需要 2 张 NPU 卡。")

    npu_groups = [f"{npu_list[i*2]},{npu_list[i*2+1]}" for i in range(num_instances)]
    print(f"检测到可用 NPU: {npu_list}。将启动 {num_instances} 个并行实例，分配组: {npu_groups}")

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
                print(f"正在提交任务给实例 {i+1} (NPU: {npu_groups[i]}, Case数: {len(dir_chunks[i])})...")
                future = executor.submit(
                    worker_process, 
                    worker_id=i+1, 
                    npus=npu_groups[i], 
                    dirpaths_chunk=dir_chunks[i], 
                    batch_size=batch_size
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
    available_npus = [ 2, 3,4,5]
    
    # 指向你的测试集目录
    root_path = "/home/sbp/lixinyang/pingmesh/data/nodes"
    dirpaths = generate_prompts(root_path)
    
    if dirpaths:
        print(f"共发现 {len(dirpaths)} 个 Case 任务，开始分配 BiAn 并行推理...")
        
        start_time = time.time()
        final_results = distribute_inference_tasks(
            dirpath_list=dirpaths, 
            npu_list=available_npus,
            batch_size=16 # 摘要任务比较短，batch_size 可以适当开大点
        )
        end_time = time.time()
        
        print(f"所有并行推理已完成！总耗时: {end_time - start_time:.2f} 秒")
        
        timenow = int(time.time())
        save_dir = f"/home/sbp/lixinyang/pingmesh/data/res/bian_baseline_{timenow}"
        os.makedirs(save_dir, exist_ok=True)
        
        if final_results:
            save_path = os.path.join(save_dir, "res.json")
            save_json(final_results, save_path)
            print(f"最终 BiAn Baseline 结果已保存至: {save_path}")
    else:
        print("没有找到需要推理的 Case 目录。")