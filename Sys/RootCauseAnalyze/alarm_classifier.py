"""
LLM 告警分类器 — 两模式
========================
Mode 1 (global): 全数据集去重, 分类后存为单个 taxonomy JSON
Mode 2 (per_case): 每个 case 单独送 LLM, 分类结果存到 case 目录下

用法:
  # 全局模式
  python alarm_classifier.py --data data/node/xxx --mode global -o data/weights/alarm_taxonomy.json

  # 逐 case 模式 (分类写入每个 case 的 alarm_taxonomy.json)
  python alarm_classifier.py --data data/node/xxx --mode per_case --write
"""

import os, json, sys, time
from collections import Counter

TAXONOMY_PROMPT = """你是数据中心网络运维专家。请根据告警名称, 判断每条告警在**本次故障场景**中充当的角色。

对每条告警, 输出一个 JSON 对象:
  {"name":"<告警名称>","type":"causal|symptom|noise","severity":1-100}

分类标准:
  "causal"  — 根因型。直接指向物理/硬件故障:
     端口物理Down、光模块异常/功率异常、设备掉线/重启、硬件故障、
     链路Down(物理层)、单板故障、电源异常、风扇故障、网络设备掉线监控
  "symptom" — 继发型。被波及或衍生:
     BGP邻居中断/震荡、OSPF邻居Down、路由变化/震荡、丢包/拥塞、
     CPU/内存告警、超时、协议层异常、接口Error计数增长
  "noise"   — 噪声/信息性:
     阈值恢复通知、配置变更、心跳超时、冗余切换通知、周期性统计

【硬性要求】
- 输出一行一个 JSON, 不要 markdown 代码块, 不要解释
- 如果告警名称无法判断, 默认为 "symptom", severity=50

现在请分类以下告警:
"""


def _parse_response(text):
    results = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try: obj = json.loads(line)
        except json.JSONDecodeError:
            try: obj = json.loads(line + "}")
            except json.JSONDecodeError: continue
        if not all(k in obj for k in ("name","type","severity")):
            continue
        t = obj["type"]
        if t not in ("causal","symptom","noise"): t = "symptom"
        yield {"name": obj["name"], "type": t, "severity": max(1, min(100, int(obj["severity"])))}


# ══════════════════════════════════════════════════════════════════
# Shared: LLM inference
# ══════════════════════════════════════════════════════════════════

def _llm_infer(prompts, model_path, npu_cards, batch_size):
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npu_cards
    from vllm import LLM, SamplingParams
    llm = LLM(model=model_path, tensor_parallel_size=len(npu_cards.split(",")),
              gpu_memory_utilization=0.85, max_model_len=16384, trust_remote_code=True)
    sp = SamplingParams(temperature=0.3, max_tokens=4096, repetition_penalty=1.05)

    responses = []
    for i in range(0, len(prompts), batch_size):
        batch = prompts[i:i+batch_size]
        try:
            out = llm.chat([[{"role":"user","content":p}] for p in batch], sp)
        except Exception as e:
            print(f"  batch {i//batch_size+1}/{len(prompts)//batch_size+1} 失败: {e}")
            responses.extend([""] * len(batch))
            continue
        responses.extend([o.outputs[0].text if o.outputs else "" for o in out])
        print(f"  batch {i//batch_size+1}: {len(batch)} cases -> {sum(1 for r in responses[-len(batch):] if r)} responses")
    return responses


# ══════════════════════════════════════════════════════════════════
# Per-case mode
# ══════════════════════════════════════════════════════════════════

def _collect_case_alarms(case_dir):
    """从 case 目录的全链路文件中提取所有告警名(去重) + 简要描述。"""
    node_file = None
    for f in os.listdir(case_dir):
        if "全链路.json" in f and "pingmesh" in f:
            node_file = f; break
    if not node_file: return []

    raw = json.load(open(os.path.join(case_dir, node_file), "r", encoding="utf-8"))
    nodes = list(raw.values()) if isinstance(raw, dict) else raw

    alarm_info = {}  # name → {count, sample_descriptions}
    for nd in nodes:
        if not isinstance(nd, dict): continue
        for evt in nd.get("alarms", []) + nd.get("logs", []):
            name = evt.strip() if isinstance(evt, str) else str(evt.get("alarm_name", evt.get("name", ""))).strip()
            if not name: continue
            if name not in alarm_info:
                desc = ""
                if isinstance(evt, dict):
                    desc = str(evt.get("alarm_description", evt.get("description", "")))[:120]
                alarm_info[name] = {"count": 0, "desc": desc}
            alarm_info[name]["count"] += 1

    # 按出现次数降序排列
    return sorted(alarm_info.items(), key=lambda x: -x[1]["count"])


