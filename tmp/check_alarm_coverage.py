"""
诊断: 146 例数据中，有多少 case 的候选设备告警/日志为空？
LLM 重排需要告警语义信息——如果大部分 case 告警为空，LLM 无法有效介入。
"""

import json
import os
import sys
sys.path.insert(0, "/home/sbp/lixinyang/pingmesh")

data_root = "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"

empty_cases = 0
total_cases = 0
alarm_stats = []  # (case_name, total_alarms, has_any_high_severity)

for dirpath, _, filenames in os.walk(data_root):
    node_file = None
    for fn in filenames:
        if "全链路.json" in fn and "pingmesh" in fn:
            node_file = fn
            break
    if not node_file:
        continue

    raw = json.load(open(os.path.join(dirpath, node_file), "r", encoding="utf-8"))
    nodes = list(raw.values()) if isinstance(raw, dict) else raw

    total_alarms = sum(len(n.get("alarms", [])) + len(n.get("logs", [])) for n in nodes)
    has_any_high = any(
        any(
            (a.get("alarm_name") if isinstance(a, dict) else a) in
            ("stachg_todwn", "trunkdown", "vlan接口down(dcn)",
             "BGP邻居中断", "端口Down", "链路Down", "光模块异常",
             "OSPF邻居Down", "设备掉电", "硬件故障")
            for a in n.get("alarms", []) + n.get("logs", [])
        )
        for n in nodes
    )

    total_cases += 1
    alarm_stats.append((os.path.basename(dirpath), total_alarms, has_any_high))
    if total_alarms == 0:
        empty_cases += 1

print(f"总 case: {total_cases}")
print(f"所有设备告警/日志均为空: {empty_cases} ({100*empty_cases//max(1,total_cases)}%)")
print(f"有告警数据的 case: {total_cases - empty_cases}")

# 有告警数据的 case 中，有多少含高危告警
cases_with_data = [s for s in alarm_stats if s[1] > 0]
high_sev = [s for s in cases_with_data if s[2]]
print(f"其中含疑似高危告警: {len(high_sev)}/{len(cases_with_data) if cases_with_data else 0}")
print()

# 按告警数量分档
ranges = [(0, 0), (1, 10), (11, 50), (51, 200), (201, 9999)]
for lo, hi in ranges:
    if lo == hi == 0:
        count = empty_cases
    else:
        count = sum(1 for s in alarm_stats if lo <= s[1] <= hi)
    print(f"  告警数 [{lo:>4}-{hi:>4}]: {count} 例 ({100*count//max(1,total_cases)}%)")

# 结论
print()
if empty_cases > total_cases * 0.7:
    print(">> 结论: 大部分 case 告警为空。LLM 缺少语义信号，不应在全部 case 上做重排。")
    print(">> 建议: 仅对告警非空的 case 调用 LLM，其余直接输出算法排名。")
else:
    print(f">> 结论: {total_cases - empty_cases} 例有告警数据，LLM 重排有信息基础。")
