"""
数据感知 + 过滤脚本
===================
1. 扫描 data/pingmesh_extend, 统计每 case 的告警数、设备数、gt 覆盖
2. 过滤告警数过少和 gt 不在候选集的 case
3. 将通过的 case 输出到 data/nodes_extend

用法:
  python tmp/perceive_and_filter.py [--write]
"""

import os
import json
import shutil
import sys
from collections import Counter

SRC = "/home/sbp/lixinyang/pingmesh/data/pingmesh_extend"
DST = "/home/sbp/lixinyang/pingmesh/data/nodes_extend"

WRITE = "--write" in sys.argv

# ══════════════════════════════════════════════════════════════════
# 1. 扫描 + 统计
# ══════════════════════════════════════════════════════════════════

cases = []  # [{csn, path, filename, n_devices, n_alarms, n_with_alarms, gt_ips, gt_in_topo}]

for fname in sorted(os.listdir(SRC)):
    if not fname.endswith(".json"):
        continue

    fpath = os.path.join(SRC, fname)
    try:
        raw = json.load(open(fpath, "r", encoding="utf-8"))
    except Exception as e:
        print(f"  skip {fname}: JSON 解析失败 ({e})")
        continue

    # 提取 csn
    parts = fname.replace(".json", "").split("-")
    csn = parts[1] if len(parts) >= 2 else fname.replace(".json", "")

    # ── 必填字段校验 ──
    full_link = raw.get("full_link")
    if not isinstance(full_link, dict):
        print(f"  skip {csn}: 缺少 full_link")
        continue

    task_info = full_link.get("task_info")
    if not isinstance(task_info, dict):
        print(f"  skip {csn}: 缺少 task_info")
        continue

    alarm_time = task_info.get("alarm_time")
    if not alarm_time:
        print(f"  skip {csn}: 缺少 alarm_time")
        continue

    topo_value = full_link.get("task_topo", {}).get("value")
    if not isinstance(topo_value, list) or not topo_value:
        print(f"  skip {csn}: 缺少 task_topo.value")
        continue

    # source_ip / sink_ip（info.json 必需）
    if not task_info.get("source_ip") or not task_info.get("sink_ip"):
        print(f"  skip {csn}: 缺少 source_ip 或 sink_ip")
        continue

    # gt
    gt_label = full_link.get("groud_truth",
               full_link.get("ground_truth",
               full_link.get("grond_truth")))
    if not isinstance(gt_label, dict):
        print(f"  skip {csn}: 缺少 ground_truth")
        continue

    abnormal = gt_label.get("abnormal_node")
    if not isinstance(abnormal, list) or not abnormal:
        print(f"  skip {csn}: 缺少 abnormal_node")
        continue

    # 每个 abnormal_node 必须有 ip 或 mgmt_ip
    has_valid_gt = False
    for an in abnormal:
        if not isinstance(an, dict):
            continue
        if an.get("ip") or an.get("mgmt_ip"):
            has_valid_gt = True
            break
    if not has_valid_gt:
        print(f"  skip {csn}: abnormal_node 中无有效 IP")
        continue

    # ── 统计 ──
    n_alarms = 0
    n_logs = 0
    devices_with_alarms = set()
    devices_with_ts = set()

    # 从 task_topo 中提取节点统计
    topo_value = full_link.get("task_topo", {}).get("value", [])
    all_device_ips = set()
    all_device_names = set()

    for path in topo_value:
        for segment in path:
            for node in segment.get("nodes", []):
                ip = node.get("mgmt_ip", "")
                name = node.get("name", "")
                if ip: all_device_ips.add(ip)
                if name: all_device_names.add(name)

    # 从 alarm_list / log_list 统计告警
    alarm_list = full_link.get("alarm_list", [])
    log_list = full_link.get("log_list", {})

    for a in alarm_list:
        if isinstance(a, dict):
            n_alarms += 1
            dev_ip = a.get("mgmt_ip", a.get("device_ip", ""))
            if dev_ip:
                devices_with_alarms.add(dev_ip)
                if a.get("alarm_time"):
                    devices_with_ts.add(dev_ip)

    if isinstance(log_list, dict):
        log_items = log_list.get("data", log_list.get("logs", []))
        for l in log_items:
            if isinstance(l, dict):
                n_logs += 1

    # ── gt（复用上面已验证的变量）──
    gt_ips = []
    for an in abnormal:
        ip = an.get("ip", an.get("mgmt_ip", ""))
        if ip:
            gt_ips.append(ip)

    gt_in_topo = all(g in all_device_ips for g in gt_ips) if gt_ips else False

    n_devices = len(all_device_ips)
    n_with_alarms = len(devices_with_alarms)

    cases.append({
        "csn": csn,
        "path": fpath,
        "filename": fname,
        "n_devices": n_devices,
        "n_alarms_total": n_alarms + n_logs,
        "n_alarms": n_alarms,
        "n_logs": n_logs,
        "n_with_alarms": n_with_alarms,
        "n_with_ts": len(devices_with_ts),
        "gt_ips": gt_ips,
        "gt_in_topo": gt_in_topo,
    })

