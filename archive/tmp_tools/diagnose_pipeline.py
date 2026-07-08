"""
三方面诊断:
  1. 候选集是否过小
  2. 管道的初筛是否过度缩减
  3. 是否有数据泄漏

用法:
  python archive/tmp_tools/diagnose_pipeline.py /path/to/nodes_labeled
"""

import json, os, sys
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

try:
    from Sys.config import config

    DEFAULT_DATA_ROOT = config.data.nodes_labeled
    DEFAULT_WEIGHT_PATH = config.data.alarm_weights
except Exception:
    DEFAULT_DATA_ROOT = "/home/sbp/lixinyang/pingmesh/data/node/nodes_max_labeled"
    DEFAULT_WEIGHT_PATH = "/home/sbp/lixinyang/pingmesh/data/weights/classified_alarms/all_alarms.json"

data_root = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DATA_ROOT

# ============================================================
# 1. 候选集大小
# ============================================================
print("=" * 60)
print("1. 每个 case 的候选集大小（全链路设备数）")
print("=" * 60)

sizes = []
small_cases = []  # < 10 设备
for dirpath, _, filenames in os.walk(data_root):
    for f in filenames:
        if "全链路.json" in f and "pingmesh" in f:
            raw = json.load(open(os.path.join(dirpath, f), "r", encoding="utf-8"))
            nodes = list(raw.values()) if isinstance(raw, dict) else raw
            n = len(nodes)
            sizes.append(n)
            if n < 10:
                small_cases.append((os.path.basename(dirpath), n))
            break

if sizes:
    print(f"  case 总数: {len(sizes)}")
    print(f"  设备数范围: min={min(sizes)}  max={max(sizes)}  median={sorted(sizes)[len(sizes)//2]}")
    dist = Counter()
    for s in sizes:
        if s < 5: dist["<5"] += 1
        elif s < 10: dist["5-9"] += 1
        elif s < 20: dist["10-19"] += 1
        elif s < 50: dist["20-49"] += 1
        elif s < 100: dist["50-99"] += 1
        elif s < 200: dist["100-199"] += 1
        else: dist["200+"] += 1
    print("  分布:")
    for k in ["<5", "5-9", "10-19", "20-49", "50-99", "100-199", "200+"]:
        if dist[k]:
            print(f"    {k:>8}: {dist[k]} ({100*dist[k]//max(1,len(sizes))}%)")

if small_cases:
    print(f"\n  ⚠️ 设备数 < 10 的 case: {len(small_cases)} 个")
    if len(small_cases) > len(sizes) * 0.1:
        print(f"  >> 超过 10% 的 case 候选集过小，Top-3/Top-5 自然会收敛到 Top-1")
    for csn, n in small_cases[:5]:
        print(f"    {csn}: {n} 台设备")
    if len(small_cases) > 5:
        print(f"    ... 还有 {len(small_cases)-5} 个")
else:
    print(f"\n  ✓ 所有 case 设备数 >= 10，候选集充足")


# ============================================================
# 2. 管道初筛检测 — 算法排名后实际有分的设备数
# ============================================================
print()
print("=" * 60)
print("2. 管道内是否有初筛缩减候选")
print("=" * 60)

from Sys.RootCauseAnalyze.skill_pipeline import rank_devices_by_skills
from Sys.RootCauseAnalyze.skills.temporal_ranker import score_temporal
from Sys.RootCauseAnalyze.skills.topo_ranker import score_topo

wpath = DEFAULT_WEIGHT_PATH

scored_count_dist = Counter()
dead_device_cases = []  # 大量设备得分为 0 的 case

for dirpath, _, filenames in os.walk(data_root):
    node_files = [f for f in filenames if "全链路.json" in f and "pingmesh" in f]
    if not node_files or "info.json" not in filenames:
        continue
    try:
        raw = json.load(open(os.path.join(dirpath, node_files[0]), "r", encoding="utf-8"))
        nodes = list(raw.values()) if isinstance(raw, dict) else raw
        info = json.load(open(os.path.join(dirpath, "info.json"), "r", encoding="utf-8"))
    except Exception:
        continue

    scores_pr = score_topo(nodes, info, weight_path=wpath, directed=True)
    scores_ts = score_temporal(nodes, info, dirpath=dirpath)

    n_total = len(nodes)
    n_scored = sum(1 for ip in scores_pr if scores_pr.get(ip, 0) > 0
                   or scores_ts.get(ip, 0) > 0)
    n_zero = n_total - n_scored

    if n_total < 20: scored_count_dist["<20"] += 1
    else: scored_count_dist[f"{n_scored}/{n_total}"] += 0  # just count ratios

    ratio = n_zero / max(1, n_total)
    bucket = f"{int(ratio*100)}%"
    if n_zero > n_total * 0.8 and n_total >= 20:
        dead_device_cases.append((os.path.basename(dirpath), n_zero, n_total))

