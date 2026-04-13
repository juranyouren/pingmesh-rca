import os, json
import sys
import time
import math
import re
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.append("/home/sbp/lixinyang/pingmesh")
from utils.prompts import PROMPT,SKILLED_PROMPT
from SkillBank.SkillExecutor import SkillExecutor
def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


class SkilledAnalyzer:
    def __init__(self, model_path="/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B", ASCEND_RT_VISIBLE_DEVICES="0,1",skill_json_path="/home/sbp/lixinyang/pingmesh/SkillBank/skills.json",short=0):
        """
        初始化基于 vllm.LLM 的技能型根因分析器
        """
        print(f"[{os.getpid()}] 正在初始化 vLLM 引擎，使用的 NPU 卡号为: {ASCEND_RT_VISIBLE_DEVICES}")
        
        self.model_path = model_path
        self.ASCEND_RT_VISIBLE_DEVICES = ASCEND_RT_VISIBLE_DEVICES
        #self.skills = self._load_skill(skill_json_path)
        print("loading skills")
        self.executor=SkillExecutor()
        
        self.skills = self.executor.get_skill_conf()
        self.short=short#short为1则不传入源数据
        
        # 将 skill_id 统一转换为 string 方便检索
        print(self.skills)
        for s in self.skills:
            s["skill_id"] = str(s["skill_id"])
            
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = self.ASCEND_RT_VISIBLE_DEVICES
        
        from vllm import LLM, SamplingParams
        
        self.llm = LLM(
            model=self.model_path,
            tensor_parallel_size=2,  
            gpu_memory_utilization=0.85,
            max_model_len=int(65536/4),
            trust_remote_code=True
        )
        
        self.sampling_params = SamplingParams(
            temperature=0.6,
            max_tokens=2048,
            repetition_penalty=1.05
        )

    def _load_skill(self, skill_path: str) -> list:
        """
        从外部 JSON 文件加载技能库配置，并调用 _refine_skill_id 验证和重排
        """
        if not skill_path or not os.path.exists(skill_path):
            print(f"[{os.getpid()}] 警告: 找不到技能库文件 {skill_path}，将使用空技能库。")
            return []
            
        try:
            with open(skill_path, 'r', encoding='utf-8') as f:
                raw_skills = json.load(f)
            
            if not isinstance(raw_skills, list):
                raise ValueError("技能库 JSON 文件的顶层结构必须是 List。")
            
            # 调用重排函数，确保每个 skill 都有唯一的 skill_id
            valid_skills = self._refine_skill_id(raw_skills)
            
            print(f"[{os.getpid()}] 成功从 {skill_path} 加载并校验了 {len(valid_skills)} 个分析技能。")
            return valid_skills
            
        except Exception as e:
            print(f"[{os.getpid()}] 错误: 读取/解析技能库 {skill_path} 失败: {e}")
            return []

    def _refine_skill_id(self, raw_skills: list) -> list:
        """
        在挂载技能库时验证是否有重复的 skill_id。
        如果存在重复或缺失，则重新分配一个全局唯一的 ID。
        """
        seen_ids = set()
        refined_skills = []
        
        # 1. 扫描一遍，找出当前全部合法的数字 ID 中的最大值，作为分配新 ID 的基准
        max_numeric_id = 0
        for s in raw_skills:
            sid = str(s.get("skill_id", "")).strip()
            if sid.isdigit():
                max_numeric_id = max(max_numeric_id, int(sid))
                
        next_available_id = max_numeric_id + 1

        # 2. 逐个验证并重新编排
        for skill in raw_skills:
            refined_skill = skill.copy() # 复制一份，避免直接修改原始输入
            current_id = str(refined_skill.get("skill_id", "")).strip()
            
            # 如果 ID 为空，或者已经存在于 seen_ids 中（说明重复了），则重新分配
            if not current_id or current_id in seen_ids:
                new_id = str(next_available_id)
                print(f"[{os.getpid()}] 提示: 发现重复或缺失的 skill_id (原值: '{current_id}'), 已重新编排为: '{new_id}'")
                refined_skill["skill_id"] = new_id
                current_id = new_id
                next_available_id += 1
                
            seen_ids.add(current_id)
            refined_skills.append(refined_skill)
            
        return refined_skills

    def _build_retrieval_prompt(self, original_prompt: str) -> str:
        """构建阶段一：用于检索可用 Skill 的 Prompt"""
        skills_summary = []
        for s in self.skills:
            skills_summary.append(
                f"Skill ID: {s['skill_id']}\n"
                f"Name: {s['skill_name']}\n"
                f"Trigger Logic: {json.dumps(s['trigger_conditions'], ensure_ascii=False)}"
            )
        skills_text = "\n\n".join(skills_summary)
        
        retrieval_prompt = (
            "You are an expert network troubleshooter. Below is the list of available diagnostic skills "
            "and their trigger conditions:\n"
            "=== AVAILABLE SKILLS ===\n"
            f"{skills_text}\n"
            "========================\n\n"
            "Here is the network anomaly information:\n"
            f"{original_prompt[:1500]}...\n\n" # 截断原始 prompt 以防过长，只需让它看关键信息即可
            "Based on the anomaly information and the skill trigger conditions, select the most relevant skill IDs to use. "
            "Output ONLY a JSON list of integers representing the skill_ids (e.g., [1, 2, 5]). Do not output any other text."
        )
        return retrieval_prompt

    def _extract_skill_ids(self, response_text: str) -> list:
        """从阶段一模型返回的内容中提取解析 Skill ID"""
        # DeepSeek-R1 可能带有 <think> 标签，将其剥离
        content = response_text
        if "</think>" in content:
            content = content.split("</think>")[-1]
            
        # 使用正则寻找方括号中的数字列表
        match = re.search(r'\[([\d\s,\'"]+)\]', content)
        if match:
            nums = re.findall(r'\d+', match.group(1))
            return [str(n) for n in nums]
        return []

    def _build_final_prompt(self, original_prompt: str, selected_skill_ids: list, dirpath: str) -> str:
        """构建阶段二：将检索到的 Skill Instructions 注入原始 Prompt 进行最终推理，并进行 Token 级安全截断"""
        # 2. 从指定目录读取 nodes 和 info 数据
        nodes_path = os.path.join(dirpath, "nodes.json")
        info_path = os.path.join(dirpath, "info.json")
        
        nodes_data = "{}"
        info_data = "{}"
        
        if os.path.exists(nodes_path):
            with open(nodes_path, 'r', encoding='utf-8') as f:
                nodes_data = f.read()
                
        if os.path.exists(info_path):
            with open(info_path, 'r', encoding='utf-8') as f:
                info_data = f.read()

        # 3. 执行选中的 Skill 并收集诊断结果
        skill_ret = "当前未调用任何专家工具，请仅依靠 Info 和 Nodes 数据进行推导。"
        if selected_skill_ids:
            selected_skills = [s for s in self.skills if s["skill_id"] in selected_skill_ids]
            if selected_skills:
                instructions = []
                for s in selected_skills:
                    if s.get("python_executor"):
                        # 执行 Python 脚本并获取返回字符串
                        exec_result = self.executor.execute(s["python_executor"], dirpath)
                        instructions.append(f"[{s['skill_name']} 执行结果]:\n{exec_result}")
                    else:
                        instructions.append(f"[{s['skill_name']} 规则要求]:\n" + json.dumps(s['execution_instructions'], ensure_ascii=False, indent=2))
                skill_ret = f"{chr(10).join(instructions)}\n"

        # 4. Token 级智能截断处理
        tokenizer = self.llm.get_tokenizer()
        max_input_tokens = int(self.llm.llm_engine.model_config.max_model_len * 0.8)

        # 预计算：如果不放入 Info 和 Nodes，模板和 Skill Results 会占用的 Token 数
        base_prompt_empty = SKILLED_PROMPT.format(SKILLRET=skill_ret, INFO="", NODES="")
        base_tokens = tokenizer.encode(base_prompt_empty)
        base_len = len(base_tokens)

        # 留给 Info 和 Nodes 的 Token 额度
        remaining_tokens = max_input_tokens - base_len

        # 极端情况：Skill 数据本身就爆了（通常说明你的 Python 脚本吐了未经清洗的脏数据）
        if remaining_tokens <= 0:
            truncated_skill = tokenizer.decode(base_tokens[:max_input_tokens])
            return truncated_skill + "\n[系统警告：工具输出数据过长，上下文已被强制截断！]"

        # 分别计算 Info 和 Nodes 的 Token
        info_tokens = tokenizer.encode(info_data)
        nodes_tokens = tokenizer.encode(nodes_data)

        # 如果总体超长，执行分级截断
        if len(info_tokens) + len(nodes_tokens) > remaining_tokens:
            # 策略：保障 Info 最多占用剩余空间的 40%，剩下的全给 Nodes
            max_info_tokens = int(remaining_tokens * 0.4)
            
            if len(info_tokens) > max_info_tokens:
                info_data = tokenizer.decode(info_tokens[:max_info_tokens]) + "\n...[Info 数据因超长被截断]..."
                remaining_for_nodes = remaining_tokens - max_info_tokens
            else:
                remaining_for_nodes = remaining_tokens - len(info_tokens)
                
            if len(nodes_tokens) > remaining_for_nodes:
                nodes_data = tokenizer.decode(nodes_tokens[:remaining_for_nodes]) + "\n...[Nodes 数据因超长被截断]..."

        # 5. 格式化最终填充完毕的 Prompt
        final_prompt = SKILLED_PROMPT.format(
            SKILLRET=skill_ret,
            INFO=info_data,
            NODES=nodes_data
        )

        return final_prompt

    def _safe_truncate(self, text: str) -> str:
        """兜底的截断方法"""
        tokenizer = self.llm.get_tokenizer()
        tokens = tokenizer.encode(text)
        max_input_tokens = int(self.llm.llm_engine.model_config.max_model_len *0.8)
        if len(tokens) > max_input_tokens:
            return tokenizer.decode(tokens[:max_input_tokens]) + "\n\n...[因超长被截断]..."
        return text

    def batch_infer(self, dirpaths: list, prompts: list, batch_size: int = 8) -> list:
        print(f"[{os.getpid()}] 正在执行技能检索与推理 (共 {len(prompts)} 条, Batch Size: {batch_size})...")

        def vllm_invoke(llm, inputs:list, sampling_params, desc="Inferring", b_size=1):
            from tqdm import tqdm
            all_responses = []
            for i in tqdm(range(0, len(inputs), b_size), desc=desc):
                batch_inputs = inputs[i:i + b_size]
                applied_prompts = [[
                    {'role': 'user', 'content': prompt}
                ] for prompt in batch_inputs]
                outputs_w_prompts = llm.chat(applied_prompts, sampling_params)
                all_responses.extend([item.outputs[0].text for item in outputs_w_prompts])
            return all_responses
            
        try:
            # Stage 1: 模型调用 - 检索 Skill
            retrieval_prompts = [self._build_retrieval_prompt(p) for p in prompts]
            retrieval_responses = vllm_invoke(
                llm=self.llm, 
                inputs=retrieval_prompts, 
                sampling_params=self.sampling_params, 
                desc="Stage 1: Retrieving Skills",
                b_size=batch_size
            )
            
            # 组装带 Skill 的最终 Prompt
            final_prompts = []
            skill_ids_list=[]
            for dirpath, original_p, ret_res in zip(dirpaths, prompts, retrieval_responses):
                skill_ids = self._extract_skill_ids(ret_res)
                skill_ids_list.append(skill_ids)
                final_p = self._build_final_prompt(original_p, skill_ids,dirpath)
                final_prompts.append(final_p)

            # Stage 2: 模型调用 - 基于 Skill 执行根因分析
            final_responses = vllm_invoke(
                llm=self.llm, 
                inputs=final_prompts, 
                sampling_params=self.sampling_params, 
                desc="Stage 2: Root Cause Analysis",
                b_size=batch_size
            )
            return final_responses,final_prompts,retrieval_responses,skill_ids_list
            
        except Exception as e:
            print(f"\n[Error {os.getpid()}] vLLM 批量推理执行异常: {str(e)}")
            return ["模型未返回有效推理内容或发生异常。"] * len(prompts)


