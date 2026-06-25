"""
Alarm Classifier — LLM 告警三分类器
====================================
对每个 case 收集全部告警名称（去重），送 LLM 做三分类：
  causal  — 根因型：物理故障、硬件异常、设备掉线
  symptom — 继发型：被波及的反应（BGP震荡、丢包、CPU）
  noise   — 噪声型：周期性通知、心跳、阈值恢复

输出 alarm_taxonomy.json，供 PageRank / Temporal 使用。

与 llm_alarm_scorer.py 的区别：
  - 旧：只打0-100分（单维）
  - 新：三分类 + 严重度评分（二维）

用法:
  # 收集全数据集告警名 → LLM 分类 → 存盘
  python Sys/RootCauseAnalyze/alarm_classifier.py \
    --data /path/to/nodes --output data/weights/alarm_taxonomy.json

  # 后续 pipeline 自动读取 alarm_taxonomy.json（如果存在）
"""

import os, json, sys

TAXONOMY_PROMPT = """你是数据中心网络运维专家。请对以下告警进行分类。

对每条告警, 输出一个 JSON 对象, 包含三个字段:
  "name": 告警名称(原文)
  "type": "causal" / "symptom" / "noise"
  "severity": 1-100 (严重度, 越高越指向根因)

分类标准:
  "causal"  — 根因型, 直接指向物理/硬件故障:
     端口物理Down、光模块异常/功率异常、设备掉线/重启、硬件故障、
     链路Down(物理层)、单板故障、电源异常、风扇故障
  "symptom" — 继发型, 被波及或衍生:
     BGP邻居中断/震荡、OSPF邻居Down、路由变化/震荡、
     丢包/拥塞、CPU/内存告警、超时、协议层异常
  "noise"   — 噪声/信息性, 不考虑:
     阈值恢复通知、配置变更、心跳超时、冗余切换通知、
     周期性统计上报、debug级别日志

评分标准:
  90-100: 明确指向单一设备物理故障 (如 端口物理Down、光模块故障)
  70-89:  指向网络连接中断, 既可能是根因也可能被波及 (如 BGP中断)
  50-69:  性能/容量异常 (如 CPU高、丢包), 通常为次生
  30-49:  状态变化通知 (如 端口Up/Down震荡)
  10-29:  信息性, 仅记录
   1-9:   完全可忽略的噪声

【硬性要求】
- 每个告警名只评估一次, 用其典型含义判断, 不考虑特定 case 上下文
- 输出一行一个 JSON 对象, 不要 markdown 代码块, 不要解释文字

现在请分类以下告警:
"""


def _build_batches(items, batch_size=32):
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]


def _parse_response(text):
    """从 LLM 回复中解析 {name, type, severity} 列表。"""
    results = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            try:
                obj = json.loads(line + "}")
            except json.JSONDecodeError:
                continue
        if "name" in obj and "type" in obj:
            t = obj["type"]
            if t not in ("causal", "symptom", "noise"):
                t = "symptom"  # 兜底
            s = max(1, min(100, int(obj.get("severity", 50))))
            results.append({"name": obj["name"], "type": t, "severity": s})
    return results


def collect_all_alarms(data_root):
    """扫描全数据集, 返回去重后的告警名称列表。"""
    all_names = set()
    for dirpath, _, filenames in os.walk(data_root):
        node_file = None
        for f in filenames:
            if "全链路.json" in f and "pingmesh" in f:
                node_file = f
                break
        if not node_file:
            continue
        raw = json.load(open(os.path.join(dirpath, node_file), "r", encoding="utf-8"))
        nodes = list(raw.values()) if isinstance(raw, dict) else raw
        for nd in nodes:
            if not isinstance(nd, dict):
                continue
            for evt in nd.get("alarms", []) + nd.get("logs", []):
                name = evt.strip() if isinstance(evt, str) else str(evt.get("alarm_name", evt.get("name", ""))).strip()
                if name:
                    all_names.add(name)
    return sorted(all_names)


def run_classification(missing_alarms, taxonomy, model_path=None, npu_cards="0,1", batch_size=32):
    """用 LLM 对告警列表分类, 把结果合并写入 taxonomy 变量, 返回新增数量。"""
    if not missing_alarms:
        return 0

    if model_path is None:
        try:
            from Sys.config import config
            model_path = config.model.model_path
        except Exception:
            model_path = "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B"

    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npu_cards
    from vllm import LLM, SamplingParams

    print(f"模型: {model_path}, 待分类: {len(missing_alarms)} 条")
    llm = LLM(model=model_path, tensor_parallel_size=len(npu_cards.split(",")),
              gpu_memory_utilization=0.85, max_model_len=16384, trust_remote_code=True)
    sp = SamplingParams(temperature=0.3, max_tokens=4096, repetition_penalty=1.05)

    scored = {}
    for bi, batch in enumerate(_build_batches(missing_alarms, batch_size)):
        prompt = TAXONOMY_PROMPT + "\n".join(f"- {a}" for a in batch)
        try:
            outputs = llm.chat([[{"role": "user", "content": prompt}]], sp)
            response = outputs[0].outputs[0].text if outputs else ""
        except Exception as e:
            print(f"  batch {bi+1}/{len(missing_alarms)//batch_size+1} 失败: {e}")
            continue
        for item in _parse_response(response):
            scored[item["name"]] = {"type": item["type"], "severity": item["severity"]}
        print(f"  batch {bi+1}: {len(batch)} sent -> {len(_parse_response(response))} parsed")

    # 合并
    added = 0
    for name, info in scored.items():
        if name not in taxonomy:
            taxonomy[name] = info
            added += 1
    return added


# ══════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Alarm Classifier — LLM 告警三分类")
    p.add_argument("--data", "-d", required=True, help="node 数据目录")
    p.add_argument("--output", "-o", required=True, help="输出 taxonomy 文件路径")
    p.add_argument("--base", "-b", default=None,
                   help="已有 taxonomy 文件（增量更新）")
    p.add_argument("--model-path", default=None,
                   help="模型路径（默认: config.model.model_path）")
    p.add_argument("--npu-cards", "-n", default="0,1",
                   help="NPU 卡号 (default: 0,1)")
    p.add_argument("--batch-size", type=int, default=32,
                   help="LLM 批量大小 (default: 32)")
    args = p.parse_args()

    # 加载已有 taxonomy
    taxonomy = {}
    if args.base and os.path.exists(args.base):
        taxonomy = json.load(open(args.base, "r", encoding="utf-8"))
        print(f"已有 taxonomy: {len(taxonomy)} 条")

    all_alarms = collect_all_alarms(args.data)
    print(f"数据集告警名称: {len(all_alarms)} 种")

    missing = [a for a in all_alarms if a not in taxonomy]
    print(f"已覆盖: {len(all_alarms) - len(missing)}, 待分类: {len(missing)}")

    added = run_classification(missing, taxonomy,
                               model_path=args.model_path,
                               npu_cards=args.npu_cards,
                               batch_size=args.batch_size)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    json.dump(taxonomy, open(args.output, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"已写入: {args.output} ({len(taxonomy)} 条, 新增 {added})")
