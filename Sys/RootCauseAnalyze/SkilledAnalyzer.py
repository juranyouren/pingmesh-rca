import os, json
import sys
import time
import math
import re
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.append("/home/sbp/lixinyang/pingmesh")
from prompts import PROMPT, SKILLED_PROMPT
from Sys.config import config
from Sys.RootCauseAnalyze.skills.provider import BuiltinSkillProvider
from Sys.utils.case_utils import find_full_link_file, read_gt_ips
from Sys.utils.io_utils import load_json, save_json


def _extract_gt_ips(dirpath: str) -> list:
    """Extract ground-truth IPs from label.json for diagnostics/evaluation."""
    return read_gt_ips(dirpath)


def check_gt_in_prompt(dirpath: str, prompt: str) -> dict:
    """Check whether ground-truth IPs appear in the prompt text."""
    gt_ips = _extract_gt_ips(dirpath)
    missing = [ip for ip in gt_ips if ip not in prompt]
    return {
        "dir": dirpath,
        "gt_ips": gt_ips,
        "missing_ips": missing,
        "all_missing": bool(gt_ips) and len(missing) == len(gt_ips),
    }

class SkilledAnalyzer:
    def __init__(self, model_path=None, ASCEND_RT_VISIBLE_DEVICES=None, skill_json_path=None, short=None, top_k=None,
                 confidence_gate=False, confidence_high_margin=15.0, confidence_agreement_margin=8.0,
                 summarize_nodes=False, summary_model_path=None, summary_npu_cards=None,
                 summary_max_tokens=1024):
        """
        Initialize the skill-guided RCA analyzer.
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

        print(f"[{os.getpid()}] vLLM 将按需初始化，使用的 NPU 卡号为: {ASCEND_RT_VISIBLE_DEVICES}")

        self.model_path = model_path
        self.ASCEND_RT_VISIBLE_DEVICES = ASCEND_RT_VISIBLE_DEVICES
        print("loading skills")
        self.executor = BuiltinSkillProvider()

        self.skills = self.executor.get_skill_conf()
        self.short=short
        self.top_k = top_k
        self.confidence_gate_enabled = bool(confidence_gate)
        self.confidence_high_margin = float(confidence_high_margin)
        self.confidence_agreement_margin = float(confidence_agreement_margin)
        self.summarize_nodes_enabled = bool(summarize_nodes)
        self.summary_model_path = summary_model_path or os.environ.get("PINGMESH_SUMMARY_MODEL_PATH", "")
        self.summary_npu_cards = summary_npu_cards or os.environ.get("PINGMESH_SUMMARY_NPU_CARDS", ASCEND_RT_VISIBLE_DEVICES.split(",")[0])
        self.summary_max_tokens = int(summary_max_tokens)
        self.llm = None
        self.sampling_params = None

        # 将 skill_id 统一转换为 string，方便检索。
        print(self.skills)
        for s in self.skills:
            s["skill_id"] = str(s["skill_id"])

        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = self.ASCEND_RT_VISIBLE_DEVICES

    def _summarize_candidate_detail(self, candidate_detail: str) -> str:
        if not self.summarize_nodes_enabled:
            return candidate_detail
        if not self.summary_model_path:
            raise ValueError("summarize_nodes is enabled but PINGMESH_SUMMARY_MODEL_PATH/--summary-model-path is not set")
        from Sys.RootCauseAnalyze.gate.node_summarizer import VllmNodeSummarizer, summarize_nodes_with

        with VllmNodeSummarizer(
            model_path=self.summary_model_path,
            npu_cards=self.summary_npu_cards,
            max_tokens=self.summary_max_tokens,
        ) as summarizer:
            return summarize_nodes_with(candidate_detail, summarize_batch=summarizer.summarize_batch)

    def _ensure_llm(self):
        """Lazy init vLLM so confidence-gated all-bypass workers avoid model loading."""
        if self.llm is not None and self.sampling_params is not None:
            return

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

    def _build_final_prompt(self, original_prompt: str, selected_skill_ids: list, dirpath: str):
        """Return (final_prompt, skill_ips, gate)."""
        from Sys.RootCauseAnalyze.gate.decision import assess_gate
        from Sys.RootCauseAnalyze.gate.evidence import build_fused_evidence

        skill_ret, info_data, detail_compact, detail_raw, skill_ips = build_fused_evidence(
            node_list=self.executor.get_node_list(dirpath),
            info=self.executor.get_alarminfo(dirpath),
            dirpath=dirpath,
            skill_map=self.executor.skill_map,
            weight_dirpath=config.data.alarm_weights,
            top_k=self.top_k,
        )
        detail_for_llm = self._summarize_candidate_detail(detail_compact)

        if not selected_skill_ids:
            skill_ret = "No deterministic skill was selected; infer from info and candidate details only."

        gate = {
            "enabled": False,
            "decision": "invoke_llm",
            "reason": "confidence_gate_disabled",
            "recommended_ips": skill_ips[:3],
        }
        if self.confidence_gate_enabled and selected_skill_ids:
            gate = assess_gate(
                skill_ret,
                high_margin=self.confidence_high_margin,
                agreement_margin=self.confidence_agreement_margin,
            )
            if gate.get("decision") in ("bypass_llm", "operator_review"):
                gate_tag = "CONFIDENCE_GATE_BYPASS" if gate.get("decision") == "bypass_llm" else "CONFIDENCE_GATE_OPERATOR_REVIEW"
                final_prompt = (
                    f"{gate_tag}\n"
                    "# 故障概况\n"
                    f"{info_data}\n\n"
                    "# 算法证据\n"
                    f"{skill_ret}\n\n"
                    "# 候选设备详情\n"
                    f"{detail_for_llm}"
                )
                return final_prompt, skill_ips, gate

        if self.summarize_nodes_enabled:
            return SKILLED_PROMPT.format(SKILLRET=skill_ret, INFO=info_data, NODES=detail_for_llm), skill_ips, gate

        self._ensure_llm()
        tokenizer = self.llm.get_tokenizer()
        max_input_tokens = int(self.llm.llm_engine.model_config.max_model_len * 0.8)

        base_len = len(tokenizer.encode(SKILLED_PROMPT.format(SKILLRET="", INFO="", NODES="")))
        remaining_tokens = max_input_tokens - base_len

        skill_tokens = tokenizer.encode(skill_ret)
        if len(skill_tokens) > remaining_tokens:
            skill_ret = tokenizer.decode(skill_tokens[:remaining_tokens]) + "\n...[证据表过长截断]..."
            return SKILLED_PROMPT.format(SKILLRET=skill_ret, INFO="", NODES=""), skill_ips, gate
        remaining_tokens -= len(skill_tokens)

        info_tokens = tokenizer.encode(info_data)
        if len(info_tokens) > remaining_tokens:
            info_data = tokenizer.decode(info_tokens[:remaining_tokens]) + "\n...[Info 鎴柇]..."
            return SKILLED_PROMPT.format(SKILLRET=skill_ret, INFO=info_data, NODES=""), skill_ips, gate
        remaining_tokens -= len(info_tokens)

        # 候选详情始终使用结构化 JSON (detail_compact)，token 不够时截断。
        nodes_data = detail_for_llm
        nodes_tokens = tokenizer.encode(nodes_data)
        if len(nodes_tokens) > remaining_tokens:
            nodes_data = tokenizer.decode(nodes_tokens[:remaining_tokens]) + "\n...[候选详情截断]..."

        return SKILLED_PROMPT.format(SKILLRET=skill_ret, INFO=info_data, NODES=nodes_data), skill_ips, gate

    def _safe_truncate(self, text: str) -> str:
        tokenizer = self.llm.get_tokenizer()
        tokens = tokenizer.encode(text)
        max_input_tokens = int(self.llm.llm_engine.model_config.max_model_len *0.8)
        if len(tokens) > max_input_tokens:
            return tokenizer.decode(tokens[:max_input_tokens]) + "\n\n...[因超长被截断]..."
        return text

    # [MODIFIED] 增加 target_skill_ids 参数
    def batch_infer(self, dirpaths: list, prompts: list, target_skill_ids: list, batch_size: int = 8) -> list:
        """返回 (responses, prompts, retrieval_responses, skill_ids_list, skill_ips_list, gt_ips_list, confidence_gates)."""
        print(f"[{os.getpid()}] 正在执行技能推理(直接使用传入的技能集 {target_skill_ids}) (共 {len(prompts)} 条, Batch Size: {batch_size})...")

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
            from Sys.RootCauseAnalyze.gate.response import make_bypass_response

            final_prompts = []
            final_responses = [None] * len(prompts)
            skill_ids_list = []
            skill_ips_list = []
            gt_ips_list = []
            confidence_gates = []
            retrieval_responses = ["Skipped Retrieval Stage"] * len(prompts)
            llm_prompts = []
            llm_indices = []

            for dirpath, original_p in zip(dirpaths, prompts):
                skill_ids_list.append(target_skill_ids)
                final_p, skill_ips, gate = self._build_final_prompt(original_p, target_skill_ids, dirpath)
                final_prompts.append(final_p)
                skill_ips_list.append(skill_ips)
                confidence_gates.append(gate)
                # 读取 gt_ips
                gt_ips_list.append(self._read_gt_ips(dirpath))
                if gate.get("decision") in ("bypass_llm", "operator_review"):
                    final_responses[len(final_prompts) - 1] = make_bypass_response(gate)
                    if gate.get("decision") == "operator_review":
                        retrieval_responses[len(final_prompts) - 1] = "Confidence gate requested operator review"
                    else:
                        retrieval_responses[len(final_prompts) - 1] = "Confidence gate bypassed LLM"
                else:
                    llm_indices.append(len(final_prompts) - 1)
                    llm_prompts.append(final_p)

            if llm_prompts:
                self._ensure_llm()
                llm_responses = vllm_invoke(
                    llm=self.llm,
                    inputs=llm_prompts,
                    sampling_params=self.sampling_params,
                    desc="Stage 2: Root Cause Analysis",
                    b_size=batch_size
                )
                for idx, response in zip(llm_indices, llm_responses):
                    final_responses[idx] = response

            return final_responses, final_prompts, retrieval_responses, skill_ids_list, skill_ips_list, gt_ips_list, confidence_gates

        except Exception as e:
            print(f"\n[Error {os.getpid()}] vLLM batch inference failed: {str(e)}")
            return (["model inference failed"] * len(prompts),
                    [""] * len(prompts),
                    [""] * len(prompts),
                    [[]] * len(prompts),
                    [[]] * len(prompts),
                    [[]] * len(prompts),
                    [{"enabled": self.confidence_gate_enabled, "decision": "error", "reason": str(e)}] * len(prompts))

    @staticmethod
    def _read_gt_ips(dirpath: str) -> list:
        return read_gt_ips(dirpath)


def _find_full_link_file(dirpath: str, filenames: list) -> str:
    return find_full_link_file(dirpath, filenames)


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
    """Print and save prompt coverage diagnostics for ground-truth IPs."""
    if not reports:
        return
    no_gt = [r for r in reports if not r["gt_ips"]]
    all_missing = [r for r in reports if r["all_missing"]]
    partial_missing = [r for r in reports if r["missing_ips"] and not r["all_missing"]]

    print("=" * 60)
    print(f"[GT 诊断] 共 {len(reports)} 个 case")
    print(f"  - 无 gt_ip 标注:        {len(no_gt)}")
    print(f"  - gt_ip 全部不在 prompt: {len(all_missing)}  -> 大模型不可能命中")
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
def worker_process(worker_id: int, npus: str, dirpaths_chunk: list, prompts_chunk: list, target_skill_ids: list, batch_size: int = 8, short=0, top_k=10, confidence_gate=False, confidence_high_margin=15.0, confidence_agreement_margin=8.0, summarize_nodes=False, summary_model_path=None, summary_npu_cards=None, summary_max_tokens=1024) -> dict:
    import os
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    print(f"[Worker {worker_id}] 环境变量已设置 ASCEND_RT_VISIBLE_DEVICES={npus}")
    sleep_time = (worker_id - 1) * 60
    time.sleep(sleep_time)

    analyzer = SkilledAnalyzer(
        ASCEND_RT_VISIBLE_DEVICES=npus,
        short=short,
        top_k=top_k,
        confidence_gate=confidence_gate,
        confidence_high_margin=confidence_high_margin,
        confidence_agreement_margin=confidence_agreement_margin,
        summarize_nodes=summarize_nodes,
        summary_model_path=summary_model_path,
        summary_npu_cards=summary_npu_cards,
        summary_max_tokens=summary_max_tokens,
    )
    # [MODIFIED] 将 target_skill_ids 传入 batch_infer
    (responses, prmpts, ret_ress, skills, skill_ips_ls, gt_ips_ls, confidence_gates) = analyzer.batch_infer(
        dirpaths=dirpaths_chunk, 
        prompts=prompts_chunk, 
        target_skill_ids=target_skill_ids, 
        batch_size=batch_size
    )
    
    resls=[]
    for dp, res, pmt, ret_res, skill, sips, gips, gate in zip(dirpaths_chunk, responses, prmpts, ret_ress, skills, skill_ips_ls, gt_ips_ls, confidence_gates):
        clean_res = res.strip() if isinstance(res, str) else str(res)
        result_dict = {
            "dir": dp,
            "skill_ips": sips,
            "gt_ips": gips,
            "ret_response":ret_res,
            "skills_used":skill,
            "confidence_gate": gate,
            "prompt":pmt,
            "response":clean_res,
        }
        resls.append(result_dict)

    return resls

# [MODIFIED] 增加 target_skill_ids 接收并传递给 worker
def distribute_inference_tasks(dirpath_list: list, prompt_list: list, npu_list: list, target_skill_ids: list, batch_size: int = 8, short=0, top_k=10, confidence_gate=False, confidence_high_margin=15.0, confidence_agreement_margin=8.0, summarize_nodes=False, summary_model_path=None, summary_npu_cards=None, summary_max_tokens=1024) -> dict:
    total_tasks = len(prompt_list)
    if total_tasks == 0:
        return {}

    num_instances = len(npu_list) // 2
    if num_instances == 0:
        raise ValueError("At least two NPU cards are required for each inference worker.")

    npu_groups = [f"{npu_list[i*2]},{npu_list[i*2+1]}" for i in range(num_instances)]
    print(f"检测到可用 NPU: {npu_list}。将启动 {num_instances} 个并行实例，分配给: {npu_groups}")

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
                    top_k=top_k,
                    confidence_gate=confidence_gate,
                    confidence_high_margin=confidence_high_margin,
                    confidence_agreement_margin=confidence_agreement_margin,
                    summarize_nodes=summarize_nodes,
                    summary_model_path=summary_model_path,
                    summary_npu_cards=summary_npu_cards,
                    summary_max_tokens=summary_max_tokens,
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

    p = argparse.ArgumentParser(description="SkilledAnalyzer - Skill 触发的 LLM RCA 推理")
    p.add_argument("--data-root", "-d", default=config.data.nodes_labeled,
                   help="数据根目录(含 nodes.json + info.json 的 case 目录)")
    p.add_argument("--output-dir", "-o", default=None,
                   help="结果输出子目录名(相对于 results，默认使用当前时间戳)")
    p.add_argument("--npu-cards", "-n", default=config.model.npu_cards,
                   help=f"使用的 NPU 卡号，逗号分隔 (default: {config.model.npu_cards})")
    p.add_argument("--skills", "-s", nargs="*", type=int, default=config.skill.skill_ids,
                   help="启用的 Skill ID 列表 (default: [1,2,3])")
    p.add_argument("--batch-size", "-b", type=int, default=config.model.batch_size,
                   help="批量推理大小 (default: 8)")
    p.add_argument("--short", type=int, default=config.skill.short_mode, choices=[0, 1],
                   help="short=1 不传入原始节点数据以节省 Token (default: 0)")
    p.add_argument("--top-k", "-k", type=int, default=config.temporal.top_k,
                   help="展示给 LLM 的候选设备数 (default: 10)")
    p.add_argument("--failures-from", default=None,
                   help="只跑指定 failures JSON 中的错案 (debug/回归用)")
    p.add_argument("--confidence-gate", action="store_true",
                   help="启用置信度门控：高置信算法结果跳过 LLM 重排")
    p.add_argument("--confidence-high-margin", type=float, default=15.0,
                   help="combined Top-1/Top-2 分差达到该阈值时跳过 LLM (default: 15.0)")
    p.add_argument("--confidence-agreement-margin", type=float, default=8.0,
                   help="多方法同意且 combined 分差达到该阈值时跳过 LLM (default: 8.0)")
    p.add_argument("--summarize-nodes", action="store_true",
                   help="Summarize candidate NODES with a small model before sending them to the RCA LLM")
    p.add_argument("--summary-model-path", default=os.environ.get("PINGMESH_SUMMARY_MODEL_PATH", ""),
                   help="Path to the small node-summary model, e.g. a 1.5B model")
    p.add_argument("--summary-npu-cards", default=os.environ.get("PINGMESH_SUMMARY_NPU_CARDS", ""),
                   help="NPU cards for the small summary model; defaults to the worker's first NPU")
    p.add_argument("--summary-max-tokens", type=int, default=int(os.environ.get("PINGMESH_SUMMARY_MAX_TOKENS", "1024")),
                   help="Max tokens generated by the small node-summary model")
    args = p.parse_args()

    target_skill_ids = [str(sid) for sid in args.skills]

    if args.failures_from:
        # 只跑指定错案列表
        dirpaths = get_dirpaths_from_fcases(args.failures_from)
        prompts = generate_partial_prompts(dirpaths)
    else:
        dirpaths, prompts = generate_prompts(args.data_root)

    if prompts:
        print(f"Generated {len(prompts)} inference tasks, skills={target_skill_ids}.")

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
            confidence_gate=args.confidence_gate,
            confidence_high_margin=args.confidence_high_margin,
            confidence_agreement_margin=args.confidence_agreement_margin,
            summarize_nodes=args.summarize_nodes,
            summary_model_path=args.summary_model_path,
            summary_npu_cards=args.summary_npu_cards or None,
            summary_max_tokens=args.summary_max_tokens,
        )
        print(f"All inference workers finished in {time.time() - start_time:.2f}s.")

        if args.output_dir:
            save_dir = os.path.join(config.data.results, args.output_dir)
        else:
            save_dir = os.path.join(config.data.results, str(int(time.time())))
        os.makedirs(save_dir, exist_ok=True)

        if final_results:
            save_path = os.path.join(save_dir, "res.json")
            save_json(final_results, save_path)
            print(f"Results saved to {save_path}")
    else:
        print("No inference tasks found.")
