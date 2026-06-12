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
from Sys.config import config

def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _extract_gt_ips(dirpath: str) -> list:
    """从 label.json 提取 ground-truth 根因 IP（与 Score_N.get_groundtruth 同逻辑：ranking 前 3）。"""
    label_path = os.path.join(dirpath, "label.json")
    if not os.path.exists(label_path):
        return []
    try:
        labels = load_json(label_path)
    except Exception:
        return []
    if not isinstance(labels, list):
        return []
    labels_sorted = sorted(labels, key=lambda x: x.get("ranking", 999))
    gt_ips = []
    for label in labels_sorted[:3]:
        for node in label.get("abnormal_node", []):
            ip = node.get("ip")
            if ip and ip not in gt_ips:
                gt_ips.append(ip)
    return gt_ips


def check_gt_in_prompt(dirpath: str, prompt: str) -> dict:
    """
    数据/管道诊断：检查 ground-truth IP 是否出现在送入大模型的 prompt 文本中。
    若 gt_ip 根本不在 prompt 里，大模型不可能命中——属于数据标注或管道问题，而非模型问题。
    返回 {dir, gt_ips, missing_ips, all_missing}。
    """
    gt_ips = _extract_gt_ips(dirpath)
    missing = [ip for ip in gt_ips if ip not in prompt]
    return {
        "dir": dirpath,
        "gt_ips": gt_ips,
        "missing_ips": missing,
        "all_missing": bool(gt_ips) and len(missing) == len(gt_ips),
    }