if dead_device_cases:
    print(f"  ⚠️ 设备中 >80% 得分为 0 的 case: {len(dead_device_cases)} 个")
    print(f"     含义: 绝大多数设备在 PR 和时序上都拿 0 分")
    print(f"     原因: 设备 alarms/logs 全空 + personalization 无区分度")
    for csn, nz, nt in dead_device_cases[:5]:
        print(f"    {csn}: {nz}/{nt} 设备得分=0")
    if len(dead_device_cases) > 5:
        print(f"    ... 还有 {len(dead_device_cases)-5} 个")
else:
    print(f"  ✓ 没有大比例得分为 0 的 case")

# 算法输出中实际有几分能拿到非零 score
topk_check = 5
from Sys.RootCauseAnalyze.skill_pipeline import rank_devices_by_skills
dup_top5 = 0
for dirpath, _, filenames in os.walk(data_root):
    node_files = [f for f in filenames if "全链路.json" in f and "pingmesh" in f]
    if not node_files or "info.json" not in filenames: continue
    try:
        raw = json.load(open(os.path.join(dirpath, node_files[0]), "r", encoding="utf-8"))
        nodes = list(raw.values()) if isinstance(raw, dict) else raw
        info = json.load(open(os.path.join(dirpath, "info.json"), "r", encoding="utf-8"))
        ips, _ = rank_devices_by_skills(nodes, info, dirpath, skill_ids=[1,2], directed=True, weight_dirpath=wpath)
        if len(set(ips[:5])) < min(5, len(nodes)):
            dup_top5 += 1
    except: pass

print(f"\n  Top-5 有重复 IP: {dup_top5} 例（pool 不足时可能发生）")


# ============================================================
# 3. 数据泄漏检测
# ============================================================
print()
print("=" * 60)
print("3. 数据泄漏检测")
print("=" * 60)

# 3.1 代码层面: 推理路径是否读 label.json
leak_sources = []

# 检查 evidence_fusion.py
with open("Sys/RootCauseAnalyze/evidence_fusion.py", "r", encoding="utf-8") as f:
    ef_src = f.read()
if any(s in ef_src for s in ["_read_label_timestamps", "label.json"]):
    leak_sources.append("evidence_fusion.py 含 label 引用")

# 检查当前 ranker 实现
for path, name in [
    ("Sys/RootCauseAnalyze/skills/topo_ranker.py", "topo_ranker.py"),
    ("Sys/RootCauseAnalyze/skills/temporal_ranker.py", "temporal_ranker.py"),
]:
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if "label.json" in src:
        leak_sources.append(f"{name} 含 label.json 引用")

if leak_sources:
    for s in leak_sources:
        print(f"  ❌ {s}")
else:
    print(f"  ✓ 推理路径代码不含 label.json 引用")

# 3.2 数据层面: gt IP 是否只通过全链路文件进入 prompt
# 抽样检查 5 个 case
print()
print("  --- 抽样验证: gt IP 是否在全链路文件中合法出现 ---")
sample_count = 0
leak_count = 0

for dirpath, _, filenames in os.walk(data_root):
    if sample_count >= 10:
        break

    node_files = [f for f in filenames if "全链路.json" in f and "pingmesh" in f]
    label_path = os.path.join(dirpath, "label.json")
    if not node_files or not os.path.exists(label_path):
        continue

    try:
        raw = json.load(open(os.path.join(dirpath, node_files[0]), "r", encoding="utf-8"))
        nodes = list(raw.values()) if isinstance(raw, dict) else raw
        labels = json.load(open(label_path, "r", encoding="utf-8"))
    except Exception:
        continue

    if not isinstance(labels, list):
        continue

    # 提取 gt IPs
    labels_sorted = sorted(labels, key=lambda x: x.get("ranking", 999))
    gt_ips = set()
    for lb in labels_sorted[:3]:
        for an in lb.get("abnormal_node", []):
            if an.get("ip"):
                gt_ips.add(an["ip"])

    if not gt_ips:
        continue

    # gt IPs 是否在全链路文件的 mgmt_ip 中存在？
    full_node_ips = set()
    for n in nodes:
        ip = n.get("mgmt_ip", n.get("ip", n.get("name", "")))
        if ip:
            full_node_ips.add(ip)

    missing = gt_ips - full_node_ips
    sample_count += 1
    if missing:
        leak_count += 1
        if leak_count <= 3:
            print(f"  ⚠️ {os.path.basename(dirpath)}: gt IPs {missing} 不在全链路文件中")

print(f"\n  {sample_count} 个抽样 case 中, {sample_count - leak_count} 个 gt IP 在全链路文件中存在")
if leak_count > 0:
    print(f"  ⚠️ {leak_count} 个 case 的 gt IP 不在全链路文件中")
    print(f"  >> 可能是标注了外部设备, 或者是全链路数据不完整")
