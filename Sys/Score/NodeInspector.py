"""
Node 数据集感知工具
===================
统计 node 数据集的设备规模与告警覆盖。
(消融失败分析已移到 Score_N.calculate_metrics → top1_failures.json)

用法:
  python Sys/Score/NodeInspector.py /path/to/node_data
"""

import os, json, sys
from collections import Counter


def stats_node(data_root, count_logs=False):
    """统计 node 数据集的关键指标。count_logs: 是否把 log 也算作告警。"""
    cases = []
    skip = 0

    for dirpath, dirnames, filenames in os.walk(data_root):
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

        n_total = len(nodes)
        n_with_alarms = sum(1 for nd in nodes if isinstance(nd, dict)
                            and (nd.get("alarms") or (count_logs and nd.get("logs"))))
        cases.append({"csn": os.path.basename(dirpath),
                      "n_total": n_total, "n_with_alarms": n_with_alarms})

    if not cases:
        print("未找到有效 case")
        return

    nt = [c["n_total"] for c in cases]
    na = [c["n_with_alarms"] for c in cases]

    print(f"Case 总数: {len(cases)}  (跳过: {skip})  count_logs={count_logs}\n")

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

    print("\n--- 每 case 有告警/日志的设备数 ---")
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

    print(f"\n  平均: {sum(na)/len(na):.1f} / {sum(nt)/len(nt):.1f} 设备")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="NodeInspector — node 数据集感知")
    p.add_argument("data_root", help="node 数据目录")
    p.add_argument("--count-logs", action="store_true",
                   help="把 log 也算作告警 (默认只看 alarm)")
    args = p.parse_args()
    stats_node(args.data_root, count_logs=args.count_logs)