class SkilledAnalyzer:
    def __init__(self, model_path=None, ASCEND_RT_VISIBLE_DEVICES=None, skill_json_path=None, short=None, top_k=None):
        """
        初始化基于 vllm.LLM 的技能型根因分析器。
        所有参数可选，默认从 Sys.config 读取。
        """
        if model_path is None:
            model_path = config.model.model_path
        if ASCEND_RT_VISIBLE_DEVICES is None:
            ASCEND_RT_VISIBLE_DEVICES = config.model.npu_cards
        if skill_json_path is None:
            skill_json_path = config.skills.skills_json
        if short is None:
            short = config.skill.short_mode
        if top_k is None:
            top_k = config.temporal.top_k

        print(f"[{os.getpid()}] 正在初始化 vLLM 引擎，使用的 NPU 卡号为: {ASCEND_RT_VISIBLE_DEVICES}")

        self.model_path = model_path
        self.ASCEND_RT_VISIBLE_DEVICES = ASCEND_RT_VISIBLE_DEVICES
        print("loading skills")
        self.executor=SkillExecutor(skills_folder=config.skills.skills_folder)

        self.skills = self.executor.get_skill_conf()
        self.short=short#short为1则不传入源数据
        self.top_k = top_k      # 传给证据融合层的候选数

        # 将 skill_id 统一转换为 string 方便检索
        print(self.skills)
        for s in self.skills:
            s["skill_id"] = str(s["skill_id"])

        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = self.ASCEND_RT_VISIBLE_DEVICES

        from vllm import LLM, SamplingParams

        self.llm = LLM(
            model=self.model_path,
            tensor_parallel_size=2,
            gpu_memory_utilization=config.model.gpu_memory_utilization,
            max_model_len=config.model.max_model_len,
            trust_remote_code=config.model.trust_remote_code
        )

        self.sampling_params = SamplingParams(
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
            repetition_penalty=config.model.repetition_penalty
        )

    def _load_skill(self, skill_path: str) -> list:
        if not skill_path or not os.path.exists(skill_path):
            print(f"[{os.getpid()}] 警告: 找不到技能库文件 {skill_path}，将使用空技能库。")
            return []
            
        try:
            with open(skill_path, 'r', encoding='utf-8') as f:
                raw_skills = json.load(f)
            
            if not isinstance(raw_skills, list):
                raise ValueError("技能库 JSON 文件的顶层结构必须是 List。")
            
            valid_skills = self._refine_skill_id(raw_skills)
            
            print(f"[{os.getpid()}] 成功从 {skill_path} 加载并校验了 {len(valid_skills)} 个分析技能。")
            return valid_skills
            
        except Exception as e:
            print(f"[{os.getpid()}] 错误: 读取/解析技能库 {skill_path} 失败: {e}")
            return []

    def _refine_skill_id(self, raw_skills: list) -> list:
        seen_ids = set()
        refined_skills = []
        
        max_numeric_id = 0
        for s in raw_skills:
            sid = str(s.get("skill_id", "")).strip()
            if sid.isdigit():
                max_numeric_id = max(max_numeric_id, int(sid))
                
        next_available_id = max_numeric_id + 1

        for skill in raw_skills:
            refined_skill = skill.copy()
            current_id = str(refined_skill.get("skill_id", "")).strip()
            
            if not current_id or current_id in seen_ids:
                new_id = str(next_available_id)
                print(f"[{os.getpid()}] 提示: 发现重复或缺失的 skill_id (原值: '{current_id}'), 已重新编排为: '{new_id}'")
                refined_skill["skill_id"] = new_id
                current_id = new_id
                next_available_id += 1
                
            seen_ids.add(current_id)
            refined_skills.append(refined_skill)
            
        return refined_skills

    def _build_final_prompt(self, original_prompt: str, selected_skill_ids: list, dirpath: str) -> str:
        """构建阶段二：证据融合层产出证据表 + 候选详情；token 充足时填入完整原始数据，注入 Prompt。"""
        from Sys.RootCauseAnalyze.evidence_fusion import build_fused_evidence

        # 融合层产出：证据表 / info 概况 / 候选紧凑详情 / 候选完整原始数据
        skill_ret, info_data, detail_compact, detail_raw = build_fused_evidence(
            node_list=self.executor.get_node_list(dirpath),
            info=self.executor.get_alarminfo(dirpath),
            dirpath=dirpath,
            skill_map=self.executor.skill_map,
            weight_dirpath=config.data.alarm_weights,
            co_occur_path=config.skills.co_occur_rules,
            top_k=self.top_k,
        )

        if not selected_skill_ids:
            skill_ret = "当前未调用任何专家工具，请仅依靠 Info 和候选详情进行推导。"

        tokenizer = self.llm.get_tokenizer()
        max_input_tokens = int(self.llm.llm_engine.model_config.max_model_len * 0.8)

        base_len = len(tokenizer.encode(SKILLED_PROMPT.format(SKILLRET="", INFO="", NODES="")))
        remaining_tokens = max_input_tokens - base_len

        # 证据表（skill_ret）最重要，优先保；info 次之
        skill_tokens = tokenizer.encode(skill_ret)
        if len(skill_tokens) > remaining_tokens:
            skill_ret = tokenizer.decode(skill_tokens[:remaining_tokens]) + "\n...[证据表超长截断]..."
            return SKILLED_PROMPT.format(SKILLRET=skill_ret, INFO="", NODES="")
        remaining_tokens -= len(skill_tokens)

        info_tokens = tokenizer.encode(info_data)
        if len(info_tokens) > remaining_tokens:
            info_data = tokenizer.decode(info_tokens[:remaining_tokens]) + "\n...[Info 截断]..."
            return SKILLED_PROMPT.format(SKILLRET=skill_ret, INFO=info_data, NODES="")
        remaining_tokens -= len(info_tokens)

        # 候选详情：默认紧凑版（证据表已有全部结构化信息），short=0 且 token 极充足时才用 raw
        if self.short:
            nodes_data = detail_compact
        else:
            raw_tokens = len(tokenizer.encode(detail_raw))
            # raw 超过剩余 token 30% 就不打扰 LLM（紧凑版足够）
            nodes_data = detail_raw if raw_tokens <= remaining_tokens * 0.3 else detail_compact
        nodes_tokens = tokenizer.encode(nodes_data)
        if len(nodes_tokens) > remaining_tokens:
            nodes_data = tokenizer.decode(nodes_tokens[:remaining_tokens]) + "\n...[候选详情截断]..."

        return SKILLED_PROMPT.format(SKILLRET=skill_ret, INFO=info_data, NODES=nodes_data)

    def _safe_truncate(self, text: str) -> str:
        tokenizer = self.llm.get_tokenizer()
        tokens = tokenizer.encode(text)
        max_input_tokens = int(self.llm.llm_engine.model_config.max_model_len *0.8)
        if len(tokens) > max_input_tokens:
            return tokenizer.decode(tokens[:max_input_tokens]) + "\n\n...[因超长被截断]..."
        return text

    # [MODIFIED] 增加 target_skill_ids 参数
    def batch_infer(self, dirpaths: list, prompts: list, target_skill_ids: list, batch_size: int = 8) -> list:
        print(f"[{os.getpid()}] 正在执行技能推理 (直接使用传入的技能集 {target_skill_ids}) (共 {len(prompts)} 条, Batch Size: {batch_size})...")

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
            # [MODIFIED] 跳过 Stage 1，直接构建 Final Prompts
            final_prompts = []
            skill_ids_list = []
            retrieval_responses = ["Skipped Retrieval Stage"] * len(prompts) # 使用占位符保持向下兼容结构

            for dirpath, original_p in zip(dirpaths, prompts):
                # 直接使用传入的 target_skill_ids
                skill_ids_list.append(target_skill_ids)
                final_p = self._build_final_prompt(original_p, target_skill_ids, dirpath)
                final_prompts.append(final_p)

            # Stage 2: 模型调用 - 基于 Skill 执行根因分析
            final_responses = vllm_invoke(
                llm=self.llm, 
                inputs=final_prompts, 
                sampling_params=self.sampling_params, 
                desc="Stage 2: Root Cause Analysis",
                b_size=batch_size
            )
            return final_responses, final_prompts, retrieval_responses, skill_ids_list
            
        except Exception as e:
            print(f"\n[Error {os.getpid()}] vLLM 批量推理执行异常: {str(e)}")
            return ["模型未返回有效推理内容或发生异常。"] * len(prompts)


