"""
失败案例分析器
==============
对 Top-1 失败的案例，加载其 node 数据，分析根因设备为什么没被排到第一。

诊断维度 (针对每个 gt 根因设备):
  1. 根因设备是否有告警/日志? (无 → 算法看不到信号)
  2. 告警是否命中权重表? (未命中 → personalization 无加成)
  3. 根因的 PR 分 / 时序分 / 综合分, 对比排在它前面的设备
  4. 是谁挤掉了它 (rank 1 设备的特征)

输入: top1_failures.json (由 Score_N 生成)
输出: 每个失败案例一份报告 + 汇总

用法:
  python Sys/Score/failure_analyzer.py /path/to/res_dir
  python Sys/Score/failure_analyzer.py /path/to/res_dir --bucket "miss (not in top5)"
"""

import os, json, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_ip(node):
    return node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))


def _find_node_file(case_dir):
    if not os.path.isdir(case_dir):
        return None
    for f in os.listdir(case_dir):
        if "全链路.json" in f and "pingmesh" in f:
            return os.path.join(case_dir, f)
    return None


def _load_nodes(case_dir):
    nf = _find_node_file(case_dir)
    if not nf:
        return {}
    try:
        raw = _load(nf)
    except Exception:
        return {}
    nodes = list(raw.values()) if isinstance(raw, dict) else raw
    return {_get_ip(n): n for n in nodes if isinstance(n, dict)}


def _alarm_names(node):
    names = []
    for evt in node.get("alarms", []) + node.get("logs", []):
        if isinstance(evt, str):
            names.append(evt)
        elif isinstance(evt, dict):
            nm = evt.get("alarm_name", evt.get("name", ""))
            if nm:
                names.append(nm)
    return names


def analyze_case(rec, weight_dirpath=None):
    """对单个失败 case 生成诊断报告 dict。"""
    case_dir = rec["dir"]
    gt_ips = rec.get("gt_ips", [])
    pred_ips = rec.get("pred_ips", [])
    best_rank = rec.get("best_rank")

    node_by_ip = _load_nodes(case_dir)

    # 加载评分函数 (与推理一致)
    try:
        from Sys.RootCauseAnalyze.skill_pipeline import _score_topo, _score_temporal
        from Sys.config import config
        info_path = os.path.join(case_dir, "info.json")
        info = _load(info_path) if os.path.exists(info_path) else {}
        wpath = weight_dirpath or config.data.alarm_weights
        node_list = list(node_by_ip.values())
        pr = _score_topo(node_list, info, weight_dirpath=wpath, directed=True)
        ts = _score_temporal(node_list, info, dirpath=case_dir)
        combined = {ip: (pr.get(ip, 0) + ts.get(ip, 0)) / 2 for ip in node_by_ip}
    except Exception as e:
        pr, ts, combined = {}, {}, {}

    # 诊断每个 gt 设备
    gt_diag = []
    for gip in gt_ips:
        nd = node_by_ip.get(gip)
        if not nd:
            gt_diag.append({"ip": gip, "issue": "根因设备不在 node 数据中"})
            continue
        alarms = _alarm_names(nd)
        gt_diag.append({
            "ip": gip,
            "role": nd.get("role", "?"),
            "cross": nd.get("cross", 0),
            "n_alarms": len(alarms),
            "alarms": alarms[:5],
            "pr_score": round(pr.get(gip, 0), 4),
            "temporal_score": round(ts.get(gip, 0), 4),
            "combined": round(combined.get(gip, 0), 4),
        })

    # rank 1 设备 (挤掉 gt 的)
    top1_ip = pred_ips[0] if pred_ips else None
    top1_diag = None
    if top1_ip and top1_ip in node_by_ip:
        nd = node_by_ip[top1_ip]
        top1_diag = {
            "ip": top1_ip,
            "role": nd.get("role", "?"),
            "cross": nd.get("cross", 0),
            "n_alarms": len(_alarm_names(nd)),
            "pr_score": round(pr.get(top1_ip, 0), 4),
            "temporal_score": round(ts.get(top1_ip, 0), 4),
            "combined": round(combined.get(top1_ip, 0), 4),
        }

    # 失败原因归类
    reason = _classify_reason(gt_diag, top1_diag)

    return {
        "csn": os.path.basename(case_dir),
        "best_rank": best_rank,
        "reason": reason,
        "gt_devices": gt_diag,
        "ranked_1st": top1_diag,
    }


def _classify_reason(gt_diag, top1_diag):
    """根据诊断数据归类失败原因。"""
    if not gt_diag:
        return "无 gt 数据"

    # 所有 gt 都无告警
    if all(g.get("n_alarms", 0) == 0 for g in gt_diag if "issue" not in g):
        return "根因设备无告警 (算法无信号)"

    if any("issue" in g for g in gt_diag):
        return "根因设备不在 node 数据中"

    # gt 的综合分 vs top1
    if top1_diag:
        gt_best = max((g.get("combined", 0) for g in gt_diag), default=0)
        if gt_best > 0 and top1_diag["combined"] - gt_best < 0.05:
            return "综合分接近 (算法难区分)"
        if top1_diag.get("temporal_score", 0) > 0 and all(g.get("temporal_score", 0) == 0 for g in gt_diag):
            return "时序信号误导 (rank1 时序高, gt 时序为0)"
        if top1_diag.get("pr_score", 0) > max((g.get("pr_score", 0) for g in gt_diag), default=0):
            return "拓扑信号误导 (rank1 PR 高于 gt)"

    return "其他"


def run(res_dir, bucket=None, ip_source="skill"):
    fail_path = os.path.join(res_dir, "top1_failures.json")
    if not os.path.exists(fail_path):
        print(f"未找到 {fail_path} (先运行 Score_N 评测)")
        return

    failures = _load(fail_path)
    src = failures.get(ip_source, {})
    if not src:
        print(f"{ip_source} 无失败案例")
        return

    reports = []
    reason_counter = Counter()

    for bucket_name, cases in src.items():
        if bucket and bucket != bucket_name:
            continue
        for rec in cases:
            rep = analyze_case(rec)
            rep["bucket"] = bucket_name
            reports.append(rep)
            reason_counter[rep["reason"]] += 1

    # 输出
    out_path = os.path.join(res_dir, "failure_analysis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)

    print(f"分析了 {len(reports)} 个失败案例 ({ip_source})")
    print(f"\n--- 失败原因分布 ---")
    for reason, count in reason_counter.most_common():
        print(f"  {count:>3}  {reason}")
    print(f"\n详细报告: {out_path}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="失败案例分析器")
    p.add_argument("res_dir", help="评测结果目录 (含 top1_failures.json)")
    p.add_argument("--source", default="skill", choices=["skill", "llm"],
                   help="分析 skill 还是 llm 的失败案例")
    p.add_argument("--bucket", default=None,
                   help="只分析特定桶 (如 'miss (not in top5)')")
    args = p.parse_args()
    run(args.res_dir, bucket=args.bucket, ip_source=args.source)
