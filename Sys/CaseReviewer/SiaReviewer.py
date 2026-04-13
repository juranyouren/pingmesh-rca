import os
import json
import re
import sys
import time
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.append("/home/sbp/lixinyang/pingmesh")
# 保留你原有的提炼和定稿 Prompt
from utils.prompts import RULE_DISTILLATION, MASTER_CHECKLIST_GEN,SIAMESE_CASE_REVIEW


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

# --- 孪生网络核心：相似度计算工具 ---
import os
import json

def get_case_alarms(case_data):
    """
    通过 case_data 中的目录路径，直接加载原始 Node 数据，
    提取所有节点中包含的真实告警名称集合，用于计算 Jaccard 相似度。
    """
    alarms_set = set()
    
    # 1. 获取该 Case 的数据目录路径 (兼容不同的字段命名)
    dirpath = case_data.get("dir", case_data.get("name", ""))
    if not dirpath or not os.path.exists(dirpath):
        return alarms_set
        
    # 2. 动态寻找 Node 数据文件
    node_file_path = None
    try:
        for f in os.listdir(dirpath):
            if f == "nodes.json":
                node_file_path = os.path.join(dirpath, f)
                break
    except Exception as e:
        print(f"读取目录 {dirpath} 失败: {e}")
        return alarms_set

    if not node_file_path:
        return alarms_set

    # 3. 加载并解析 Node 数据
    try:
        with open(node_file_path, 'r', encoding='utf-8') as f:
            nodes_raw = json.load(f)
            
        # 兼容 nodes_raw 是字典 (key为节点名) 或直接是列表的情况
        node_list = nodes_raw.values() if isinstance(nodes_raw, dict) else nodes_raw
        
        # 4. 遍历所有节点，提取 alarms
        for node in node_list:
            if not isinstance(node, dict):
                continue
            alarms = node.get("alarms", [])
            for alarm in alarms:
                # 兼容告警是纯字符串，或者是字典 {"name": "RM_DELETE..."} 的格式
                alarm_name = ""
                if isinstance(alarm, str):
                    alarm_name = alarm
                elif isinstance(alarm, dict):
                    alarm_name = alarm.get("name", alarm.get("alarm_name", ""))
                
                # 过滤掉无效的空名或过短的垃圾信息
                if alarm_name and len(alarm_name) > 3:
                    alarms_set.add(str(alarm_name).upper())
                    
    except Exception as e:
        print(f"解析 Node 文件 {node_file_path} 时发生异常: {e}")
        
    return alarms_set

def calculate_jaccard_similarity(set1, set2):
    if not set1 and not set2: return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0
# ----------------------------------

class SiaReviewer:
    def __init__(self, model_path="/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B", ASCEND_RT_VISIBLE_DEVICES="0,1"):
        print(f"[{os.getpid()}] 初始化 vLLM 引擎 (孪生审查模式)，NPU 卡号: {ASCEND_RT_VISIBLE_DEVICES}")
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
        print(f"[{os.getpid()}] 执行批量对比推理 (共 {len(prompts)} 条, Batch Size: {batch_size})...")
        def vllm_invoke(llm, inputs:list, sampling_params, batch_size=1):
            from tqdm import tqdm
            all_responses = []
            for i in tqdm(range(0, len(inputs), batch_size)):
                batch_inputs = inputs[i:i + batch_size]
                applied_prompts = [[{'role': 'user', 'content': prompt}] for prompt in batch_inputs]
                outputs_w_prompts = llm.chat(applied_prompts, sampling_params)
                all_responses.extend([item.outputs[0].text for item in outputs_w_prompts])
            return all_responses
            
        try:
            return vllm_invoke(self.llm, prompts, self.sampling_params, batch_size)
        except Exception as e:
            print(f"\n[Error {os.getpid()}] vLLM 推理异常: {str(e)}")
            return ["模型未返回有效推理内容。"] * len(prompts)

def generate_siamese_review_prompts(failed_path: str, success_path: str) -> tuple:
    """生成孪生对比学习 Prompt (Hard Negative Mining)"""
    dirpath_list = []
    prompt_list = []
    print(f"开始解析 Failed 数据: {failed_path}")
    print(f"开始解析 Success 数据: {success_path}")
    
    try:
        failed_data = load_json(failed_path)
        success_data = load_json(success_path)
    except Exception as e:
        print(f"[错误] 读取数据失败: {e}")
        return [], []

    print(f"载入成功: 失败案例 {len(failed_data)} 条, 成功案例 {len(success_data)} 条。正在进行孪生匹配...")

    for f_case in failed_data:
        dirpath = f_case.get("name")
        if not dirpath: continue
        
        f_alarms = get_case_alarms(f_case)
        best_s_case = None
        highest_sim = -1.0
        
        # 为每一个 Failed Case 寻找最相似的 Success Case
        for s_case in success_data:
            s_alarms = get_case_alarms(s_case)
            sim = calculate_jaccard_similarity(f_alarms, s_alarms)
            if sim > highest_sim:
                highest_sim = sim
                best_s_case = s_case
                
        # 兜底：如果完全没有相似的，随便选一个成功的作为边界约束
        if best_s_case is None and success_data:
            best_s_case = success_data[0]

        try:
            f_pmt = f_case.get("pmt", "")
            # 简单裁剪避免 Token 爆炸 (可根据实际情况调整)
            f_pmt = f_pmt[:15000] if len(f_pmt) > 15000 else f_pmt
            s_pmt = best_s_case.get("pmt", "")
            s_pmt = s_pmt[:15000] if len(s_pmt) > 15000 else s_pmt
            
            prompt = SIAMESE_CASE_REVIEW.format(
                SUCCESS_GT=best_s_case.get("gt_ips", []),
                SUCCESS_PROMPT=s_pmt,
                FAILED_GT=f_case.get("gt_ips", []),
                FAILED_PRED=f_case.get("pred_ips", f_case.get("response", "")), # 兼容不同格式
                FAILED_PROMPT=f_pmt
            )
            
            dirpath_list.append(dirpath)
            prompt_list.append(prompt)
        except Exception as e:
            print(f"\n[错误] 组装 Case {dirpath} 时异常: {e}")
            
    return dirpath_list, prompt_list

