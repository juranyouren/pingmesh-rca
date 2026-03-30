import os, json
import sys
import time
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.append("/home/sbp/lixinyang/pingmesh")
# 导入您设计好的两类Prompt
from utils.prompts import CASE_REVIEW_SINGLE, CASE_REVIEW_ALL,SKILL_GEN

def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

class CaseReviewer:
    def __init__(self, model_path="/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B", ASCEND_RT_VISIBLE_DEVICES="0,1"):
        print(f"[{os.getpid()}] 正在初始化 vLLM 引擎，使用的 NPU 卡号为: {ASCEND_RT_VISIBLE_DEVICES}")
        
        self.model_path = model_path
        self.ASCEND_RT_VISIBLE_DEVICES = ASCEND_RT_VISIBLE_DEVICES
        
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = self.ASCEND_RT_VISIBLE_DEVICES
        
        from vllm import LLM, SamplingParams
        
        self.llm = LLM(
            model=self.model_path,
            tensor_parallel_size=2,  # 规定每个实例使用两张卡
            gpu_memory_utilization=0.85,
            max_model_len=65536/4,
            trust_remote_code=True
        )
        
        self.sampling_params = SamplingParams(
            temperature=0.6,
            max_tokens=4096, # 反思报告可能较长，调大了max_tokens
            repetition_penalty=1.05
        )

    def batch_infer(self, prompts: list, batch_size: int = 8) -> list:
        """
        // Pseudocode for batch_infer:
        // 1. Log inference start
        // 2. Define inner vllm_invoke function with tqdm progress
        // 3. Try to run chat inferences in batches
        // 4. Return responses or handle exceptions
        """
        print(f"[{os.getpid()}] 正在执行批量推理 (共 {len(prompts)} 条, Batch Size: {batch_size})...")

        def vllm_invoke(llm, inputs:list, sampling_params, batch_size=1):
            from tqdm import tqdm
            all_responses = []
            n = getattr(sampling_params, "n", 1)
            for i in tqdm(range(0, len(inputs), batch_size)):
                batch_inputs = inputs[i:i + batch_size]
                applied_prompts = [[
                    {'role': 'user', 'content': prompt}
                ] for prompt in batch_inputs]
                outputs_w_prompts = llm.chat(applied_prompts, sampling_params)
                if n > 1:
                    for item in outputs_w_prompts:
                        all_responses.append([out.text for out in item.outputs])
                else:
                    all_responses.extend([item.outputs[0].text for item in outputs_w_prompts])
            return all_responses
        try:
            responses = vllm_invoke(
                llm=self.llm, 
                inputs=prompts, 
                sampling_params=self.sampling_params, 
                batch_size=batch_size
            )
            return responses
        except Exception as e:
            print(f"\n[Error {os.getpid()}] vLLM 批量推理执行异常: {str(e)}")
            return ["模型未返回有效推理内容或发生异常。"] * len(prompts)


import os
import json

def generate_single_review_prompts(res_file_path: str) -> tuple:
    """生成第一阶段的单Case反思Prompt（从res.json中读取）"""
    dirpath_list = []
    prompt_list = []
    print(f"开始解析结果文件 {res_file_path} 并构造单Case反思 Prompt...")
    
    try:
        # 读取汇总了失败 case 的 res.json
        res_data = load_json(res_file_path)
    except Exception as e:
        print(f"[错误] 无法读取或解析结果文件 {res_file_path}: {e}")
        return [], []

    for item in res_data:
        dirpath = item.get("name")
        if not dirpath:
            print("[警告] 发现缺少 'name' 字段的记录，已跳过。")
            continue
            
        try:
            # 1. 根据 name 字段去对应目录读取原始输入数据
            node_path = os.path.join(dirpath, "nodes.json")
            info_path = os.path.join(dirpath, "info.json")
            
            if not (os.path.exists(node_path) and os.path.exists(info_path)):
                print(f"[警告] 目录 {dirpath} 下缺失 nodes.json 或 info.json，跳过该Case。")
                continue
                
            node = load_json(node_path)
            info = load_json(info_path)
            
            # 2. 从 res.json 中提取大模型之前的回答与真实标签
            # 直接将模型的思维链(think)和输出都作为 wrong_prediction 传给反思Prompt，效果更好
            wrong_prediction = item.get("response", "") 
            ground_truth_ips = item.get("groundtruth_ips", [])
            
            # 3. 构造单case反思 prompt
            # prompt = CASE_REVIEW_SINGLE.format(
            #     node_info=json.dumps(node, ensure_ascii=False),
            #     alarm_info=json.dumps(info, ensure_ascii=False),
            #     wrong_prediction=wrong_prediction, 
            #     ground_truth=json.dumps(ground_truth_ips, ensure_ascii=False)
            # )

            case_dict={
                "input":item.get("pmt"),
                "ground_truth_ips":ground_truth_ips,
                "wrong_prediction":wrong_prediction
            }
            prompt = SKILL_GEN.format(
                case=case_dict
            )
            
            dirpath_list.append(dirpath)
            prompt_list.append(prompt)
            
        except Exception as e:
            print(f"\n[错误] 处理 Case {dirpath} 时发生异常: {e}")
            
    return dirpath_list, prompt_list


