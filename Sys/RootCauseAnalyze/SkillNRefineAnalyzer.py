import os, json
import sys
import time
import math
import re
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.append("/home/sbp/lixinyang/pingmesh")
# 注意：这里需要导入您刚新增的 REFINE_PROMPT
from utils.prompts import PROMPT, SKILLED_PROMPT, REFINE_PROMPT
from SkillBank.SkillExecutor import SkillExecutor

def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

class SkillNRefineAnalyzer:
    def __init__(
        self,
        model_path="/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B",
        ASCEND_RT_VISIBLE_DEVICES="0,1",
        checklist_path="/home/sbp/lixinyang/pingmesh/SkillBank/check_list.json",
        short=0,
        skill_ids_to_use=None,  # <--- 在此暴露配置
        top_k=10,
    ):
        """
        初始化具有【固定技能调用】+【Refine 审查层】双阶段推理的分析器
        """
        print(f"[{os.getpid()}] 正在初始化 vLLM 引擎，使用的 NPU 卡号为: {ASCEND_RT_VISIBLE_DEVICES}")

        self.model_path = model_path
        self.ASCEND_RT_VISIBLE_DEVICES = ASCEND_RT_VISIBLE_DEVICES
        self.short = short
        self.top_k = top_k

        # 接收外部传入的技能 ID 列表，如果为空则默认使用 [1]
        self.skill_ids_to_use = skill_ids_to_use if skill_ids_to_use is not None else [1]

        # 1. 加载技能库执行器
        print(f"[{os.getpid()}] Loading skills...")
        self.executor = SkillExecutor()
        self.skills = self.executor.get_skill_conf()
        for s in self.skills:
            s["skill_id"] = str(s["skill_id"])

        # 2. 加载 Refine 层的军规 Checklist
        self.checklist_text = self._load_checklist(checklist_path)
            
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
            max_tokens=3072, 
            repetition_penalty=1.05
        )

    def _load_checklist(self, path: str) -> str:
        """安全加载 Master Checklist"""
        if os.path.exists(path):
            try:
                data = load_json(path)
                print(f"[{os.getpid()}] 成功加载 Refine Checklist: 包含 {len(data)} 条核心规则。")
                return json.dumps(data, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[{os.getpid()}] 警告: Checklist 读取异常，将使用空规则: {e}")
        else:
            print(f"[{os.getpid()}] 提示: 未找到 Checklist 文件 {path}，Refine 层将在无历史规则下裸跑。")
        return "[]"

    def _prepare_context(self, dirpath: str, selected_skill_ids: list) -> tuple:
        """通过证据融合层把三个 Skill 输出压缩为紧凑三段，并保留 Token 安全网。"""
        from Sys.RootCauseAnalyze.evidence_fusion import build_fused_evidence
        try:
            from Sys.config import config
            weight_dirpath = config.data.alarm_weights
            co_occur_path = config.skills.co_occur_rules
        except Exception:
            weight_dirpath, co_occur_path = None, None

        skill_ret, info_data, detail_compact, detail_raw = build_fused_evidence(
            node_list=self.executor.get_node_list(dirpath),
            info=self.executor.get_alarminfo(dirpath),
            dirpath=dirpath,
            skill_map=self.executor.skill_map,
            weight_dirpath=weight_dirpath,
            co_occur_path=co_occur_path,
            top_k=self.top_k,
        )

        if not selected_skill_ids:
            skill_ret = "当前未调用任何专家工具，请仅依靠 Info 和候选详情进行推导。"

        # ── Token 级安全网：证据表 > info > 候选详情（token 充足优先完整原始数据）──
        tokenizer = self.llm.get_tokenizer()
        max_input_tokens = int(self.llm.llm_engine.model_config.max_model_len * 0.7)

        base_prompt_empty = SKILLED_PROMPT.format(SKILLRET="", INFO="", NODES="")
        remaining_tokens = max_input_tokens - len(tokenizer.encode(base_prompt_empty))

        skill_tokens = tokenizer.encode(skill_ret)
        if len(skill_tokens) > remaining_tokens:
            return tokenizer.decode(skill_tokens[:remaining_tokens]) + "\n...[证据表超长截断]...", "", ""
        remaining_tokens -= len(skill_tokens)

        info_tokens = tokenizer.encode(info_data)
        if len(info_tokens) > remaining_tokens:
            info_data = tokenizer.decode(info_tokens[:remaining_tokens]) + "\n...[Info 截断]..."
            return skill_ret, info_data, ""
        remaining_tokens -= len(info_tokens)

        # 默认紧凑版（证据表已有全部结构化信息），raw 超过剩余 30% 就不侵扰 LLM
        raw_tokens = len(tokenizer.encode(detail_raw))
        nodes_data = detail_raw if raw_tokens <= remaining_tokens * 0.3 else detail_compact
        nodes_tokens = tokenizer.encode(nodes_data)
        if len(nodes_tokens) > remaining_tokens:
            nodes_data = tokenizer.decode(nodes_tokens[:remaining_tokens]) + "\n...[候选详情截断]..."

        return skill_ret, info_data, nodes_data


    def _build_safe_refine_prompt(self, skill_ret: str, info_data: str, nodes_data: str, draft_res: str) -> str:
        """专为 Refine 层设计的极限截断组装器，确保绝不爆 Token"""
        tokenizer = self.llm.get_tokenizer()
        
        # 1. 对初稿 (Draft) 进行无情压缩
        compressed_draft = draft_res
        try:
            # 尝试把 Draft 解析为 JSON，只保留 reasoning 和 ip
            draft_json = re.search(r'```json\s*(.*?)\s*```', draft_res, re.DOTALL | re.IGNORECASE)
            if draft_json:
                parsed_draft = json.loads(draft_json.group(1))
                compressed_draft = json.dumps({
                    "reasoning": parsed_draft.get("reasoning", "未提取到思路"),
                    "ip": parsed_draft.get("ip", [])
                }, ensure_ascii=False)
        except Exception:
            # 如果解析失败，强行截断初稿前 1000 个字符
            compressed_draft = draft_res[:1000] + "...[初稿部分超长截断]"

        # 2. 计算不可妥协的 Token 消耗 (模板 + 军规 + 工具结果 + 压缩后的初稿)
        base_prompt_empty = REFINE_PROMPT.format(
            SKILLRET=skill_ret, INFO="", NODES="", 
            DRAFT_RESULT=compressed_draft, DYNAMIC_CHECKLIST=self.checklist_text
        )
        base_tokens = tokenizer.encode(base_prompt_empty)
        
        # 3. 计算留给 Info 和 Nodes 的极限空间
        # 留 20% 的余量给大模型生成输出
        max_total_tokens = int(self.llm.llm_engine.model_config.max_model_len * 0.8)
        remaining_tokens = max_total_tokens - len(base_tokens)

        # 极端情况：连基础模板都塞不下了
        if remaining_tokens <= 0:
            return tokenizer.decode(base_tokens[:max_total_tokens]) + "\n[严重警告：上下文已爆，强制腰斩！]"

        # 4. 对 Info 和 Nodes 进行二次极限截断
        info_tokens = tokenizer.encode(info_data)
        nodes_tokens = tokenizer.encode(nodes_data)

        if len(info_tokens) + len(nodes_tokens) > remaining_tokens:
            # Refine 层更看重 Info（全局告警），给 Info 更多权重 (50%)
            max_info_tokens = int(remaining_tokens * 0.5)
            
            if len(info_tokens) > max_info_tokens:
                safe_info = tokenizer.decode(info_tokens[:max_info_tokens]) + "\n...[Info 极限截断]..."
                remaining_for_nodes = remaining_tokens - max_info_tokens
            else:
                safe_info = info_data
                remaining_for_nodes = remaining_tokens - len(info_tokens)
                
            if len(nodes_tokens) > remaining_for_nodes:
                safe_nodes = tokenizer.decode(nodes_tokens[:remaining_for_nodes]) + "\n...[Nodes 极限截断]..."
            else:
                safe_nodes = nodes_data
        else:
            safe_info = info_data
            safe_nodes = nodes_data

        # 5. 安全组装最终的 Refine Prompt
        return REFINE_PROMPT.format(
            SKILLRET=skill_ret,
            INFO=safe_info,
            NODES=safe_nodes,
            DRAFT_RESULT=compressed_draft,
            DYNAMIC_CHECKLIST=self.checklist_text
        )

    def batch_infer(self, dirpaths: list, prompts: list, batch_size: int = 8) -> tuple:
        print(f"[{os.getpid()}] 正在执行 [初稿生成 -> Refine审查] 流水线 (共 {len(prompts)} 条, 使用 Skill IDs: {self.skill_ids_to_use})...")

        def vllm_invoke(llm, inputs: list, sampling_params, desc="Inferring", b_size=1):
            from tqdm import tqdm
            all_responses = []
            for i in tqdm(range(0, len(inputs), b_size), desc=desc):
                batch_inputs = inputs[i:i + b_size]
                applied_prompts = [[{'role': 'user', 'content': prompt}] for prompt in batch_inputs]
                outputs_w_prompts = llm.chat(applied_prompts, sampling_params)
                all_responses.extend([item.outputs[0].text for item in outputs_w_prompts])
            return all_responses
            
        try:
            # ================== Stage 1: 准备上下文并生成初稿 (Draft) ==================
            draft_prompts = []
            contexts = []  
            
            for dirpath in dirpaths:
                # 使用初始化时挂载的 self.skill_ids_to_use
                skill_ret, info_data, nodes_data = self._prepare_context(dirpath, self.skill_ids_to_use)
                draft_p = SKILLED_PROMPT.format(SKILLRET=skill_ret, INFO=info_data, NODES=nodes_data)
                
                draft_prompts.append(draft_p)
                contexts.append((skill_ret, info_data, nodes_data))
                
            draft_responses = vllm_invoke(
                llm=self.llm, 
                inputs=draft_prompts, 
                sampling_params=self.sampling_params, 
                desc="Stage 1: Generating Drafts",
                b_size=batch_size
            )
            

            # ================== Stage 2: 注入 Checklist 并执行 Refine ==================
            refine_prompts = []
            for (skill_ret, info_data, nodes_data), draft_res in zip(contexts, draft_responses):
                refine_p = self._build_safe_refine_prompt(
                    skill_ret=skill_ret,
                    info_data=info_data,
                    nodes_data=nodes_data,
                    draft_res=draft_res
                )
                refine_prompts.append(refine_p)
                
            final_responses = vllm_invoke(
                llm=self.llm, 
                inputs=refine_prompts, 
                sampling_params=self.sampling_params, 
                desc="Stage 2: Refining Results",
                b_size=batch_size
            )
            
            return final_responses, draft_responses, draft_prompts, refine_prompts
            
        except Exception as e:
            print(f"\n[Error {os.getpid()}] vLLM 批量推理执行异常: {str(e)}")
            return (
                ["发生异常"] * len(prompts), ["发生异常"] * len(prompts),
                ["异常"] * len(prompts), ["异常"] * len(prompts)
            )

def worker_process(worker_id: int, npus: str, dirpaths_chunk: list, prompts_chunk: list, batch_size: int = 8, short=0, skill_ids_to_use=None, top_k=10) -> list:
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    print(f"[Worker {worker_id}] 环境变量已设置 ASCEND_RT_VISIBLE_DEVICES={npus}")
    time.sleep((worker_id - 1) * 60)

    # 初始化分析器时传入 skill_ids_to_use
    analyzer = SkillNRefineAnalyzer(
        ASCEND_RT_VISIBLE_DEVICES=npus,
        short=short,
        skill_ids_to_use=skill_ids_to_use,
        top_k=top_k,
    )
    
    responses, drafts, draft_pmts, refine_pmts = analyzer.batch_infer(
        dirpaths=dirpaths_chunk, 
        prompts=prompts_chunk, 
        batch_size=batch_size
    )
    
    resls = []
    for dp, res, draft, d_pmt, r_pmt in zip(dirpaths_chunk, responses, drafts, draft_pmts, refine_pmts):
        clean_res = str(res).strip()
        clean_draft = str(draft).strip()
        
        result_dict = {
            "dir": dp,
            "draft_prompt": d_pmt,
            "draft_response": clean_draft, 
            "refine_prompt": r_pmt,
            "response": clean_res          
        }
        resls.append(result_dict)

    return resls

def distribute_inference_tasks(dirpath_list: list, prompt_list: list, npu_list: list, batch_size: int = 8, short=0, skill_ids_to_use=None, top_k=10) -> list:
    total_tasks = len(prompt_list)
    if total_tasks == 0: return []

    num_instances = len(npu_list) // 2
    if num_instances == 0: raise ValueError("卡数不足！每个实例至少需要 2 张 NPU 卡。")

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
                future = executor.submit(
                    worker_process, 
                    worker_id=i+1, 
                    npus=npu_groups[i], 
                    dirpaths_chunk=dir_chunks[i], 
                    prompts_chunk=prompt_chunks[i],
                    batch_size=batch_size,
                    short=short,
                    skill_ids_to_use=skill_ids_to_use, # <--- 继续透传
                    top_k=top_k
                )
                futures.append(future)

        for future in as_completed(futures):
            try:
                res_ls = future.result()
                all_results.extend(res_ls)
            except Exception as exc:
                print(f"某个子进程执行过程中发生了异常: {exc}")

    return all_results

def _find_full_link_file(dirpath: str, filenames: list) -> str:
    """在目录下找到全链路 JSON 文件（兼容两种命名），优先级高于 nodes.json。"""
    for f in filenames:
        if "全链路.json" in f and "pingmesh" in f:
            return f
    return None


def generate_prompts(root_path: str) -> tuple:
    dirpath_list = []
    prompt_list = []
    print(f"开始扫描目录 {root_path} 并构造基础 Prompt...")

    for dirpath, dirnames, filenames in os.walk(root_path):
        info_file = "info.json" in filenames
        full_link_file = _find_full_link_file(dirpath, filenames)
        if info_file and full_link_file:
            node_path = os.path.join(dirpath, full_link_file)
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

if __name__ == "__main__":
    import argparse

    # 尝试从 config 读取默认值，不存在就用硬编码兜底
    try:
        from Sys.config import config
        _data = config.data.nodes_labeled
        _skills = config.skill.skill_ids
        _short = config.skill.short_mode
        _batch = config.model.batch_size
    except Exception:
        _data = "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"
        _skills = [1, 2]
        _short = 0
        _batch = 8

    p = argparse.ArgumentParser(description="SkillNRefineAnalyzer — Skill + Refine 双阶段 RCA 推理")
    p.add_argument("--data-root", "-d", default=_data,
                   help="数据根目录")
    p.add_argument("--output-dir", "-o", default=None,
                   help="结果输出子目录名（相对于 results，默认用当前时间戳）")
    p.add_argument("--npu-cards", "-n", default="0,1,2,3,4,5,6,7",
                   help="使用的 NPU 卡号，逗号分隔 (default: 0,1,2,3,4,5,6,7)")
    p.add_argument("--skills", "-s", nargs="*", type=int, default=_skills,
                   help="启用的 Skill ID 列表 (default: [1,2,3])")
    p.add_argument("--batch-size", "-b", type=int, default=_batch,
                   help="批量推理大小 (default: 8)")
    p.add_argument("--short", type=int, default=_short, choices=[0, 1],
                   help="short=1 不传入原始节点数据省 Token (default: 0)")
    p.add_argument("--top-k", "-k", type=int, default=10,
                   help="展示给 LLM 的候选设备数 (default: 10)")
    args = p.parse_args()

    available_npus = [int(x.strip()) for x in args.npu_cards.split(",")]

    dirpaths, prompts = generate_prompts(args.data_root)

    if prompts:
        print(f"共生成 {len(prompts)} 个任务，Skills={args.skills}...")
        start_time = time.time()

        final_results = distribute_inference_tasks(
            dirpath_list=dirpaths,
            prompt_list=prompts,
            npu_list=available_npus,
            batch_size=args.batch_size,
            short=args.short,
            skill_ids_to_use=args.skills,
            top_k=args.top_k,
        )

        print(f"所有并行推理已完成！总耗时: {time.time() - start_time:.2f} 秒")

        try:
            save_dir = os.path.join(config.data.results, args.output_dir if args.output_dir else str(int(time.time())))
        except Exception:
            save_dir = os.path.join("/home/sbp/lixinyang/pingmesh/data/res", args.output_dir if args.output_dir else str(int(time.time())))
        os.makedirs(save_dir, exist_ok=True)

        if final_results:
            save_path = os.path.join(save_dir, "res.json")
            save_json(final_results, save_path)
            print(f"最终结果已保存至: {save_path}")
            print("对比 draft_response 和 response 评估 Refine 层干预效果")
    else:
        print("没有找到需要推理的任务。")