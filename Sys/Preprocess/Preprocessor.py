"""
数据预处理器
============
整合 RAW 数据 → NODE 数据的全流程。

阶段:
  Phase 1 — Raw Cleanup:  合并同 csn 文件, 互补缺失键
  Phase 2 — Validate & Extract: 校验必填字段, 提取 info/label/nodes
  Phase 3 — Prune (可选): 拓扑剪枝

数据用词约定:
  raw  = pingmesh_extend 下的原始 JSON (含 full_link.task_topo 等)
  node = 提取后的结构化数据 (info.json + label.json + pingmesh-{csn}-全链路.json)

用法:
  # 全流程
  python Sys/Preprocess/Preprocessor.py \
    --raw data/pingmesh_extend --out data/nodes_extend --write

  # 仅 Phase 1 (合并)
  python Sys/Preprocess/Preprocessor.py \
    --raw data/pingmesh_extend --out data/nodes_merged --phase merge --write

  # 仅 Phase 2
  python Sys/Preprocess/Preprocessor.py \
    --raw data/nodes_merged --out data/nodes_final --phase extract --write
"""

import os, json, sys, shutil
from collections import defaultdict, Counter


# ══════════════════════════════════════════════════════════════════
# Phase 1: Raw Cleanup — 合并同 CSN 文件
# ══════════════════════════════════════════════════════════════════

def extract_csn(fname):
    """pingmesh-756668925-xxx.json / merged_pingmesh-756668925-xxx.json → 756668925"""
    name = fname.replace(".json", "")
    parts = name.split("-")
    if "merged_pingmesh" in parts:
        idx = parts.index("merged_pingmesh")
    elif "pingmesh" in parts:
        idx = parts.index("pingmesh")
    else:
        return None
    return parts[idx + 1] if idx + 1 < len(parts) else None


def deep_merge(base, other):
    """递归合并, other 补充 base 中缺失/为空的键。已有非空键不覆盖。"""
    if not isinstance(base, dict) or not isinstance(other, dict):
        return base
    for key, val in other.items():
        if key not in base:
            base[key] = val
        elif base[key] is None or base[key] == {} or base[key] == []:
            base[key] = val
        elif isinstance(base[key], dict) and isinstance(val, dict):
            deep_merge(base[key], val)
        elif isinstance(base[key], list) and isinstance(val, list) and not base[key]:
            base[key] = val
    return base