# ══════════════════════════════════════════════════════════════════
# 2. 报告
# ══════════════════════════════════════════════════════════════════

print("=" * 60)
print(f"数据感知报告: {SRC}")
print("=" * 60)
print(f"总文件数: {len(cases)}")
print()

# ── 告警分布 ──
alarm_counts = [c["n_alarms_total"] for c in cases]
print(f"告警+日志数: min={min(alarm_counts) if alarm_counts else 0}  "
      f"median={sorted(alarm_counts)[len(alarm_counts)//2] if alarm_counts else 0}  "
      f"max={max(alarm_counts) if alarm_counts else 0}")

dist = Counter()
for a in alarm_counts:
    if a == 0: dist["0"] += 1
    elif a <= 10: dist["1-10"] += 1
    elif a <= 50: dist["11-50"] += 1
    elif a <= 100: dist["51-100"] += 1
    elif a <= 500: dist["101-500"] += 1
    else: dist["500+"] += 1
print("  告警数分布:")
for k in ["0", "1-10", "11-50", "51-100", "101-500", "500+"]:
    if dist[k]:
        print(f"    {k:>8}: {dist[k]}")

# ── 有告警的设备数 ──
wa = [c["n_with_alarms"] for c in cases]
print(f"\n有告警的设备数: min={min(wa) if wa else 0}  "
      f"median={sorted(wa)[len(wa)//2] if wa else 0}  max={max(wa) if wa else 0}")
dist2 = Counter()
for a in wa:
    if a <= 2: dist2["≤2"] += 1
    elif a <= 5: dist2["3-5"] += 1
    elif a <= 10: dist2["6-10"] += 1
    elif a <= 20: dist2["11-20"] += 1
    else: dist2["20+"] += 1
print("  分布:")
for k in ["≤2", "3-5", "6-10", "11-20", "20+"]:
    if dist2[k]:
        print(f"    {k:>6}: {dist2[k]}")

# ── 设备数 ──
devs = [c["n_devices"] for c in cases]
print(f"\n每 case 设备数: min={min(devs) if devs else 0}  "
      f"median={sorted(devs)[len(devs)//2] if devs else 0}  max={max(devs) if devs else 0}")

# ── gt 覆盖 ──
gt_ok = sum(1 for c in cases if c["gt_ips"] and c["gt_in_topo"])
gt_missing = sum(1 for c in cases if c["gt_ips"] and not c["gt_in_topo"])
gt_none = sum(1 for c in cases if not c["gt_ips"])
print(f"\ngt 覆盖率:")
print(f"  gt 存在且在全链路 topo 中: {gt_ok}")
print(f"  gt 存在但不在 topo 中:    {gt_missing}")
print(f"  无 gt 标注:               {gt_none}")

# ══════════════════════════════════════════════════════════════════
# 3. 过滤
# ══════════════════════════════════════════════════════════════════

print()
print("=" * 60)
print("过滤条件: n_with_alarms >= 5 AND gt_in_topo = True")
print("=" * 60)

passed = []
rejected = {"low_alarms": [], "gt_missing": [], "both": []}

for c in cases:
    low = c["n_with_alarms"] < 5
    no_gt = not c["gt_ips"] or not c["gt_in_topo"]

    if low and no_gt:
        rejected["both"].append(c)
    elif low:
        rejected["low_alarms"].append(c)
    elif no_gt:
        rejected["gt_missing"].append(c)
    else:
        passed.append(c)

print(f"通过: {len(passed)}")
print(f"拒绝 — 告警数不足: {len(rejected['low_alarms'])}")
print(f"拒绝 — gt 不在 topo: {len(rejected['gt_missing'])}")
print(f"拒绝 — 两者: {len(rejected['both'])}")

if not passed:
    print("\n>> 无 case 通过过滤。尝试放宽条件:")
    # 只要求 gt 存在
    relaxed = [c for c in cases if c["gt_ips"] and c["gt_in_topo"]]
    print(f">> 仅要求 gt_in_topo: {len(relaxed)} 个")
    if len(relaxed) > 0:
        print(">> 建议使用这些 case, 然后依赖后续算法处理告警稀疏问题")
        passed = relaxed

