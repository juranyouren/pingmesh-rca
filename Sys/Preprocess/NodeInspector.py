"""
Node 数据集感知工具
===================
1. 每个 case 的设备数统计
2. 每个 case 有告警的设备数统计
3. 消融结果失败案例信息

用法:
  # 统计 node 数据
  python Sys/Preprocess/NodeInspector.py stats /path/to/node_data

  # 分析消融失败案例
  python Sys/Preprocess/NodeInspector.py failures /path/to/res_dir
"""

import os, json, sys
from collections import Counter


# ══════════════════════════════════════════════════════════════════
# 1. Node 数据统计
# ══════════════════════════════════════════════════════════════════

def stats_node(data_root):
    """统计 node 数据集的关键指标。"""
    cases = []
    skip = 0

    for dirpath, dirnames, filenames in os.walk(data_root):
        # 找全链路文件
        node_file = None
        for f in filenames:
            if "全链路.json" in f and "pingmesh" in f:
                node_file = f
                break
        if not node_file or "info.json" not in filenames:
            continue

        try:
            nodes_raw = json.load(open(os.path.join(dirpath, node_file), "r", encoding="utf-8"))
            nodes = list(nodes_raw.values()) if isinstance(nodes_raw, dict) else nodes_raw
        except Exception:
            skip += 1
            continue

        csn = os.path.basename(dirpath)
        n_total = len(nodes)
        n_with_alarms = sum(1 for nd in nodes if isinstance(nd, dict)
                            and (nd.get("alarms") or nd.get("logs")))

        cases.append({
            "csn": csn,
            "n_total": n_total,
            "n_with_alarms": n_with_alarms,
        })

    if not cases:
        print("未找到有效 case")
        return

    _print_stats(cases, skip)


def _print_stats(cases, skip=0):
    nt = [c["n_total"] for c in cases]
    na = [c["n_with_alarms"] for c in cases]

    print(f"Case 总数: {len(cases)}  (跳过: {skip})")
    print()

    # 设备数
    print("--- 每 case 设备数 ---")
    print(f"  min={min(nt)}  median={sorted(nt)[len(nt)//2]}  max={max(nt)}")
    dist = Counter()
    for n in nt:
        if n < 10: dist["<10"] += 1
        elif n < 50: dist["10-49"] += 1
        elif n < 100: dist["50-99"] += 1
        elif n < 200: dist["100-199"] += 1
        elif n < 500: dist["200-499"] += 1
        else: dist["500+"] += 1
    for k in ["<10", "10-49", "50-99", "100-199", "200-499", "500+"]:
        if dist[k]:
            print(f"  {k:>8}: {dist[k]} ({100*dist[k]//max(1,len(nt))}%)")

    # 有告警设备数
    print()
    print("--- 每 case 有告警/日志的设备数 ---")
    print(f"  min={min(na)}  median={sorted(na)[len(na)//2]}  max={max(na)}")
    dist = Counter()
    for n in na:
        if n == 0: dist["0"] += 1
        elif n <= 5: dist["1-5"] += 1
        elif n <= 10: dist["6-10"] += 1
        elif n <= 20: dist["11-20"] += 1
        else: dist["20+"] += 1
    for k in ["0", "1-5", "6-10", "11-20", "20+"]:
        if dist[k]:
            print(f"  {k:>6}: {dist[k]} ({100*dist[k]//max(1,len(na))}%)")

    # Mean
    print(f"\n  平均: {sum(na)/len(na):.1f} / {sum(nt)/len(nt):.1f} 设备")


# ══════════════════════════════════════════════════════════════════
# 2. 消融失败分析
# ══════════════════════════════════════════════════════════════════

def analyze_failures(res_dir):
    """分析消融结果中的失败案例。"""
    # 找 summary.json
    summary_path = os.path.join(res_dir, "summary.json")
    if not os.path.exists(summary_path):
        print(f"未找到 summary.json: {summary_path}")
        return

    summary = json.load(open(summary_path, "r", encoding="utf-8"))
    results = summary.get("results", [])

    print(f"消融组合数: {len(results)}")
    print()

    for r in results:
        tag = r.get("tag", "?")
        skills = r.get("skills", "?")
        top1 = r.get("top1", 0)
        top3 = r.get("top3", 0)
        top5 = r.get("top5", 0)
        total = r.get("total_cases", 0)
        failed = total - int(total * top1 / 100) if top1 > 0 else 0

        n_top1_only = int(total * top1 / 100) if top1 > 0 else 0
        n_top3 = int(total * top3 / 100) if top3 > 0 else 0
        n_top5 = int(total * top5 / 100) if top5 > 0 else 0

        in_top3_not_top1 = n_top3 - n_top1_only
        in_top5_not_top3 = n_top5 - n_top3
        not_in_top5 = total - n_top5

        print(f"--- [{tag}] skills={skills} ---")
        print(f"  Top-1: {top1}% ({n_top1_only}/{total})")
        print(f"  Top-3: {top3}% (新增 {in_top3_not_top1} 例在 rank 2-3)")
        print(f"  Top-5: {top5}% (新增 {in_top5_not_top3} 例在 rank 4-5)")
        print(f"  不在 Top-5: {not_in_top5} 例 ({100*not_in_top5//max(1,total)}%)")
        print()


# ══════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="NodeInspector — node 数据集感知 + 消融失败分析")
    sub = p.add_subparsers(dest="cmd")

    s1 = sub.add_parser("stats", help="node 数据统计")
    s1.add_argument("data_root", help="node 数据目录")

    s2 = sub.add_parser("failures", help="消融失败分析")
    s2.add_argument("res_dir", help="消融结果目录 (含 summary.json)")

    args = p.parse_args()

    if args.cmd == "stats":
        stats_node(args.data_root)
    elif args.cmd == "failures":
        analyze_failures(args.res_dir)
    else:
        p.print_help()