def classify_per_case(data_root, model_path=None, npu_cards="0,1",
                      batch_size=32, write=False):
    """逐 case 分类, LLM 对每个 case 的所有告警名打分+分类。"""
    if model_path is None:
        try:
            from Sys.config import config
            model_path = config.model.model_path
        except Exception:
            model_path = "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B"

    # 收集所有 case
    cases = []
    for dirpath, _, filenames in os.walk(data_root):
        if "info.json" not in filenames: continue
        cases.append(dirpath)

    print(f"Case 总数: {len(cases)}")

    # 构建 prompt (每个 case 一个)
    prompts = []
    case_alarms = []
    for d in cases:
        alarms = _collect_case_alarms(d)
        case_alarms.append(alarms)
        if not alarms:
            prompts.append(None)  # 无告警的 case 跳过
            continue
        alarm_lines = [f"- {name}  (出现{info['count']}次)" +
                       (f" 描述:{info['desc']}" if info['desc'] else "")
                       for name, info in alarms]
        prompts.append(TAXONOMY_PROMPT + "\n".join(alarm_lines))

    # 过滤空 case
    valid_idx = [i for i, p in enumerate(prompts) if p is not None]
    valid_prompts = [prompts[i] for i in valid_idx]
    print(f"有告警的 case: {len(valid_prompts)}")

    if not valid_prompts:
        return

    start = time.time()
    responses = _llm_infer(valid_prompts, model_path, npu_cards, batch_size)
    elapsed = time.time() - start
    print(f"LLM 推理完成, 耗时 {elapsed:.0f}s")

    # 解析 + 写入
    total_classified = 0
    for i, resp in zip(valid_idx, responses):
        parsed = list(_parse_response(resp))
        if not parsed: continue
        taxonomy = {item["name"]: {"type": item["type"], "severity": item["severity"]}
                    for item in parsed}
        total_classified += len(taxonomy)

        if write:
            json.dump(taxonomy, open(os.path.join(cases[i], "alarm_taxonomy.json"), "w",
                                     encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"分类完成: {total_classified} 条 alarm_taxonomy")


# ══════════════════════════════════════════════════════════════════
# Global mode (保留原功能)
# ══════════════════════════════════════════════════════════════════

def collect_all_alarms(data_root):
    all_names = set()
    for dirpath, _, filenames in os.walk(data_root):
        node_file = None
        for f in filenames:
            if "全链路.json" in f and "pingmesh" in f: node_file = f; break
        if not node_file: continue
        raw = json.load(open(os.path.join(dirpath, node_file), "r", encoding="utf-8"))
        nodes = list(raw.values()) if isinstance(raw, dict) else raw
        for nd in nodes:
            if not isinstance(nd, dict): continue
            for evt in nd.get("alarms", []) + nd.get("logs", []):
                name = evt.strip() if isinstance(evt, str) else str(evt.get("alarm_name", evt.get("name", ""))).strip()
                if name: all_names.add(name)
    return sorted(all_names)


def classify_global(data_root, output_path, base_path=None,
                    model_path=None, npu_cards="0,1", batch_size=32):
    taxonomy = {}
    if base_path and os.path.exists(base_path):
        taxonomy = json.load(open(base_path, "r", encoding="utf-8"))

    all_alarms = collect_all_alarms(data_root)
    missing = [a for a in all_alarms if a not in taxonomy]
    print(f"数据集告警: {len(all_alarms)} 种, 缺失: {len(missing)}")

    if not missing: return

    if model_path is None:
        try:
            from Sys.config import config
            model_path = config.model.model_path
        except Exception:
            model_path = "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B"

    prompts = []
    for i in range(0, len(missing), batch_size):
        batch = missing[i:i+batch_size]
        prompts.append(TAXONOMY_PROMPT + "\n".join(f"- {a}" for a in batch))

    responses = _llm_infer(prompts, model_path, npu_cards, 1)

    for resp in responses:
        for item in _parse_response(resp):
            taxonomy[item["name"]] = {"type": item["type"], "severity": item["severity"]}

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    json.dump(taxonomy, open(output_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"已写入: {output_path} ({len(taxonomy)} 条)")


# ══════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="LLM 告警分类器 — global / per_case")
    p.add_argument("--data", "-d", required=True, help="node 数据目录")
    p.add_argument("--mode", "-m", default="global", choices=["global", "per_case"],
                   help="global: 全量去重一次性分类; per_case: 逐 case 分类")
    p.add_argument("--output", "-o", default=None, help="输出路径 (global 模式必需)")
    p.add_argument("--base", "-b", default=None, help="已有 taxonomy (global 模式增量)")
    p.add_argument("--model-path", default=None, help="模型路径")
    p.add_argument("--npu-cards", "-n", default="0,1", help="NPU 卡号")
    p.add_argument("--batch-size", type=int, default=32, help="LLM batch size")
    p.add_argument("--write", action="store_true", help="per_case 模式写出 alarm_taxonomy.json")
    args = p.parse_args()

    if args.mode == "per_case":
        classify_per_case(args.data, model_path=args.model_path,
                          npu_cards=args.npu_cards, batch_size=args.batch_size,
                          write=args.write)
    else:
        if not args.output:
            p.error("global 模式需要 --output")
        classify_global(args.data, args.output, base_path=args.base,
                        model_path=args.model_path, npu_cards=args.npu_cards,
                        batch_size=args.batch_size)