# ══════════════════════════════════════════════════════════════════
# 4. 输出
# ══════════════════════════════════════════════════════════════════

if WRITE and passed:
    if os.path.exists(DST):
        shutil.rmtree(DST)
    os.makedirs(DST, exist_ok=True)

    for c in passed:
        csn = c["csn"]
        case_dir = os.path.join(DST, csn)
        os.makedirs(case_dir, exist_ok=True)

        # 读原始数据
        raw = json.load(open(c["path"], "r", encoding="utf-8"))
        full_link = raw.get("full_link", {})

        # ── 构造 info.json（与 Collector 输出格式一致）──
        task_info = full_link.get("task_info", {})
        alarm_content = {
            "alarm_name": "",
            "alarm_time": task_info.get("alarm_time"),
            "source_ip": json.dumps(task_info.get("source_ip", [])),
            "sink_ip": json.dumps(task_info.get("sink_ip", [])),
            "analysis_type": task_info.get("analysis_type", ""),
            "scenario_code": task_info.get("scenario_code", ""),
            "task_num": task_info.get("task_num", 0),
            "alarm_description": task_info.get("alarm_description", ""),
            "src_tunnel_ip": task_info.get("src_tunnel_ip", ""),
            "dst_tunnel_ip": task_info.get("dst_tunnel_ip", ""),
            "csn": csn,
        }
        json.dump(alarm_content, open(os.path.join(case_dir, "info.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

        # ── 构造 label.json（从 ground_truth 提取）──
        gt = full_link.get("groud_truth",
              full_link.get("ground_truth",
              full_link.get("grond_truth", {})))
        if isinstance(gt, dict):
            labels = [{
                "ranking": gt.get("ranking", 1),
                "abnormal_node": gt.get("abnormal_node", []),
            }]
        else:
            labels = []
        json.dump(labels, open(os.path.join(case_dir, "label.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

        # ── 构造 pingmesh-{csn}-全链路.json ──
        # 从 task_topo 提取节点, 附加 alarm_list/log_list 中的告警
        node_map = {}  # mgmt_ip → node dict
        topo_value = full_link.get("task_topo", {}).get("value", [])
        for path in topo_value:
            for segment in path:
                for node in segment.get("nodes", []):
                    ip = node.get("mgmt_ip", "")
                    if not ip:
                        continue
                    if ip not in node_map:
                        node_map[ip] = {
                            "role": node.get("role", ""),
                            "mgmt_ip": ip,
                            "name": node.get("name", ""),
                            "linked_from": [],
                            "linked_to": [],
                            "alarms": [],
                            "logs": [],
                            "cross": 0,
                        }

        # 填充 linked_from / linked_to（从 paths 中推导邻接关系）
        for path in topo_value:
            for segment in path:
                seg_nodes = []
                for node in segment.get("nodes", []):
                    ip = node.get("mgmt_ip", "")
                    if ip: seg_nodes.append(ip)
                for i in range(len(seg_nodes)):
                    ip = seg_nodes[i]
                    if ip not in node_map: continue
                    if i > 0:
                        node_map[ip].setdefault("linked_from", [])
                        if seg_nodes[i-1] not in node_map[ip]["linked_from"]:
                            node_map[ip]["linked_from"].append(seg_nodes[i-1])
                    if i < len(seg_nodes) - 1:
                        node_map[ip].setdefault("linked_to", [])
                        if seg_nodes[i+1] not in node_map[ip]["linked_to"]:
                            node_map[ip]["linked_to"].append(seg_nodes[i+1])

        # 填充 alarms / logs
        alarm_list = full_link.get("alarm_list", [])
        for a in alarm_list:
            if not isinstance(a, dict): continue
            dev_ip = a.get("mgmt_ip", a.get("device_ip", ""))
            if dev_ip in node_map:
                node_map[dev_ip].setdefault("alarms", []).append(a)

        log_items = full_link.get("log_list", {}).get("data", []) if isinstance(full_link.get("log_list", {}), dict) else []
        for l in log_items:
            if not isinstance(l, dict): continue
            dev_ip = l.get("mgmt_ip", l.get("device_ip", ""))
            if dev_ip in node_map:
                node_map[dev_ip].setdefault("logs", []).append(l)

        # 输出
        out_name = f"pingmesh-{csn}-全链路.json"
        json.dump(node_map, open(os.path.join(case_dir, out_name), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

    print(f"\n>> 已写入 {len(passed)} 个 case 到 {DST}")
elif not WRITE:
    print()
    print(">> DRY RUN — 加 --write 参数执行写入")