def _find_full_link_file(dirpath: str, filenames: list) -> str:
    """在目录下找到全链路 JSON 文件（兼容两种命名），优先级高于 nodes.json。"""
    for f in filenames:
        if "全链路.json" in f and "pingmesh" in f:
            return f
    return None


def generate_prompts(root_path: str) -> tuple:
    dirpath_list = []
    prompt_list = []
    gt_check_reports = []   # gt_ip 是否在 prompt 中的诊断
    print(f"开始扫描目录 {root_path} 并构造 Prompt...")

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
                # 数据诊断：检查 gt_ip 是否真的在 prompt 里
                gt_check_reports.append(check_gt_in_prompt(dirpath, prompt))
            except Exception as e:
                print(f"\n[错误] 读取/解析目录 {dirpath} 时发生异常: {e}")

    # 汇总并落盘 gt_ip 缺失诊断
    _report_gt_check(root_path, gt_check_reports)

    return dirpath_list, prompt_list


def _report_gt_check(root_path: str, reports: list):
    """打印并保存 gt_ip 缺失诊断：哪些 case 的根因 IP 根本不在 prompt 中。"""
    if not reports:
        return
    no_gt = [r for r in reports if not r["gt_ips"]]
    all_missing = [r for r in reports if r["all_missing"]]
    partial_missing = [r for r in reports if r["missing_ips"] and not r["all_missing"]]

    print("=" * 60)
    print(f"[GT 诊断] 共 {len(reports)} 个 case")
    print(f"  - 无 gt_ip 标注:        {len(no_gt)}")
    print(f"  - gt_ip 全部不在 prompt: {len(all_missing)}  ← 大模型不可能命中")
    print(f"  - gt_ip 部分不在 prompt: {len(partial_missing)}")
    if all_missing:
        print("  [全缺失案例]:")
        for r in all_missing:
            print(f"    {r['dir']}  gt={r['gt_ips']}")
    print("=" * 60)

    out_path = os.path.join(root_path, "gt_in_prompt_check.json")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "total": len(reports),
                "no_gt_label": len(no_gt),
                "all_missing": len(all_missing),
                "partial_missing": len(partial_missing),
                "all_missing_cases": all_missing,
                "partial_missing_cases": partial_missing,
            }, f, ensure_ascii=False, indent=2)
        print(f"[GT 诊断] 详情已保存至: {out_path}")
    except Exception as e:
        print(f"[GT 诊断] 保存失败: {e}")

