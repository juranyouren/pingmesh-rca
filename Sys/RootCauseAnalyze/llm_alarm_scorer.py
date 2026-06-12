"""
LLM Alarm Scorer — 大模型前置告警语义打分
=========================================
对权重表中缺失的告警名，由 LLM 根据网络运维经验打出 1-100 的严重程度分，
合并到基础权重文件后输出 enriched 版本。

不依赖 NPU 之外的硬件，复用 vLLM 推理栈。

用法:
  python Sys/RootCauseAnalyze/llm_alarm_scorer.py \
    --missing missing_alarms.json --output enriched_weights.json
"""

import os
import sys
import json
import re

ALARM_SCORING_PROMPT = """你是数据中心网络运维专家。请根据告警名称，评估该告警在网络故障中作为**根因**的严重程度和指向性。

评分标准 (1-100):
  90-100: 明确指向物理设备/链路故障 (如设备掉电、端口物理Down、光模块故障、硬件异常)
  70-89:  高层协议中断，通常是根因而非衍生 (如 BGP邻居中断、OSPF邻居Down、VRRP状态异常)
  50-69:  中等严重，可能是根因也可能是衍生 (如接口Error计数增长、CRC错包、路由震荡)
  30-49:  较低严重，通常为次生告警 (如链路Flapping、端口Up/Down快速切换)
  10-29:  信息性告警，几乎不会是根因 (如链路恢复、配置变更通知、阈值恢复)
   1-9:   噪声，运维可忽略 (如周期性心跳超时、冗余组件切换通知)

【输出要求】
对每条告警只输出一个 JSON 对象，包含 alarm_name 和 score 两个字段。
用紧凑格式，一行一条，不要 markdown 代码块，不要解释。

现在请为以下告警打分:
"""


def build_batches(alarms, batch_size=32):
    for i in range(0, len(alarms), batch_size):
        yield alarms[i:i + batch_size]


def parse_scores(response_text):
    """从 LLM 回复中提取 {alarm_name: score} 列表。"""
    results = []
    # 尝试逐行匹配 JSON 对象
    for line in response_text.strip().split("\n"):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            if "alarm_name" in obj and "score" in obj:
                s = int(obj["score"])
                results.append((obj["alarm_name"], max(1, min(100, s))))
        except (json.JSONDecodeError, ValueError, TypeError):
            # 尝试修复截断
            try:
                obj = json.loads(line + "}")
                if "alarm_name" in obj and "score" in obj:
                    s = int(obj["score"])
                    results.append((obj["alarm_name"], max(1, min(100, s))))
            except Exception:
                pass
    return results


def run_scoring(missing_alarms, output_path, base_weights_path=None,
                model_path=None, npu_cards="0,1", batch_size=32):
    """
    主入口: 用 LLM 对缺失告警打分，合并 base 权重，写 enriched 文件。
    """
    # ── 加载基础权重 ──
    base_weights = {}
    if base_weights_path and os.path.exists(base_weights_path):
        with open(base_weights_path, "r", encoding="utf-8") as f:
            for item in json.load(f):
                base_weights[item["alarm_name"]] = int(item["alarm_priority"])

    if not missing_alarms:
        print("无缺失告警，直接使用基础权重")
        enriched = [{"alarm_name": k, "alarm_priority": base_weights.get(k, 0)}
                    for k in sorted(base_weights)]
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(enriched, f, ensure_ascii=False, indent=2)
        print(f"已写入: {output_path} ({len(enriched)} 条)")
        return output_path

    print(f"缺失告警: {len(missing_alarms)} 条, 基础权重: {len(base_weights)} 条")
    print(f"批量大小: {batch_size}, NPU: {npu_cards}")

    # ── 初始化 vLLM ──
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npu_cards
    from vllm import LLM, SamplingParams

    if model_path is None:
        try:
            from Sys.config import config
            model_path = config.model.model_path
        except Exception:
            model_path = "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B"

    print(f"加载模型: {model_path}")

    llm = LLM(
        model=model_path,
        tensor_parallel_size=len(npu_cards.split(",")),
        gpu_memory_utilization=0.85,
        max_model_len=16384,
        trust_remote_code=True,
    )
    sampling_params = SamplingParams(temperature=0.3, max_tokens=4096, repetition_penalty=1.05)

    # ── 批量推理 ──
    scored = {}
    batches = list(build_batches(missing_alarms, batch_size))

    for bi, batch in enumerate(batches):
        prompt = ALARM_SCORING_PROMPT + "\n".join(f"- {a}" for a in batch)
        try:
            outputs = llm.chat([[{"role": "user", "content": prompt}]], sampling_params)
            response = outputs[0].outputs[0].text if outputs else ""
        except Exception as e:
            print(f"  batch {bi+1}/{len(batches)} 推理失败: {e}")
            continue

        parsed = parse_scores(response)
        for name, score in parsed:
            scored[name] = score
        print(f"  batch {bi+1}/{len(batches)}: 发送 {len(batch)} → 解析 {len(parsed)} 条, 累计 {len(scored)}")

    # ── 未解析到的用默认值 10 ──
    for a in missing_alarms:
        if a not in scored:
            scored[a] = 10

    print(f"LLM 打分完成: {len(scored)} 条")

    # ── 合并输出 ──
    merged = dict(base_weights)
    merged.update(scored)
    enriched = [{"alarm_name": k, "alarm_priority": merged[k]} for k in sorted(merged)]

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
    print(f"已写入: {output_path} ({len(enriched)} 条, base={len(base_weights)} llm={len(scored)})")
    return output_path


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="LLM Alarm Scorer — 大模型前置告警语义打分")
    p.add_argument("--missing", "-m", required=True, help="缺失告警列表 JSON 文件")
    p.add_argument("--output", "-o", required=True, help="输出 enriched 权重文件路径")
    p.add_argument("--base-weights", "-b", default=None, help="基础权重文件路径")
    p.add_argument("--model-path", default=None,
                   help="模型路径（默认: config.model.model_path）")
    p.add_argument("--npu-cards", "-n", default="0,1",
                   help="NPU 卡号 (default: 0,1)")
    p.add_argument("--batch-size", type=int, default=32,
                   help="LLM 批量大小 (default: 32)")
    args = p.parse_args()

    missing = json.load(open(args.missing, "r", encoding="utf-8"))

    run_scoring(
        missing_alarms=missing,
        output_path=args.output,
        base_weights_path=args.base_weights,
        model_path=args.model_path,
        npu_cards=args.npu_cards,
        batch_size=args.batch_size,
    )
