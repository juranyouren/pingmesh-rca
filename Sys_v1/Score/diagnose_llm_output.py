"""
诊断 LLM 重排输出质量
====================
对比 res.json 中的 LLM 输出 vs 算法排名，找出 87%→30% 的根因。
"""

import json
import os
import re
from collections import Counter


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_ips_from_response(response_text):
    """与 LlmTextParser 相同逻辑提取 IP。"""
    if not response_text or not isinstance(response_text, str):
        return []
    # 尝试 JSON 代码块
    json_pattern = re.compile(r'```json\s*(\{.*?\})\s*```', re.DOTALL | re.IGNORECASE)
    ip_pattern = re.compile(r'"ip"\s*:\s*"(\d{1,3}(?:\.\d{1,3}){3})"')
    ip_generic = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b')

    blocks = json_pattern.findall(response_text)
    if blocks:
        try:
            data = json.loads(blocks[-1])
            ips = data.get("ip", [])
            if isinstance(ips, str):
                ips = [ips]
            return [ip for ip in ips if isinstance(ip, str)]
        except Exception:
            pass
        try:
            data = json.loads(blocks[-1].replace("'", '"'))
            ips = data.get("ip", [])
            if isinstance(ips, str):
                ips = [ips]
            return [ip for ip in ips if isinstance(ip, str)]
        except Exception:
            pass

    ips = ip_pattern.findall(response_text)
    if ips:
        return ips
    return [ip for ip in ip_generic.findall(response_text) if not ip.startswith(("0.", "255."))]


def extract_evidence_ips(response_text):
    """从 LLM 收到的 prompt 中提取证据表里的候选 IP。"""
    if not response_text or not isinstance(response_text, str):
        return []
    ip_pattern = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b')
    return list(dict.fromkeys(ip_pattern.findall(response_text)))  # 保序去重


def diagnose(res_json_path):
    results = load_json(res_json_path)
    print(f"共 {len(results)} 个 case\n")

    empty_output = 0
    parser_fail = 0
    hallucination_only = 0
    match_count = Counter()
    total_cases = 0

    for rd in results:
        dirpath = rd.get("dir", "?")
        response = rd.get("draft_response", rd.get("response", ""))
        prompt = rd.get("prompt", "")

        # 加载 gt
        label_path = os.path.join(dirpath, "label.json")
        gt_ips = []
        if os.path.exists(label_path):
            labels = load_json(label_path)
            if isinstance(labels, list):
                labels_sorted = sorted(labels, key=lambda x: x.get("ranking", 999))
                for lb in labels_sorted[:3]:
                    for an in lb.get("abnormal_node", []):
                        ip = an.get("ip")
                        if ip and ip not in gt_ips:
                            gt_ips.append(ip)

        if not gt_ips:
            continue
        total_cases += 1

        # LLM 输出的 IP
        pred_ips = extract_ips_from_response(response)

        # 证据表中的 IP（LLM 收到的候选列表）
        evidence_ips = extract_evidence_ips(prompt)

        # 分类
        if not pred_ips:
            empty_output += 1
            match_count["empty_output"] += 1
            continue

        if not evidence_ips:
            parser_fail += 1
            continue

        # 检查预测 IP 是否在证据表中
        in_evidence = [ip for ip in pred_ips if ip in evidence_ips]
        outside_evidence = [ip for ip in pred_ips if ip not in evidence_ips]

        if outside_evidence and not in_evidence:
            hallucination_only += 1
            match_count["all_hallucination"] += 1
            if hallucination_only <= 3:
                print(f"[幻觉] {dirpath}")
                print(f"  gt={gt_ips}  pred={pred_ips}  evidence_ips={evidence_ips[:10]}")
        elif outside_evidence:
            match_count["partial_hallucination"] += 1

        # 与 gt 的匹配
        any_gt_hit = any(g in pred_ips for g in gt_ips)
        if any_gt_hit:
            match_count["gt_hit"] += 1
        else:
            match_count["gt_miss"] += 1

    print(f"\n=== 诊断汇总 ({total_cases} cases) ===")
    print(f"LLM 输出为空:        {empty_output} ({100*empty_output/max(1,total_cases):.1f}%)")
    print(f"LLM 输出全为幻觉IP:  {hallucination_only} ({100*hallucination_only/max(1,total_cases):.1f}%)")
    print(f"prompt 解析失败:      {parser_fail}")
    print(f"gt命中:               {match_count['gt_hit']} ({100*match_count['gt_hit']/max(1,total_cases):.1f}%)")
    print(f"gt未命中:             {match_count['gt_miss']}")

    if total_cases > 0:
        valid_cases = total_cases - empty_output - hallucination_only
        hit_rate_on_valid = match_count["gt_hit"] / max(1, valid_cases) * 100
        print(f"\n如果排除空输出+幻觉:  {match_count['gt_hit']}/{valid_cases} = {hit_rate_on_valid:.1f}%")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("res_json", help="res.json 路径")
    args = p.parse_args()
    diagnose(args.res_json)
