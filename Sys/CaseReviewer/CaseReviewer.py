import os, json
import re
import sys
import time
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.append("/home/sbp/lixinyang/pingmesh")
# 导入您设计好的用于生成 Refine 规则的 Prompt
from utils.prompts import BAD_CASE_REVIEW, RULE_DISTILLATION, MASTER_CHECKLIST_GEN

def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_txt(path):
    with open(path, 'r', encoding='utf-8') as file:
        return file.read()

class CaseReviewer:
    def __init__(self, model_path="/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B", ASCEND_RT_VISIBLE_DEVICES="0,1"):
        print(f"[{os.getpid()}] 正在初始化 vLLM 引擎，使用的 NPU 卡号为: {ASCEND_RT_VISIBLE_DEVICES}")
        self.model_path = model_path
        self.ASCEND_RT_VISIBLE_DEVICES = ASCEND_RT_VISIBLE_DEVICES
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = self.ASCEND_RT_VISIBLE_DEVICES
        
        from vllm import LLM, SamplingParams
        
        self.llm = LLM(
            model=self.model_path,
            tensor_parallel_size=2,
            gpu_memory_utilization=0.85,
            max_model_len=65536//4, 
            trust_remote_code=True
        )
        
        self.sampling_params = SamplingParams(
            temperature=0.6,
            max_tokens=4096,
            repetition_penalty=1.05
        )

    def batch_infer(self, prompts: list, batch_size: int = 8) -> list:
        print(f"[{os.getpid()}] 正在执行批量推理 (共 {len(prompts)} 条, Batch Size: {batch_size})...")

        def vllm_invoke(llm, inputs:list, sampling_params, batch_size=1):
            from tqdm import tqdm
            all_responses = []
            for i in tqdm(range(0, len(inputs), batch_size)):
                batch_inputs = inputs[i:i + batch_size]
                applied_prompts = [[
                    {'role': 'user', 'content': prompt}
                ] for prompt in batch_inputs]
                outputs_w_prompts = llm.chat(applied_prompts, sampling_params)
                all_responses.extend([item.outputs[0].text for item in outputs_w_prompts])
            return all_responses
            
        try:
            return vllm_invoke(self.llm, prompts, self.sampling_params, batch_size)
        except Exception as e:
            print(f"\n[Error {os.getpid()}] vLLM 批量推理执行异常: {str(e)}")
            return ["模型未返回有效推理内容或发生异常。"] * len(prompts)


def generate_single_review_prompts(res_file_path: str) -> tuple:
    """生成第一阶段的单Case反思Prompt（诊断错误并提出规则建议）"""
    dirpath_list = []
    prompt_list = []
    print(f"开始解析结果文件 {res_file_path} 并构造单Case反思 Prompt...")
    
    try:
        res_data = load_json(res_file_path)
    except Exception as e:
        print(f"[错误] 无法读取或解析结果文件: {e}")
        return [], []

    for item in res_data:
        dirpath = item.get("name")
        if not dirpath: continue
            
        try:
            wrong_prediction = item.get("response", "") 
            ground_truth_ips = item.get("gt_ips", [])
            
            prompt = BAD_CASE_REVIEW.format(
                PMT=item.get("pmt"),
                RES=wrong_prediction,
                GT=ground_truth_ips
            )
            
            dirpath_list.append(dirpath)
            prompt_list.append(prompt)
        except Exception as e:
            print(f"\n[错误] 处理 Case {dirpath} 时发生异常: {e}")
            
    return dirpath_list, prompt_list

def worker_process(worker_id: int, npus: str, dirpaths_chunk: list, prompts_chunk: list, batch_size: int = 8) -> dict:
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    time.sleep((worker_id - 1) * 60)
    
    reviewer = CaseReviewer(ASCEND_RT_VISIBLE_DEVICES=npus)
    responses = reviewer.batch_infer(prompts_chunk, batch_size=batch_size)
    
    return {dp: str(res).strip() for dp, res in zip(dirpaths_chunk, responses)}

def distribute_inference_tasks(dirpath_list: list, prompt_list: list, npu_list: list, batch_size: int = 8) -> dict:
    """多进程分发第一阶段任务"""
    total_tasks = len(prompt_list)
    if total_tasks == 0: return {}

    num_instances = len(npu_list) // 2
    npu_groups = [f"{npu_list[i*2]},{npu_list[i*2+1]}" for i in range(num_instances)]
    print(f"分配组: {npu_groups}")

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
                future = executor.submit(
                    worker_process, i+1, npu_groups[i], dir_chunks[i], prompt_chunks[i], batch_size
                )
                futures.append(future)

        for future in as_completed(futures):
            all_results.update(future.result())

    return all_results

def chunk_reviews_by_token(reviews: list, model_path: str, max_tokens: int = 10000) -> list:
    """根据 Token 数量将海量案例反思报告拆分为多个子列表"""
    try:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        use_tokenizer = True
    except:
        use_tokenizer = False

    chunks, current_chunk, current_tokens = [], [], 0

    for review in reviews:
        review_text = str(review).strip()
        item_tokens = len(tokenizer.encode(review_text)) if use_tokenizer else int(len(review_text) / 1.5)

        if item_tokens > max_tokens:
            if current_chunk: chunks.append(current_chunk)
            chunks.append([review_text])
            current_chunk, current_tokens = [], 0
            continue

        if current_tokens + item_tokens > max_tokens:
            chunks.append(current_chunk)
            current_chunk = [review_text]
            current_tokens = item_tokens
        else:
            current_chunk.append(review_text)
            current_tokens += item_tokens

    if current_chunk: chunks.append(current_chunk)
    return chunks