# [MODIFIED] 增加 target_skill_ids 参数并传递给 batch_infer
def worker_process(worker_id: int, npus: str, dirpaths_chunk: list, prompts_chunk: list, target_skill_ids: list, batch_size: int = 8, short=0, top_k=10) -> dict:
    import os
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    print(f"[Worker {worker_id}] 环境变量已设置 ASCEND_RT_VISIBLE_DEVICES={npus}")
    sleep_time = (worker_id - 1) * 60
    time.sleep(sleep_time)

    analyzer = SkilledAnalyzer(ASCEND_RT_VISIBLE_DEVICES=npus, short=short, top_k=top_k)
    # [MODIFIED] 将 target_skill_ids 传入 batch_infer
    responses, prmpts, ret_ress, skills = analyzer.batch_infer(
        dirpaths=dirpaths_chunk, 
        prompts=prompts_chunk, 
        target_skill_ids=target_skill_ids, 
        batch_size=batch_size
    )
    
    resls=[]
    for dp, res, pmt, ret_res, skill in zip(dirpaths_chunk, responses, prmpts, ret_ress, skills):
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

# [MODIFIED] 增加 target_skill_ids 接收并传递给 worker
def distribute_inference_tasks(dirpath_list: list, prompt_list: list, npu_list: list, target_skill_ids: list, batch_size: int = 8, short=0, top_k=10) -> dict:
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
                    target_skill_ids=target_skill_ids, # [MODIFIED] 注入到子进程
                    batch_size=batch_size,
                    short=short,
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

    p = argparse.ArgumentParser(description="SkilledAnalyzer — Skill 触发的 LLM RCA 推理")
    p.add_argument("--data-root", "-d", default=config.data.nodes_labeled,
                   help="数据根目录 (含 nodes.json + info.json 的 case 目录)")
    p.add_argument("--output-dir", "-o", default=None,
                   help="结果输出子目录名（相对于 results，默认用当前时间戳）")
    p.add_argument("--npu-cards", "-n", default="0,1",
                   help="使用的 NPU 卡号，逗号分隔 (default: 0,1)")
    p.add_argument("--skills", "-s", nargs="*", type=int, default=config.skill.skill_ids,
                   help="启用的 Skill ID 列表 (default: [1,2,3])")
    p.add_argument("--batch-size", "-b", type=int, default=config.model.batch_size,
                   help="批量推理大小 (default: 8)")
    p.add_argument("--short", type=int, default=config.skill.short_mode, choices=[0, 1],
                   help="short=1 不传入原始节点数据省 Token (default: 0)")
    p.add_argument("--top-k", "-k", type=int, default=config.temporal.top_k,
                   help="展示给 LLM 的候选设备数 (default: 10)")
    p.add_argument("--failures-from", default=None,
                   help="只跑指定 failures JSON 中的错案 (debug/回归用)")
    args = p.parse_args()

    target_skill_ids = [str(sid) for sid in args.skills]

    if args.failures_from:
        # 只跑指定错案列表
        dirpaths = get_dirpaths_from_fcases(args.failures_from)
        prompts = generate_partial_prompts(dirpaths)
    else:
        dirpaths, prompts = generate_prompts(args.data_root)

    if prompts:
        print(f"共生成 {len(prompts)} 个任务，Skills={target_skill_ids}...")

        available_npus = [int(x.strip()) for x in args.npu_cards.split(",")]
        start_time = time.time()
        final_results = distribute_inference_tasks(
            dirpath_list=dirpaths,
            prompt_list=prompts,
            npu_list=available_npus,
            target_skill_ids=target_skill_ids,
            batch_size=args.batch_size,
            short=args.short,
            top_k=args.top_k,
        )
        print(f"所有并行推理已完成！总耗时: {time.time() - start_time:.2f} 秒")

        if args.output_dir:
            save_dir = os.path.join(config.data.results, args.output_dir)
        else:
            save_dir = os.path.join(config.data.results, str(int(time.time())))
        os.makedirs(save_dir, exist_ok=True)

        if final_results:
            save_path = os.path.join(save_dir, "res.json")
            save_json(final_results, save_path)
            print(f"最终结果已保存至: {save_path}")
    else:
        print("没有找到需要推理的任务。")