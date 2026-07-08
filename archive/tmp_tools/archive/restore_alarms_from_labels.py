"""
将 label.json 中的 syslogs/alarms 填回 pingmesh-*-全链路.json 对应设备。

label.json 中 abnormal_node 的 syslogs/alarms 是保留的原始生产数据，
不是标注信息。填回全链路文件后，所有算法公平获取同一份数据。

Deprecated archived script. Prefer restoring from raw rootcause_analysis.

用法（先在单 case 上试）：
  python archive/tmp_tools/archive/restore_alarms_from_labels.py --dry-run /path/to/nodes_labeled
确认无误后去掉 --dry-run 正式运行。
"""

import os
import json
import argparse
import copy


def restore_case(dirpath, dry_run=True):
    """对一个 case 目录执行回填。"""
    # 找全链路文件
    node_file = None
    for fn in os.listdir(dirpath):
        if "全链路.json" in fn and "pingmesh" in fn:
            node_file = os.path.join(dirpath, fn)
            break
    if not node_file:
        return None

    # 找 label.json
    label_path = os.path.join(dirpath, "label.json")
    if not os.path.exists(label_path):
        return None

    # 读全链路
    try:
        with open(node_file, "r", encoding="utf-8") as f:
            full_data = json.load(f)
    except Exception:
        return None

    # 读 label
    try:
        with open(label_path, "r", encoding="utf-8") as f:
            labels = json.load(f)
    except Exception:
        return None

    if not isinstance(labels, list):
        return None

    # 从 label 中收集每 IP 的 syslogs + alarms
    label_data_by_ip = {}
    for item in labels:
        for node in item.get("abnormal_node", []):
            ip = node.get("ip", "")
            if not ip:
                continue
            if ip not in label_data_by_ip:
                label_data_by_ip[ip] = {"alarms": [], "syslogs": []}
            for key in ("alarms", "syslogs"):
                for evt in node.get(key, []):
                    if evt and evt not in label_data_by_ip[ip][key]:
                        label_data_by_ip[ip][key].append(evt)

    if not label_data_by_ip:
        return None

    # 在全链路中找对应设备并填充
    if isinstance(full_data, dict):
        nodes = list(full_data.values())
        is_dict = True
    else:
        nodes = full_data
        is_dict = False

    filled_count = 0
    for nd in nodes:
        ip = nd.get("mgmt_ip", nd.get("ip", nd.get("name", "")))
        if ip not in label_data_by_ip:
            continue

        label_info = label_data_by_ip[ip]

        # 合并 alarms（保留原有的，补充 label 中的）
        existing_alarm_names = set()
        for a in nd.get("alarms", []):
            name = a if isinstance(a, str) else a.get("alarm_name", a.get("name", ""))
            if name:
                existing_alarm_names.add(name)

        for new_a in label_info["alarms"]:
            name = new_a if isinstance(new_a, str) else new_a.get("alarm_name", new_a.get("name", ""))
            if name and name not in existing_alarm_names:
                nd.setdefault("alarms", []).append(new_a)
                existing_alarm_names.add(name)

        # 合并 syslogs
        existing_log_names = set()
        for l in nd.get("logs", []):
            name = l if isinstance(l, str) else l.get("alarm_name", l.get("name", ""))
            if name:
                existing_log_names.add(name)

        for new_l in label_info["syslogs"]:
            name = new_l if isinstance(new_l, str) else new_l.get("alarm_name", new_l.get("name", ""))
            if name and name not in existing_log_names:
                nd.setdefault("logs", []).append(new_l)
                existing_log_names.add(name)

        filled_count += 1

    if is_dict:
        # 重建 dict（mgmt_ip 为 key）
        rebuilt = {}
        for nd in nodes:
            key = nd.get("mgmt_ip", nd.get("ip", nd.get("name", "unknown")))
            rebuilt[key] = nd
        full_data = rebuilt
    else:
        full_data = nodes

    if not dry_run:
        # 备份原文件
        backup = node_file + ".bak"
        if not os.path.exists(backup):
            with open(backup, "w", encoding="utf-8") as f:
                json.dump(json.load(open(node_file, "r", encoding="utf-8")), f, ensure_ascii=False)

        with open(node_file, "w", encoding="utf-8") as f:
            json.dump(full_data, f, ensure_ascii=False, indent=2)

    return {"dir": dirpath, "filled_devices": filled_count, "total_devices": len(nodes),
            "label_ips": list(label_data_by_ip.keys())}


def main():
    p = argparse.ArgumentParser(description="将 label.json 的 syslogs/alarms 填回全链路文件")
    p.add_argument("data_root", help="nodes_labeled 目录")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="仅检查不写入 (默认)")
    p.add_argument("--write", dest="dry_run", action="store_false",
                   help="正式写入")
    args = p.parse_args()

    results = []
    for dirpath, _, filenames in os.walk(args.data_root):
        r = restore_case(dirpath, dry_run=args.dry_run)
        if r:
            results.append(r)

    total_filled = sum(r["filled_devices"] for r in results)
    total_devices = sum(r["total_devices"] for r in results)

    print(f"扫描 {len(results)} 个 case")
    print(f"总共 {total_devices} 台设备, 其中从 label 回填了 {total_filled} 台")
    print(f"平均每 case 回填 {total_filled / max(1, len(results)):.1f} 台设备")
    print()
    if args.dry_run:
        print(">>> DRY RUN — 未修改任何文件。确认无误后加 --write 正式执行 <<<")
    else:
        print(">>> 已写入。原文件备份为 *.bak <<<")


if __name__ == "__main__":
    main()