def extract_json_blocks(path: str, save_name: str) -> list:
    """通用的 JSON 提取函数"""
    data = load_json(path)
    result = []
    
    # 兼容传入的是字典（第一阶段输出）还是列表（第二阶段输出）
    values = data.values() if isinstance(data, dict) else data
    
    for res in values:
        json_blocks = re.findall(r'```json\s*(.*?)\s*```', str(res), re.DOTALL | re.IGNORECASE)
        if json_blocks:
            try:
                result.append(json.loads(json_blocks[-1]))
            except Exception:
                pass
                
    save_json(result, os.path.join(os.path.dirname(path), save_name))
    return result

def global_worker_batched(npus: str, prompts: list, model_path: str) -> list:
    """通用的独立进程推理 Worker (用于阶段二和阶段三)"""
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    reviewer = CaseReviewer(model_path=model_path, ASCEND_RT_VISIBLE_DEVICES=npus)
    return reviewer.batch_infer(prompts, batch_size=1)

# --- 主程序入口 ---
if __name__ == "__main__":
    MODEL_PATH = "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B"
    root_path = "/home/sbp/lixinyang/pingmesh/data/res/skill_ref1/refined_ranking_failures.json"
    CHECK_LIST_PATH="/home/sbp/lixinyang/pingmesh/SkillBank/check_list.json"
    save_dir = os.path.dirname(root_path)
    available_npus = [0,1,2, 3, 4, 5, 6, 7] 
    
    # ================= 阶段一：并行计算单Case反思提取 =================
    dirpaths, single_prompts = generate_single_review_prompts(root_path)

    if not single_prompts:
        sys.exit(0)

    print(f"====== [阶段一] 开始 {len(single_prompts)} 个失败案例的单点规则反思 ======")
    start_time = time.time()
    
    single_results_path = os.path.join(save_dir, "step1_single_reviews.json")
    single_results = distribute_inference_tasks(dirpaths, single_prompts, available_npus, 8)
    
    if single_results:
        save_json(single_results, single_results_path)
        # 提取阶段一的 JSON，保存为 step1_exps.json
        review_jsons = extract_json_blocks(single_results_path, "step1_exps.json")
    
    # ================= 阶段二：局部聚合 (Distillation) =================
    print(f"\n====== [阶段二] 开始局部规则聚类与去重 ======")
    
    # 将提取出的 JSON 转为文本形式，准备分块输入
    review_texts = [json.dumps(r, ensure_ascii=False) for r in review_jsons]
    review_chunks = chunk_reviews_by_token(review_texts, MODEL_PATH, 10000)

    chunk_prompts = []
    for chunk in review_chunks:
        formatted_summaries = "\n\n".join([f"### Bad Case Review {i+1}\n{r}" for i, r in enumerate(chunk)])
        # 使用提炼规则的 Prompt
        chunk_prompts.append(RULE_DISTILLATION.format(REPORT=formatted_summaries))

    ctx = mp.get_context('spawn')
    with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as executor:
        future = executor.submit(global_worker_batched, "2,3", chunk_prompts, MODEL_PATH)
        chunked_rule_reports = future.result()

    step2_results_path = os.path.join(save_dir, "step2_chunked_rules.json")
    save_json(chunked_rule_reports, step2_results_path)
    
    # 提取阶段二生成的 JSON 规则列表
    chunked_rules_json = extract_json_blocks(step2_results_path, "step2_rules_extracted.json")

    # ================= 阶段三：全局统一定稿 (Master Checklist 增量迭代) =================
    print(f"\n====== [阶段三] 开始生成 / 迭代全局 Master Checklist ======")
    
    # 1. 尝试读取历史的 Master Checklist
    historical_checklist_path = CHECK_LIST_PATH
    history_checklist_data = "[]"  # 默认空列表（冷启动状态）
    
    if os.path.exists(historical_checklist_path):
        try:
            history_data = load_json(historical_checklist_path)
            if history_data:  # 确保不是空文件
                history_checklist_data = json.dumps(history_data, ensure_ascii=False, indent=2)
                print(f"[Info] 检测到历史 Master Checklist，包含 {len(history_data)} 条规则，将进行增量融合。")
        except Exception as e:
            print(f"[警告] 读取历史 Master Checklist 失败，将作为首次初始化处理: {e}")
    else:
        print(f"[Info] 未检测到历史 Master Checklist，系统将执行首次冷启动生成。")

    # 2. 将阶段二提取的新规则格式化
    all_extracted_rules = json.dumps(chunked_rules_json, ensure_ascii=False, indent=2)
    
    # 3. 注入到迭代 Prompt 中
    master_prompt = MASTER_CHECKLIST_GEN.format(
        HISTORY_CHECKLIST=history_checklist_data,
        ALL_RULES=all_extracted_rules
    )
    
    # 4. 执行大模型融合推理
    with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as executor:
        future = executor.submit(global_worker_batched, "2,3", [master_prompt], MODEL_PATH)
        master_checklist_result = future.result()

    # 5. 保存并提取新的 Checklist，这会覆盖旧的 pure_master_checklist.json，实现闭环
    final_raw_path = os.path.join(os.path.dirname(CHECK_LIST_PATH),"raw.json")
    save_json(master_checklist_result, final_raw_path)
    
    # 核心闭环：提取纯净 JSON，直接覆盖原有的 historical_checklist_path
    extract_json_blocks(final_raw_path, "check_list.json")
    
    print(f"\n全部完成！最终的 Refine Checklist 已完成迭代并保存至: {historical_checklist_path}")
    print(f"总耗时: {time.time() - start_time:.2f} 秒")