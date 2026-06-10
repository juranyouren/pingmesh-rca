import os, json
import re
import sys
import time
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.append("/home/sbp/lixinyang/pingmesh")
# 导入针对“告警共现”重新设计的三阶段 Prompt
from utils.prompts import CO_OCCUR_CASE_REVIEW, CO_OCCUR_DISTILLATION, MASTER_CO_OCCUR_GEN
from Sys.CaseReviewer.FeatureExtract import FailedCaseFeatureExtractor

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
    """生成第一阶段的单Case反思Prompt（挖掘导致误判的共现告警组合）"""
    dirpath_list = []
    prompt_list = []
    print(f"开始解析错案文件 {res_file_path} 并构造单点告警挖掘 Prompt...")
    
    try:
        res_data = load_json(res_file_path)
    except Exception as e:
        print(f"[错误] 无法读取或解析结果文件: {e}")
        return [], []

    

    for item in res_data:
        # 1. 实例化 Python 提取器
        extractor = FailedCaseFeatureExtractor(item)
        feature_report = extractor.generate_feature_report()
        
        # 2. 格式化 Prompt
        prompt = CO_OCCUR_CASE_REVIEW.format(
            PMT=item.get("pmt"),
            RES=item.get("response", ""),
            GT=item.get("gt_ips", []),
            PYTHON_FEATURE_REPORT=feature_report  # 注入 Python 算好的显性特征！
        )
        prompt_list.append(prompt)
        dirpath_list.append(item.get("name"))
            
    return dirpath_list, prompt_list

def worker_process(worker_id: int, npus: str, dirpaths_chunk: list, prompts_chunk: list, batch_size: int = 8) -> dict:
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    time.sleep((worker_id - 1) * 60)
    
    reviewer = CaseReviewer(ASCEND_RT_VISIBLE_DEVICES=npus)
    responses = reviewer.batch_infer(prompts_chunk, batch_size=batch_size)
    
    return {dp: str(res).strip() for dp, res in zip(dirpaths_chunk, responses)}

def distribute_inference_tasks(dirpath_list: list, prompt_list: list, npu_list: list, batch_size: int = 8) -> dict:
    total_tasks = len(prompt_list)
    if total_tasks == 0: return {}
    num_instances = len(npu_list) // 2
    npu_groups = [f"{npu_list[i*2]},{npu_list[i*2+1]}" for i in range(num_instances)]
    
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

def chunk_reviews_by_token(reviews: list, model_path: str, max_tokens: int = 5000) -> list:
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
    data = load_json(path)
    result = []
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
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    reviewer = CaseReviewer(model_path=model_path, ASCEND_RT_VISIBLE_DEVICES=npus)
    return reviewer.batch_infer(prompts, batch_size=1)


# --- 主程序入口 ---
if __name__ == "__main__":
    MODEL_PATH = "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B"
    # 这里建议指向大模型初稿跑错的数据集（比如没有挂载共现规则前的 draft_failures）
    root_path = "/home/sbp/lixinyang/pingmesh/data/res/newskill_1/draft_ranking_failures.json"
    
    # 【核心修改点】: 指向新的告警共现经验库
    CO_OCCUR_RULES_PATH = "/home/sbp/lixinyang/pingmesh/SkillBank/alarm_co_occurrence_rules.json"
    save_dir = os.path.dirname(root_path)
    available_npus = [2,3,6,7] 
    
    # ================= 阶段一：并行计算错案告警组合挖掘 =================
    dirpaths, single_prompts = generate_single_review_prompts(root_path)
    prompt_saved=[]
    for dp,sp in zip(dirpaths,single_prompts):
        tmp={
            "dir":dp,
            "pmt":sp
        }
        prompt_saved.append(tmp)
    save_json(prompt_saved,os.path.join(save_dir, "prompt_saved.json"))
    if not single_prompts:
        sys.exit(0)

    print(f"====== [阶段一] 开始 {len(single_prompts)} 个错案的告警组合挖掘 ======")
    start_time = time.time()
    
    single_results_path = os.path.join(save_dir, "step1_single_co_occur.json")
    single_results = distribute_inference_tasks(dirpaths, single_prompts, available_npus, 8)
    
    if single_results:
        save_json(single_results, single_results_path)
        review_jsons = extract_json_blocks(single_results_path, "step1_co_occur_raw.json")
    
    # ================= 阶段二：局部聚合 (Distillation 去重) =================
    print(f"\n====== [阶段二] 开始告警组合规则聚类与去重 ======")
    single_results_path = os.path.join(save_dir, "step1_single_co_occur.json")
    review_jsons = extract_json_blocks(single_results_path, "step1_co_occur_raw.json")
    review_texts = [json.dumps(r, ensure_ascii=False) for r in review_jsons]
    review_chunks = chunk_reviews_by_token(review_texts, MODEL_PATH, 5000)

    chunk_prompts = []
    for chunk in review_chunks:
        formatted_summaries = "\n\n".join([f"### 告警共现挖掘报告 {i+1}\n{r}" for i, r in enumerate(chunk)])
        chunk_prompts.append(CO_OCCUR_DISTILLATION.format(REPORT=formatted_summaries))

    ctx = mp.get_context('spawn')
    with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as executor:
        future = executor.submit(global_worker_batched, "2,3", chunk_prompts, MODEL_PATH)
        chunked_rule_reports = future.result()

    step2_results_path = os.path.join(save_dir, "step2_chunked_co_occur.json")
    save_json(chunked_rule_reports, step2_results_path)
    chunked_rules_json = extract_json_blocks(step2_results_path, "step2_co_occur_extracted.json")

    # ================= 阶段三：全局统一定稿 (增量融合) =================
    print(f"\n====== [阶段三] 开始生成 / 迭代全局告警共现经验库 ======")
    
    history_rules_data = "[]"
    if os.path.exists(CO_OCCUR_RULES_PATH):
        try:
            history_data = load_json(CO_OCCUR_RULES_PATH)
            if history_data:
                history_rules_data = json.dumps(history_data, ensure_ascii=False, indent=2)
                print(f"[Info] 检测到历史经验库，包含 {len(history_data)} 组高危告警组合，将进行增量融合。")
        except Exception as e:
            print(f"[警告] 读取历史经验库失败，将作为首次冷启动生成: {e}")

    all_extracted_rules = json.dumps(chunked_rules_json, ensure_ascii=False, indent=2)
    
    master_prompt = MASTER_CO_OCCUR_GEN.format(
        HISTORY_RULES=history_rules_data,
        ALL_RULES=all_extracted_rules
    )
    
    with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as executor:
        future = executor.submit(global_worker_batched, "2,3", [master_prompt], MODEL_PATH)
        master_rules_result = future.result()

    final_raw_path = os.path.join(os.path.dirname(CO_OCCUR_RULES_PATH),"raw_co_occur.json")
    save_json(master_rules_result, final_raw_path)
    
    # 核心闭环：提取纯净 JSON，直接覆盖经验库文件
    extract_json_blocks(final_raw_path, "alarm_co_occurrence_rules.json")
    
    print(f"\n全部完成！告警共现经验库已迭代并保存至: {CO_OCCUR_RULES_PATH}")
    print(f"总耗时: {time.time() - start_time:.2f} 秒")