def generate_prompts(root_path: str) -> tuple:
    dirpath_list = []
    prompt_list = []
    print(f"开始扫描目录 {root_path} 并构造 Prompt...")
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        if "nodes.json" in filenames and "info.json" in filenames:
            node_path = os.path.join(dirpath, "nodes.json")
            info_path = os.path.join(dirpath, "info.json")
            try:
                node = load_json(node_path)
                info = load_json(info_path)
                prompt = PROMPT.format(NODES=node, INFO=info)
                dirpath_list.append(dirpath)
                prompt_list.append(prompt)
            except Exception as e:
                print(f"\n[错误] 读取/解析目录 {dirpath} 时发生异常: {e}")
                
    return dirpath_list, prompt_list

def worker_process(worker_id: int, npus: str, dirpaths_chunk: list, prompts_chunk: list, batch_size: int = 8,short=0) -> dict:
    import os
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    print(f"[Worker {worker_id}] 环境变量已设置 ASCEND_RT_VISIBLE_DEVICES={npus}")
    sleep_time = (worker_id - 1) * 60
    time.sleep(sleep_time)
    
    # 替换为 SkilledAnalyzer
    analyzer = SkilledAnalyzer(ASCEND_RT_VISIBLE_DEVICES=npus,short=short)
    responses,prmpts,ret_ress,skills = analyzer.batch_infer(dirpaths=dirpaths_chunk, prompts=prompts_chunk, batch_size=batch_size)
    
    resls=[]
    
    for dp, res,pmt,ret_res,skill in zip(dirpaths_chunk, responses,prmpts,ret_ress,skills):
        
        clean_res = res.strip() if isinstance(res, str) else str(res)
        result_dict = {
            "dir":dp,
            "ret_response":ret_res,
            "skills_used":skill,
            "prompt":pmt,
            "response":clean_res,
        }
        resls.append(result_dict)

    
    return resls