def worker_process(worker_id: int, npus: str, dirpaths_chunk: list, prompts_chunk: list, batch_size: int = 8) -> dict:
    import os
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    print(f"[Worker {worker_id}] 环境变量已设置 ASCEND_RT_VISIBLE_DEVICES={npus}")
    sleep_time = (worker_id - 1) * 60
    time.sleep(sleep_time)
    
    reviewer = CaseReviewer(ASCEND_RT_VISIBLE_DEVICES=npus)
    responses = reviewer.batch_infer(prompts_chunk, batch_size=batch_size)
    
    result_dict = {}
    for dp, res in zip(dirpaths_chunk, responses):
        clean_res = res.strip() if isinstance(res, str) else str(res)
        result_dict[dp] = clean_res
    
    return result_dict


def distribute_inference_tasks(dirpath_list: list, prompt_list: list, npu_list: list, batch_size: int = 8) -> dict:
    total_tasks = len(prompt_list)
    if total_tasks == 0:
        return {}

    num_instances = len(npu_list) // 2
    if num_instances == 0:
        raise ValueError("卡数不足！每个实例至少需要 2 张 NPU 卡。")

    npu_groups = [f"{npu_list[i*2]},{npu_list[i*2+1]}" for i in range(num_instances)]
    print(f"检测到可用 NPU: {npu_list}。将启动 {num_instances} 个并行实例，分配组: {npu_groups}")

    chunk_size = math.ceil(total_tasks / num_instances)
    dir_chunks = [dirpath_list[i:i + chunk_size] for i in range(0, total_tasks, chunk_size)]
    prompt_chunks = [prompt_list[i:i + chunk_size] for i in range(0, total_tasks, chunk_size)]
    
    if len(dir_chunks) > num_instances:
        dir_chunks[num_instances - 1].extend(sum(dir_chunks[num_instances:], []))
        prompt_chunks[num_instances - 1].extend(sum(prompt_chunks[num_instances:], []))
        dir_chunks = dir_chunks[:num_instances]
        prompt_chunks = prompt_chunks[:num_instances]

    all_results = {}
    ctx = mp.get_context('spawn')
    
    with ProcessPoolExecutor(max_workers=num_instances, mp_context=ctx) as executor:
        futures = []
        for i in range(num_instances):
            if i < len(dir_chunks) and len(dir_chunks[i]) > 0:
                print(f"正在提交单Case反思任务给实例 {i+1} (NPU: {npu_groups[i]})...")
                future = executor.submit(
                    worker_process, 
                    worker_id=i+1, 
                    npus=npu_groups[i], 
                    dirpaths_chunk=dir_chunks[i], 
                    prompts_chunk=prompt_chunks[i],
                    batch_size=batch_size
                )
                futures.append(future)

        for future in as_completed(futures):
            try:
                res_dict = future.result()
                all_results.update(res_dict)
            except Exception as exc:
                print(f"某个子进程执行过程中发生了异常: {exc}")

    return all_results

def chunk_reviews_by_token(reviews: list, model_path: str, max_tokens: int = 10000) -> list:
    """
    根据 Token 数量将海量案例拆分为多个子列表 (Chunk)。
    预留了大概 1500 Tokens 给系统提示词 (CASE_REVIEW_ALL 的固定文本) 和生成空间，因此安全阈值设为 8500。
    """
    try:
        from transformers import AutoTokenizer
        print(f"正在加载 Tokenizer ({model_path}) 用于精确统计 Token...")
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        use_tokenizer = True
    except Exception as e:
        print(f"[警告] Tokenizer 加载失败，将使用字符长度粗略估算: {e}")
        use_tokenizer = False

    chunks = []
    current_chunk = []
    current_tokens = 0

    for review in reviews:
        # 清理文本
        review_text = review.strip() if isinstance(review, str) else str(review)
        
        # 计算单个 Review 的 token
        if use_tokenizer:
            # 仅计算内容长度
            item_tokens = len(tokenizer.encode(f"### Failed Case X\n{review_text}\n\n"))
        else:
            # 如果加载失败，简单估算 (中英混合粗略算 1.5 chars ≈ 1 token)
            item_tokens = int(len(review_text) / 1.5)

        # 如果单个 review 已经超过阈值（极其罕见），强制截断或单独成块
        if item_tokens > max_tokens:
            print(f"[警告] 发现超大单个 Review ({item_tokens} tokens)，已单独成块。")
            if current_chunk:
                chunks.append(current_chunk)
            chunks.append([review_text])
            current_chunk = []
            current_tokens = 0
            continue

        # 累加判断是否超过当前块容量
        if current_tokens + item_tokens > max_tokens:
            chunks.append(current_chunk)
            current_chunk = [review_text]
            current_tokens = item_tokens
        else:
            current_chunk.append(review_text)
            current_tokens += item_tokens

    # 收尾最后一个块
    if current_chunk:
        chunks.append(current_chunk)

    print(f"数据切分完毕：共 {len(reviews)} 个案例，被分为 {len(chunks)} 个批次处理。")
    return chunks

