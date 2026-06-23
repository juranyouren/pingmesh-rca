"""
NIKA 数据感知脚本 — 了解 NIKA 数据格式以便适配

用法：
  python tmp/perceive_nika.py /path/to/nika/data
"""

import os, json, sys
from collections import Counter

data_root = sys.argv[1] if len(sys.argv) > 1 else "data/nika"

print("=" * 60)
print(f"NIKA 数据感知: {data_root}")
print("=" * 60)

# ── 1. 顶层结构 ──
print("\n--- 顶层文件/目录结构 ---")
top_items = os.listdir(data_root)[:20]
for item in sorted(top_items):
    full = os.path.join(data_root, item)
    tag = "DIR" if os.path.isdir(full) else "FILE"
    print(f"  [{tag}] {item}")
if len(os.listdir(data_root)) > 20:
    print(f"  ... 还有 {len(os.listdir(data_root)) - 20} 项")

# ── 2. 抽样一个文件/case 看结构 ──
print("\n--- 抽样一个 case 的结构 ---")
sample = None
for item in sorted(os.listdir(data_root)):
    full = os.path.join(data_root, item)
    if os.path.isdir(full):
        # 进子目录
        subs = os.listdir(full)
        print(f"\n  [{item}/] 包含: {subs[:10]}")
        # 找 JSON
        for sf in subs:
            if sf.endswith(".json"):
                sample = os.path.join(full, sf)
                break
        if not sample:
            # 找任何文件
            for sf in subs:
                sfp = os.path.join(full, sf)
                if os.path.isfile(sfp):
                    sample = sfp
                    break
    elif item.endswith(".json"):
        sample = full

    if sample:
        break

if sample:
    print(f"\n  抽样文件: {sample}")
    try:
        data = json.load(open(sample, "r", encoding="utf-8"))
        print(f"  顶层 key: {list(data.keys())}")

        # 递归展示结构
        def show_structure(obj, depth=1, max_depth=3):
            if depth > max_depth:
                return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    vtype = type(v).__name__
                    vdesc = ""
                    if isinstance(v, list):
                        vdesc = f"list[{len(v)}]"
                        if v and isinstance(v[0], dict):
                            vdesc += f" keys={list(v[0].keys())[:8]}"
                    elif isinstance(v, dict):
                        vdesc = f"dict keys={list(v.keys())[:8]}"
                    elif isinstance(v, str):
                        vdesc = f'"{v[:80]}..."' if len(v) > 80 else f'"{v}"'
                    elif isinstance(v, (int, float)):
                        vdesc = str(v)
                    print(f"  {'  ' * depth}{k}: {vtype} {vdesc}")
                    if depth < max_depth and isinstance(v, (dict, list)):
                        items = v if isinstance(v, list) else [v]
                        if items:
                            show_structure(items[0], depth + 1, max_depth)
            elif isinstance(obj, list) and obj:
                print(f"  {'  ' * depth}[0]: {type(obj[0]).__name__}")
                show_structure(obj[0], depth + 1, max_depth)

        show_structure(data)

        # 统计 case 数
        print(f"\n  抽样数据概览: ")
        for k, v in data.items():
            if isinstance(v, list):
                print(f"    {k}: {len(v)} items")
            elif isinstance(v, dict):
                print(f"    {k}: {len(v)} keys")
    except Exception as e:
        print(f"  解析失败: {e}")

# ── 3. 扫描所有 case ──
print("\n--- 扫描全部 case ---")
case_count = 0
has_gt = 0
has_topo = 0
has_events = 0
topology_sizes = []

for dirpath, dirnames, filenames in os.walk(data_root, topdown=True):
    # 限制深度
    depth = dirpath.replace(data_root, "").count(os.sep)
    if depth > 3:
        continue

    json_files = [f for f in filenames if f.endswith(".json")]
    if not json_files and not dirnames:
        continue

    # 尝试解析
    for fn in json_files:
        try:
            fp = os.path.join(dirpath, fn)
            d = json.load(open(fp, "r", encoding="utf-8"))
            case_count += 1

            # 检测是否有 gt
            for gt_key in ["root_cause", "ground_truth", "fault_node", "rootcause", "label"]:
                if gt_key in d or any(gt_key in str(k).lower() for k in (d.keys() if isinstance(d, dict) else [])):
                    has_gt += 1
                    break

            # 检测是否有拓扑
            for topo_key in ["topology", "topo", "graph", "network", "nodes"]:
                if any(topo_key in str(k).lower() for k in (d.keys() if isinstance(d, dict) else [])):
                    v = d.get(topo_key, d.get([k for k in d.keys() if topo_key in str(k).lower()][0] if isinstance(d, dict) and any(topo_key in str(k).lower() for k in d.keys()) else None, None))
                    if isinstance(v, (list, dict)):
                        has_topo += 1
                        if isinstance(v, list):
                            topology_sizes.append(len(v))
                        elif isinstance(v, dict):
                            # 可能是 {node_id: node} 或 {nodes: [...], edges: [...]}
                            if "nodes" in v or "edges" in v:
                                topology_sizes.append(len(v.get("nodes", v.get("edges", []))))
                            else:
                                topology_sizes.append(len(v))
                    break

            # 检测是否有告警/事件
            for evt_key in ["events", "alarms", "logs", "telemetry", "alerts", "traces"]:
                if any(evt_key in str(k).lower() for k in (d.keys() if isinstance(d, dict) else [])):
                    has_events += 1
                    break

            if case_count <= 3:
                print(f"  [{case_count}] {os.path.relpath(fp, data_root)}: keys={list(d.keys())[:10]}")
            break  # 每个目录只取第一个 JSON
        except Exception:
            pass

    if case_count >= 50:
        break

print(f"\n  扫描 {case_count} 个 case:")
print(f"    有 gt 标注: {has_gt}")
print(f"    有拓扑数据: {has_topo}")
print(f"    有告警/事件: {has_events}")
if topology_sizes:
    print(f"    拓扑规模: min={min(topology_sizes)} median={sorted(topology_sizes)[len(topology_sizes)//2]} max={max(topology_sizes)}")
print()
print("=" * 60)
print("请将以上输出反馈给我, 我将据此编写适配脚本")
print("=" * 60)