def distribute_inference_tasks(dirpath_list: list, prompt_list: list, npu_list: list, batch_size: int = 8,short=0) -> dict:
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

    all_results = []
    ctx = mp.get_context('spawn')
    
    with ProcessPoolExecutor(max_workers=num_instances, mp_context=ctx) as executor:
        futures = []
        for i in range(num_instances):
            if i < len(dir_chunks) and len(dir_chunks[i]) > 0:
                print(f"正在提交任务给实例 {i+1} (NPU: {npu_groups[i]}, 任务数: {len(dir_chunks[i])})...")
                future = executor.submit(
                    worker_process, 
                    worker_id=i+1, 
                    npus=npu_groups[i], 
                    dirpaths_chunk=dir_chunks[i], 
                    prompts_chunk=prompt_chunks[i],
                    batch_size=batch_size,
                    short=short
                )
                futures.append(future)

        for future in as_completed(futures):
            try:
                res_ls = future.result()
                all_results.extend(res_ls)
            except Exception as exc:
                print(f"某个子进程执行过程中发生了异常: {exc}")

    return all_results

def generate_partial_prompts(dirpaths:list) :
    prompt_list = []
    for dirpath  in dirpaths:
        node_path = os.path.join(dirpath, "nodes.json")
        info_path = os.path.join(dirpath, "info.json")
        try:
            node = load_json(node_path)
            info = load_json(info_path)
            prompt = PROMPT.format(NODES=node, INFO=info)
            prompt_list.append(prompt)
        except Exception as e:
            print(f"\n[错误] 读取/解析目录 {dirpath} 时发生异常: {e}")
                
    return prompt_list

def get_dirpaths_from_fcases(fcase_path):
    fcases=load_json(fcase_path)
    res=[]

    for case in fcases:
        dir=case.get("name")
        res.append(dir)
    return res

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root_path", type=str, required=True, help="输入数据的根目录")
    parser.add_argument("--save_dir", type=str, required=True, help="结果保存的目录")
    args = parser.parse_args()

    # 替换原有的硬编码配置
    available_npus = [0,1,2, 3, 4, 5, 6, 7]
    dirpaths, prompts = generate_prompts(args.root_path)
    

    if prompts:
        print(f"共生成 {len(prompts)} 个任务，开始分配并行推理...")
        start_time = time.time()
        final_results = distribute_inference_tasks(
            dirpath_list=dirpaths, 
            prompt_list=prompts, 
            npu_list=available_npus,
            batch_size=8,
            short=0
        )
        end_time = time.time()
        
        os.makedirs(args.save_dir, exist_ok=True)
        if final_results:
            save_path = os.path.join(args.save_dir, "res.json")
            save_json(final_results, save_path)

    