def phase_merge(raw_dir, out_dir, write=False):
    """
    Phase 1: 扫描原始目录, 将同 CSN 的多个文件合并为一份,
    输出到 out_dir/{csn}.json。
    """
    files = [f for f in os.listdir(raw_dir) if f.endswith(".json")]
    groups = defaultdict(list)
    unmatched = []

    for fname in sorted(files):
        csn = extract_csn(fname)
        if csn:
            groups[csn].append(os.path.join(raw_dir, fname))
        else:
            unmatched.append(fname)

    singles = sum(1 for v in groups.values() if len(v) == 1)
    multi = sum(1 for v in groups.values() if len(v) > 1)

    print(f"Phase 1 (merge): {len(files)} raw → {len(groups)} CSN ({singles} 单文件, {multi} 多文件合并)")
    if unmatched:
        print(f"  无法解析 CSN: {len(unmatched)}")

    if not write:
        print("  >> DRY RUN — 加 --write 执行")
        return

    os.makedirs(out_dir, exist_ok=True)
    merged_count = 0
    for csn, fpaths in sorted(groups.items()):
        merged = None
        for fp in fpaths:
            try:
                data = json.load(open(fp, "r", encoding="utf-8"))
            except Exception:
                merged = None
                break
            merged = deep_merge(merged, data) if merged is not None else data
        if merged is None:
            continue
        json.dump(merged, open(os.path.join(out_dir, f"{csn}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
        merged_count += 1

    print(f"  >> 已写入 {merged_count} 个合并文件到 {out_dir}")


# ══════════════════════════════════════════════════════════════════
# Phase 2: Validate & Extract — RAW → NODE
# ══════════════════════════════════════════════════════════════════

MIN_DEVICES_WITH_ALARMS = 5   # 有告警的设备数阈值
IRRELEVANT_KEYS = {"node_sign", "type", "devicetype", "verified_hops_to"}


def _get_device_ip(node):
    return node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))


def _validate_raw(csn, full_link):
    """校验必填字段, 返回 (ok, error_msg, task_info, topo_value, gt_label)。"""
    if not isinstance(full_link, dict) or not full_link:
        return False, "full_link 缺失或为空", None, None, None

    task_info = full_link.get("task_info")
    if not isinstance(task_info, dict) or not task_info:
        return False, "task_info 缺失或为空", None, None, None

    alarm_time = task_info.get("alarm_time")
    if not alarm_time:
        return False, "alarm_time 缺失", None, None, None

    topo_value = full_link.get("task_topo", {}).get("value")
    if not isinstance(topo_value, list) or not topo_value:
        return False, "task_topo.value 缺失或为空", None, None, None

    src = task_info.get("source_ip")
    snk = task_info.get("sink_ip")
    if not src or not snk or (isinstance(src, list) and not src) or (isinstance(snk, list) and not snk):
        return False, "source_ip 或 sink_ip 缺失/为空", None, None, None

    gt_label = full_link.get("groud_truth",
                full_link.get("ground_truth",
                full_link.get("grond_truth")))
    if not isinstance(gt_label, dict) or not gt_label:
        rca = full_link.get("rootcause_analysis")
        if isinstance(rca, list) and rca and isinstance(rca[0], dict):
            gt_label = rca[0]

    if not isinstance(gt_label, dict) or not gt_label:
        return False, "ground_truth / rootcause_analysis 缺失或为空", None, None, None

    abnormal = gt_label.get("abnormal_node", [])
    if not isinstance(abnormal, list) or not abnormal:
        return False, "abnormal_node 为空", None, None, None

    has_valid_gt = any(
        isinstance(an, dict) and (an.get("ip") or an.get("mgmt_ip"))
        for an in abnormal
    )
    if not has_valid_gt:
        return False, "abnormal_node 中无有效 IP", None, None, None

    return True, None, task_info, topo_value, gt_label


def _extract_nodes(topo_value, full_link):
    """
    从 task_topo 提取节点, 附加 linked_from/linked_to/cross/alarms/logs。
    返回 {mgmt_ip: {...}} 字典。
    """
    node_map = {}
    ip_to_name = {}

    for path in topo_value:
        for segment in path:
            for node in segment.get("nodes", []):
                d_name = node.get("name")
                d_ip = node.get("mgmt_ip")
                if not d_name or d_name in node_map:
                    continue
                node_map[d_name] = {
                    "role": node.get("role", ""),
                    "mgmt_ip": d_ip,
                    "name": d_name,
                    "linked_from": [],
                    "linked_to": [],
                    "alarms": [],
                    "logs": [],
                    "cross": 0,
                }
                if d_ip:
                    ip_to_name[d_ip] = d_name

            for link in segment.get("links", []):
                src_ip = link.get("src_ip")
                dst_ip = link.get("dst_ip")
                src_name = ip_to_name.get(src_ip)
                dst_name = ip_to_name.get(dst_ip)
                if src_name and dst_ip and dst_ip not in node_map[src_name]["linked_to"]:
                    node_map[src_name]["linked_to"].append(dst_ip)
                if dst_name and src_ip and src_ip not in node_map[dst_name]["linked_from"]:
                    node_map[dst_name]["linked_from"].append(src_ip)

    # cross
    for c in full_link.get("cross", []):
        try:
            if c.get("device_name") in node_map:
                node_map[c["device_name"]]["cross"] = c.get("cross", 0)
        except (KeyError, TypeError):
            pass

    # alarms
    for alarm in full_link.get("alarm_list", []):
        a_ip = alarm.get("alarm_ip_ad") if isinstance(alarm, dict) else None
        target = ip_to_name.get(a_ip)
        if target:
            node_map[target]["alarms"].append(alarm)

    # logs
    for log in full_link.get("log_list", {}).get("list", []):
        l_ip = log.get("alarm_ip_ad") if isinstance(log, dict) else None
        target = ip_to_name.get(l_ip)
        if target:
            node_map[target]["logs"].append(log)

    return node_map


def _report_stats(cases, passed, rejected, skip_reasons=None):
    """打印过滤统计报告。"""
    wa = [c["n_with_alarms"] for c in cases if c.get("n_with_alarms") is not None]
    print(f"\n  --- 过滤报告 ---")
    if skip_reasons:
        for reason, count in skip_reasons.most_common():
            print(f"  跳过 ({reason}): {count}")
    print(f"  通过: {len(passed)}")
    for reason, lst in rejected.items():
        if lst:
            print(f"  拒绝 ({reason}): {len(lst)}")
    if wa:
        print(f"  有告警设备数: min={min(wa)} median={sorted(wa)[len(wa)//2]} max={max(wa)}")


def phase_extract(raw_dir, out_dir, min_alarm_devices=MIN_DEVICES_WITH_ALARMS, strict=False, write=False):
    """
    Phase 2: 扫描 RAWed 文件, 校验, 提取 info/label/nodes。
    输出到 out_dir (每个 csn 一个子目录)。
    """
    files = [f for f in os.listdir(raw_dir) if f.endswith(".json")]
    print(f"Phase 2 (extract): 扫描 {len(files)} 个 raw 文件")

    cases = []
    skip_reasons = Counter()

    for fname in sorted(files):
        fpath = os.path.join(raw_dir, fname)
        csn = extract_csn(fname) or fname.replace(".json", "")

        try:
            data = json.load(open(fpath, "r", encoding="utf-8"))
        except Exception:
            skip_reasons["JSON 解析失败"] += 1
            continue

        full_link = data.get("full_link", {})
        ok, err, task_info, topo_value, gt_label = _validate_raw(csn, full_link)
        if not ok:
            skip_reasons[err] += 1
            continue

        node_map = _extract_nodes(topo_value, full_link)
        n_with_alarms = sum(1 for nd in node_map.values() if nd["alarms"] or nd["logs"])

        # ── RC 设备名校验 ──
        rc_names = set()
        for an in gt_label.get("abnormal_node", []):
            if isinstance(an, dict) and an.get("name"):
                rc_names.add(an["name"])
            elif isinstance(an, dict) and an.get("mgmt_ip"):
                # 如果只有 IP, 从 node_map 反查 name
                ip = an["mgmt_ip"]
                for nd_name, nd in node_map.items():
                    if nd.get("mgmt_ip") == ip:
                        rc_names.add(nd_name)
                        break

        rc_in_topo = rc_names and all(n in node_map for n in rc_names)
        rc_no_alarms = False
        if rc_in_topo:
            rc_has_alarms = all(
                node_map[n]["alarms"] or node_map[n]["logs"]
                for n in rc_names
            )
            rc_no_alarms = not rc_has_alarms

        if not rc_in_topo:
            skip_reasons["RC 设备不在 topo 中"] += 1
            continue

        if strict and rc_no_alarms:
            skip_reasons["RC 设备无告警 (strict 模式)"] += 1
            continue

        gt_ips = []
        for an in gt_label.get("abnormal_node", []):
            if isinstance(an, dict):
                ip = an.get("ip", an.get("mgmt_ip", ""))
                if ip:
                    gt_ips.append(ip)

        all_ips = set()
        for nd in node_map.values():
            ip = nd.get("mgmt_ip", "")
            if ip:
                all_ips.add(ip)
        gt_in_topo = all(g in all_ips for g in gt_ips) if gt_ips else False

        cases.append({
            "csn": csn, "path": fpath, "data": data,
            "task_info": task_info, "node_map": node_map, "gt_label": gt_label,
            "gt_ips": gt_ips, "gt_in_topo": gt_in_topo,
            "n_with_alarms": n_with_alarms,
            "n_devices": len(node_map),
        })

    # ── 过滤 ──
    passed = []
    rejected = {"告警数不足": [], "gt 不在 topo": [], "两者": []}

    for c in cases:
        low = c["n_with_alarms"] < min_alarm_devices
        no_gt = not c["gt_ips"] or not c["gt_in_topo"]
        if low and no_gt:
            rejected["两者"].append(c)
        elif low:
            rejected["告警数不足"].append(c)
        elif no_gt:
            rejected["gt 不在 topo"].append(c)
        else:
            passed.append(c)

    _report_stats(cases, passed, rejected, skip_reasons)

    if not write:
        print("  >> DRY RUN — 加 --write 执行")
        return
    if not passed:
        print("  >> 无 case 通过过滤, 中止")
        return

    os.makedirs(out_dir, exist_ok=True)
    written = 0
    for c in passed:
        csn = str(c["csn"])
        case_dir = os.path.join(out_dir, csn)
        os.makedirs(case_dir, exist_ok=True)

        task_info = c["task_info"]

        # info.json
        info = {k: task_info.get(k, "") for k in (
            "alarm_name", "alarm_time", "source_ip", "sink_ip",
            "src_tunnel_ip", "dst_tunnel_ip", "scenario_code",
            "analysis_type", "task_num", "alarm_description",
        )}
        info["alarm_time"] = task_info.get("alarm_time")
        json.dump(info, open(os.path.join(case_dir, "info.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

        # label.json
        gt = c["gt_label"]
        labels = [{"ranking": gt.get("ranking", 1), "abnormal_node": gt.get("abnormal_node", [])}]
        json.dump(labels, open(os.path.join(case_dir, "label.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

        # nodes
        out_name = f"pingmesh-{csn}-全链路.json"
        json.dump(c["node_map"], open(os.path.join(case_dir, out_name), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

        written += 1

    print(f"  >> 已写入 {written} 个 case 到 {out_dir}")


# ══════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Preprocessor — RAW→NODE 数据预处理")
    p.add_argument("--raw", "-r", default=None,
                   help="RAW 输入目录 (含原始 JSON)")
    p.add_argument("--out", "-o", default=None,
                   help="NODE 输出目录")
    p.add_argument("--phase", default="all", choices=["merge", "extract", "all"],
                   help="执行阶段: merge(合并) / extract(提取) / all(全流程)")
    p.add_argument("--min-alarm-devices", type=int, default=MIN_DEVICES_WITH_ALARMS,
                   help=f"最少有告警的设备数 (default: {MIN_DEVICES_WITH_ALARMS})")
    p.add_argument("--strict", action="store_true",
                   help="strict 模式: RC 设备无告警则丢弃")
    p.add_argument("--write", action="store_true",
                   help="执行写入 (不加则仅 dry-run)")
    args = p.parse_args()

    # 默认路径 (可从环境变量读取)
    try:
        from Sys.config import config
        _raw = config.data.pingmesh_raw if args.raw is None else args.raw
        _out = config.data.nodes_labeled if args.out is None else args.out
    except Exception:
        _raw = args.raw or "/home/sbp/lixinyang/pingmesh/data/pingmesh_extend"
        _out = args.out or "/home/sbp/lixinyang/pingmesh/data/nodes_extend"

    if args.phase in ("merge", "all"):
        phase_merge(_raw, _out, write=args.write)

    if args.phase in ("extract", "all"):
        if args.phase == "all":
            # Phase 2 读 Phase 1 的输出
            _raw = _out
        phase_extract(_raw, _out, min_alarm_devices=args.min_alarm_devices,
                      strict=args.strict, write=args.write)
