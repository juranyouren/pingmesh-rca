"""
将 rootcause_analysis 中的 alarms/syslogs 填回对应设备的 alarm_list / log_list。

pingmesh_extend 原始数据中，根因设备的告警信息可能只存在于 rootcause_analysis 字段，
而不在 full_link.alarm_list 中。此脚本将 rootcause_analysis[0].abnormal_node 中的
alarms/syslogs 按 mgmt_ip 匹配填充到 full_link.task_topo 的对应节点上。

用法:
  python tmp/restore_alarms_from_rootcause.py /path/to/pingmesh_extend [--write]
"""

import os
import json
import sys
import shutil

SRC = sys.argv[1] if len(sys.argv) > 1 else "/home/sbp/lixinyang/pingmesh/data/pingmesh_extend"
DST = SRC + "_restored"
WRITE = "--write" in sys.argv

def get_device_ip(node):
    return node.get("mgmt_ip", node.get("ip", node.get("name", "")))

def restore_file(fpath):
    """对单个文件执行填充，返回 (ok, filled_count, total_devices, data)。"""
    try:
        data = json.load(open(fpath, "r", encoding="utf-8"))
    except Exception:
        return False, 0, 0, None

    full_link = data.get("full_link", {})
    if not isinstance(full_link, dict):
        return False, 0, 0, None

    # 读取 rootcause_analysis
    rca = full_link.get("rootcause_analysis")
    if not isinstance(rca, list) or len(rca) == 0:
        return False, 0, 0, None

    rca_item = rca[0]
    if not isinstance(rca_item, dict):
        return False, 0, 0, None

    abnormal_nodes = rca_item.get("abnormal_node", [])
    if not isinstance(abnormal_nodes, list) or not abnormal_nodes:
        return False, 0, 0, None

    # 从 rootcause_analysis 中收集每 IP 的 alarms/syslogs
    label_data_by_ip = {}
    for an in abnormal_nodes:
        if not isinstance(an, dict):
            continue
        ip = an.get("ip", an.get("mgmt_ip", ""))
        if not ip:
            continue
        if ip not in label_data_by_ip:
            label_data_by_ip[ip] = {"alarms": [], "syslogs": []}
        for key in ("alarms", "syslogs"):
            for evt in an.get(key, []):
                if evt and evt not in label_data_by_ip[ip][key]:
                    label_data_by_ip[ip][key].append(evt)

    if not label_data_by_ip:
        return False, 0, 0, None

    # 遍历 task_topo 中的所有节点，匹配 IP 并填充
    topo_value = full_link.get("task_topo", {}).get("value", [])
    total_devices = 0
    filled_count = 0

    # 收集所有节点到 flat dict
    node_by_ip = {}
    for path in topo_value:
        for segment in path:
            for node in segment.get("nodes", []):
                ip = get_device_ip(node)
                if ip and ip != "unknown":
                    node_by_ip[ip] = node
                    total_devices += 1

    # 填充
    for ip, label_info in label_data_by_ip.items():
        node = node_by_ip.get(ip)
        if not node:
            continue

        # 合并 alarms
        existing_alarm_names = set()
        for a in node.get("alarms", []):
            name = a if isinstance(a, str) else a.get("alarm_name", a.get("name", ""))
            if name:
                existing_alarm_names.add(name)

        for new_a in label_info["alarms"]:
            name = new_a if isinstance(new_a, str) else new_a.get("alarm_name", new_a.get("name", ""))
            if name and name not in existing_alarm_names:
                node.setdefault("alarms", []).append(new_a)
                existing_alarm_names.add(name)

        # 合并 syslogs
        existing_log_names = set()
        for l in node.get("logs", []):
            name = l if isinstance(l, str) else l.get("alarm_name", l.get("name", ""))
            if name:
                existing_log_names.add(name)

        for new_l in label_info["syslogs"]:
            name = new_l if isinstance(new_l, str) else new_l.get("alarm_name", new_l.get("name", ""))
            if name and name not in existing_log_names:
                node.setdefault("logs", []).append(new_l)
                existing_log_names.add(name)

        filled_count += 1

    # 也填充 full_link.alarm_list（如果存在）
    alarm_list = full_link.get("alarm_list", [])
    existing_alarm_ids = set()
    for a in alarm_list:
        if isinstance(a, dict):
            aid = a.get("alarm_id", a.get("id", ""))
            if aid:
                existing_alarm_ids.add(str(aid))

    for label_info in label_data_by_ip.values():
        for new_a in label_info["alarms"]:
            if isinstance(new_a, dict):
                aid = new_a.get("alarm_id", new_a.get("id", ""))
                if aid and str(aid) not in existing_alarm_ids:
                    alarm_list.append(new_a)
                    existing_alarm_ids.add(str(aid))

    if alarm_list:
        full_link["alarm_list"] = alarm_list

    return True, filled_count, total_devices, data

# ══════════════════════════════════════════════════════════════════

print("=" * 60)
print(f"rootcause_analysis 告警回填")
print(f"  源目录: {SRC}")
print(f"  输出:   {DST}")
print("=" * 60)

files = [f for f in os.listdir(SRC) if f.endswith(".json")]
print(f"JSON 文件数: {len(files)}")

ok = skip = fail = 0
total_filled = 0
total_devices = 0

if WRITE:
    if os.path.exists(DST):
        shutil.rmtree(DST)
    os.makedirs(DST, exist_ok=True)

for fname in sorted(files):
    fpath = os.path.join(SRC, fname)
    success, filled, ndevices, modified_data = restore_file(fpath)

    if not success:
        skip += 1
        continue

    ok += 1
    total_filled += filled
    total_devices += ndevices

    if WRITE and modified_data is not None:
        json.dump(modified_data, open(os.path.join(DST, fname), "w", encoding="utf-8"),
                  ensure_ascii=False)

print(f"\n处理: {ok}  跳过(无 rootcause_analysis): {skip}  失败: {fail}")
print(f"总设备: {total_devices}  已填充: {total_filled}")

if not WRITE:
    print(f"\n>> DRY RUN — 加 --write 执行写入到 {DST}")
else:
    print(f"\n>> 已写入 {DST}")