def global_review_worker_batched(npus: str, review_chunks: list, model_path: str) -> list:
    """阶段二：在独立进程中运行全局反思，接收分块后的 reviews，避免显存溢出和 Context 截断"""
    import os
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    
    print(f"\n[Global Reviewer] 开始全局 Skill 提取，共需处理 {len(review_chunks)} 个 Chunk...")
    
    # 整个进程中只初始化一次 CaseReviewer，避免反复加载模型的巨大开销
    reviewer = CaseReviewer(model_path=model_path, ASCEND_RT_VISIBLE_DEVICES=npus)
    
    global_prompts = []
    for chunk in review_chunks:
        formatted_summaries = ""
        for idx, review in enumerate(chunk):
            formatted_summaries += f"### Failed Case {idx+1}\n{review}\n\n"
            
        prompt = CASE_REVIEW_ALL.format(failed_cases_summary_list=formatted_summaries)
        global_prompts.append(prompt)
    
    # 因为每个 prompt 逼近 10k Token 且输出可能很长，建议这里的 batch_size 设为 1 或 2，防止 NPU OOM
    responses = reviewer.batch_infer(global_prompts, batch_size=1)
    return responses

# --- 主程序入口 ---
if __name__ == "__main__":
    MODEL_PATH="/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B"
    root_path = "/home/sbp/lixinyang/pingmesh/data/res/exeskilled3/ranking_failures.json"
    available_npus = [2, 3, 4,5,6,7]  # 你的可用 NPU 列表
    
    # # ================= 阶段一：并行计算单Case反思 =================
    dirpaths, single_prompts = generate_single_review_prompts(root_path)

    if not single_prompts:
        print("没有找到需要反思的任务。请检查数据目录和文件完整性。")
        sys.exit(0)

    print(f"====== [阶段一] 开始 {len(single_prompts)} 个失败案例的单点反思 ======")
    start_time = time.time()
    single_results = distribute_inference_tasks(
        dirpath_list=dirpaths, 
        prompt_list=single_prompts, 
        npu_list=available_npus,
        batch_size=8
    )
    
    # 结果保存
    timenow = int(time.time())
    
    save_dir = os.path.dirname(root_path)
    os.makedirs(save_dir, exist_ok=True)
    
    if single_results:
        save_path = os.path.join(save_dir, "single_reviews.json")
        save_json(single_results, save_path)
        print(f"单点反思完成！结果已保存至: {save_path}")
    
    # ================= 阶段二：全局聚类与Skill提取 =================
    # print(f"\n====== [阶段二] 开始全局案例聚类与 Skill 提取 ======")
    # start_time = time.time()
    
    # # 1. 读取检查后的反思文本
    # try:
    #     single_results = load_json("/home/sbp/lixinyang/pingmesh/data/res/naive_res_prmt4_0/lesson.json/single_reviews.json")
    #     review_texts = list(single_results.values())
    #     print(f"成功加载 {len(review_texts)} 条单点反思记录。")
    # except Exception as e:
    #     print(f"读取文件失败，请检查路径: {e}")
    #     sys.exit(1)

    # # 2. 按 Token 限制分块 (单块限制在 8500 tokens 左右，确保总计不超过 10000)
    # review_chunks = chunk_reviews_by_token(
    #     reviews=review_texts, 
    #     model_path=MODEL_PATH, 
    #     max_tokens=10000 
    # )

    # # 3. 开启独立进程进行推理
    # ctx = mp.get_context('spawn')
    # with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as executor:
    #     future = executor.submit(
    #         global_review_worker_batched, 
    #         npus="0,1", 
    #         review_chunks=review_chunks,
    #         model_path=MODEL_PATH
    #     )
    #     final_skill_reports = future.result() # 这里返回的是一个 List[str]

    # # 4. 保存合并的结果
    # save_dir = os.path.dirname(root_path)
    # skill_save_path = os.path.join(save_dir, "extracted_skills_merged.md")
    # with open(skill_save_path, 'w', encoding='utf-8') as f:
    #     f.write(f"# 全局 Skill 提取报告 (分 {len(final_skill_reports)} 批生成)\n\n")
    #     for i, report in enumerate(final_skill_reports):
    #         f.write(f"## 批次 {i+1} 提取结果\n\n")
    #         f.write(report)
    #         f.write("\n\n---\n\n")
            
    # end_time = time.time()
    # print(f"\n全局 Skill 提取完成！共生成 {len(final_skill_reports)} 份分块报告，已合并保存至: {skill_save_path}")
    # print(f"总耗时: {end_time - start_time:.2f} 秒")