def worker_process(worker_id: int, npus: str, dirpaths_chunk: list, prompts_chunk: list, batch_size: int = 8) -> dict:
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    time.sleep((worker_id - 1) * 60)
    reviewer = SiaReviewer(ASCEND_RT_VISIBLE_DEVICES=npus)
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

def chunk_reviews_by_token(reviews: list, model_path: str, max_tokens: int = 10000) -> list:
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
            try: result.append(json.loads(json_blocks[-1]))
            except Exception: pass
    save_json(result, os.path.join(os.path.dirname(path), save_name))
    return result

def global_worker_batched(npus: str, prompts: list, model_path: str) -> list:
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    reviewer = SiaReviewer(model_path=model_path, ASCEND_RT_VISIBLE_DEVICES=npus)
    return reviewer.batch_infer(prompts, batch_size=1)

# --- 主程序入口 ---
if __name__ == "__main__":
    MODEL_PATH = "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B"
    
    # 修改：分别指向 draft 的失败集和成功集
    FAILED_CASES_PATH = "/home/sbp/lixinyang/pingmesh/data/res/skill1_2/draft_ranking_failures.json"
    SUCCESS_CASES_PATH = "/home/sbp/lixinyang/pingmesh/data/res/skill1_2/draft_ranking_success.json"
    
    CHECK_LIST_PATH = "/home/sbp/lixinyang/pingmesh/SkillBank/check_list.json"
    save_dir = os.path.dirname(FAILED_CASES_PATH)
    available_npus = [0,1,2,3,4,5,6,7] 
    
    # ================= 阶段一：孪生对比提取 =================
    # 调用新的孪生生成函数，自动匹配正负样本
    dirpaths, siamese_prompts = generate_siamese_review_prompts(FAILED_CASES_PATH, SUCCESS_CASES_PATH)

    if not siamese_prompts:
        print("未生成有效的提示词，退出。")
        sys.exit(0)

    print(f"====== [阶段一] 开始 {len(siamese_prompts)} 个案例的孪生对比反思 (Siamese Review) ======")
    start_time = time.time()
    
    single_results_path = os.path.join(save_dir, "step1_siamese_reviews.json")
    # 由于 Prompt 长度翻倍（包含两个 Case），建议 batch_size 调小到 4 防 OOM
    single_results = distribute_inference_tasks(dirpaths, siamese_prompts, available_npus, batch_size=4)
    
    if single_results:
        save_json(single_results, single_results_path)
        review_jsons = extract_json_blocks(single_results_path, "step1_exps.json")
    else:
        review_jsons = []
    
    # ================= 阶段二：局部聚合 (Distillation) =================
    if review_jsons:
        print(f"\n====== [阶段二] 开始局部规则聚类与去重 ======")
        review_texts = [json.dumps(r, ensure_ascii=False) for r in review_jsons]
        review_chunks = chunk_reviews_by_token(review_texts, MODEL_PATH, 10000)

        chunk_prompts = []
        for chunk in review_chunks:
            formatted_summaries = "\n\n".join([f"### Siamese Review {i+1}\n{r}" for i, r in enumerate(chunk)])
            chunk_prompts.append(RULE_DISTILLATION.format(REPORT=formatted_summaries))

        ctx = mp.get_context('spawn')
        with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as executor:
            future = executor.submit(global_worker_batched, "2,3", chunk_prompts, MODEL_PATH)
            chunked_rule_reports = future.result()

        step2_results_path = os.path.join(save_dir, "step2_chunked_rules.json")
        save_json(chunked_rule_reports, step2_results_path)
        chunked_rules_json = extract_json_blocks(step2_results_path, "step2_rules_extracted.json")

        # ================= 阶段三：全局统一定稿 =================
        print(f"\n====== [阶段三] 开始生成 / 迭代全局 Master Checklist ======")
        historical_checklist_path = CHECK_LIST_PATH
        history_checklist_data = "[]"
        
        if os.path.exists(historical_checklist_path):
            try:
                history_data = load_json(historical_checklist_path)
                if history_data:
                    history_checklist_data = json.dumps(history_data, ensure_ascii=False, indent=2)
            except Exception:
                pass

        all_extracted_rules = json.dumps(chunked_rules_json, ensure_ascii=False, indent=2)
        master_prompt = MASTER_CHECKLIST_GEN.format(
            HISTORY_CHECKLIST=history_checklist_data,
            ALL_RULES=all_extracted_rules
        )
        
        with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as executor:
            future = executor.submit(global_worker_batched, "2,3", [master_prompt], MODEL_PATH)
            master_checklist_result = future.result()

        final_raw_path = os.path.join(os.path.dirname(CHECK_LIST_PATH),"raw.json")
        save_json(master_checklist_result, final_raw_path)
        extract_json_blocks(final_raw_path, "check_list.json")
        
        print(f"\n全部完成！孪生对比蒸馏生成的 Checklist 已保存至: {historical_checklist_path}")
        print(f"总耗时: {time.time() - start_time:.2f} 秒")