else:
    print(f"  ✓ gt IP 全部在全链路文件中合法存在")


# ============================================================
# 4. 告警覆盖度 — 多少设备实际有告警/时间戳？
# ============================================================
print()
print("=" * 60)
print("4. 每 case 中存在告警/日志的设备数（时序有效候选池）")
print("=" * 60)

alarm_counts = []  # 每个 case 中有告警的设备数
alarm_ratios = []  # ratio of devices with alarms

for dirpath, _, filenames in os.walk(data_root):
    node_files = [f for f in filenames if "全链路.json" in f and "pingmesh" in f]
    if not node_files or "info.json" not in filenames:
        continue
    try:
        raw = json.load(open(os.path.join(dirpath, node_files[0]), "r", encoding="utf-8"))
        nodes = list(raw.values()) if isinstance(raw, dict) else raw
    except Exception:
        continue

    n_total = len(nodes)
    n_with_alarms = 0
    n_with_timestamps = 0  # alarms that actually have alarm_time
    for nd in nodes:
        has = False
        has_ts = False
        for evt in nd.get("alarms", []) + nd.get("logs", []):
            if not isinstance(evt, dict):
                continue
            has = True
            if evt.get("alarm_time") or evt.get("time"):
                has_ts = True
        if has:
            n_with_alarms += 1
        if has_ts:
            n_with_timestamps += 1

    alarm_counts.append(n_with_alarms)
    alarm_ratios.append(n_with_alarms / max(1, n_total))
    if n_with_alarms <= 3 and n_total >= 50:
        if len([x for x in alarm_counts if x <= 3]) <= 5:
            print(f"  ⚠️ {os.path.basename(dirpath)}: {n_with_alarms}/{n_total} 设备有告警")

if alarm_counts:
    sorted_ac = sorted(alarm_counts)
    print(f"  有告警的设备数: min={min(alarm_counts)}  median={sorted_ac[len(sorted_ac)//2]}  max={max(alarm_counts)}")
    # distribution
    dist = Counter()
    for a in alarm_counts:
        if a == 0: dist["0"] += 1
        elif a <= 2: dist["1-2"] += 1
        elif a <= 5: dist["3-5"] += 1
        elif a <= 10: dist["6-10"] += 1
        elif a <= 20: dist["11-20"] += 1
        else: dist["20+"] += 1
    print("  分布 (有告警的设备数):")
    for k in ["0", "1-2", "3-5", "6-10", "11-20", "20+"]:
        if dist[k]:
            print(f"    {k:>6}: {dist[k]} ({100*dist[k]//max(1,len(alarm_counts))}%)")

    # 关键指标: 多少 case 只有 ≤5 台设备有告警
    few = sum(1 for a in alarm_counts if a <= 5)
    pct = 100 * few // max(1, len(alarm_counts))
    print(f"\n  ≤5 台设备有告警: {few}/{len(alarm_counts)} ({pct}%)")
    if pct >= 30:
        print(f"  ⚠️ 超过 30% 的 case 有效时序候选 ≤5 → temporal 只能给 5 台设备排分")
        print(f"  >> 这便是 Top-3 和 Top-5 接近的根本原因:")
        print(f"  >> temporal 把有告警的 3-5 台设备排前面, 其余 200+ 台全是 0 分")
        print(f"  >> 等权融合后, topo 信号无法在 temporal=0 的设备间制造区分度")


# ============================================================
# 汇总
# ============================================================
print()
print("=" * 60)
print("诊断汇总")
print("=" * 60)
issues = []

if small_cases and len(small_cases) > len(sizes) * 0.1:
    issues.append(f"候选集过小: {len(small_cases)} 个 case 设备数 < 10")

if dead_device_cases:
    issues.append(f"得分为 0: {len(dead_device_cases)} 个 case 超过 80% 设备无有效得分")

if leak_sources:
    for s in leak_sources:
        issues.append(f"数据泄漏: {s}")
elif leak_count > 0:
    issues.append(f"gt IP 缺失: {leak_count}/{sample_count} 个 case 的 gt 不在全链路中")

if issues:
    print("发现问题:")
    for i in issues:
        print(f"  - {i}")
else:
    print("✓ 三项检测均无重大问题")
    print()
    if len(sizes) >= 5:
        print(f"  候选集大小: min={min(sizes)} median={sorted(sizes)[len(sizes)//2]} max={max(sizes)}")
        if min(sizes) >= 20:
            print(f"  → 候选集足够大, Top-3 和 Top-5 不会因 pool 太小而重合")
        print(f"  推理路径无 label.json 泄漏")
        print(f"  → 如果 Top-3 和 Top-5 依然接近, 原因:")
        print(f"    ① 大量 case 只有少数设备有告警 → temporal 有效候选池极小")
        print(f"    ② {100 - 56.64:.0f}% 的失败 case 中根因不在任何算法的 Top-5")
