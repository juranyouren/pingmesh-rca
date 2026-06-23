"""
nodes 数据集预处理
==================
1. 扫描 data/nodes, 识别文件名中的 csn
2. 相同 csn 的多个文件合并为一个 case (互补缺失键)
3. 合并后写入 data/nodes_extend

用法:
  python tmp/preprocess_nodes.py [--write]
"""

import os, json, sys, shutil
from collections import defaultdict, Counter

SRC = sys.argv[1] if len(sys.argv) > 1 else "/home/sbp/lixinyang/pingmesh/data/nodes"
DST = "/home/sbp/lixinyang/pingmesh/data/nodes_extend"
WRITE = "--write" in sys.argv

# ══════════════════════════════════════════════════════════════════
# 1. 扫描 + 按 csn 分组
# ══════════════════════════════════════════════════════════════════

print("=" * 60)
print(f"扫描: {SRC}")
print("=" * 60)

groups = defaultdict(list)  # csn → [filepath, ...]
skipped = []
unmatched = []

for fname in sorted(os.listdir(SRC)):
    if not fname.endswith(".json"):
        continue

    fpath = os.path.join(SRC, fname)

    # 文件名格式: pingmesh-{csn}-xxx.json 或 merged_pingmesh-{csn}-xxx.json
    name_no_ext = fname.replace(".json", "")
    parts = name_no_ext.split("-")

    # pingmesh-756668925-全链路.json → parts = ["pingmesh", "756668925", "全链路"]
    # merged_pingmesh-756668925-全链路.json → parts = ["merged", "pingmesh", "756668925", "全链路"]
    if "merged" in parts and "pingmesh" in parts:
        # merged_pingmesh-xxx-...
        idx = parts.index("pingmesh")
        csn = parts[idx + 1] if idx + 1 < len(parts) else None
    elif "pingmesh" in parts:
        # pingmesh-xxx-...
        idx = parts.index("pingmesh")
        csn = parts[idx + 1] if idx + 1 < len(parts) else None
    else:
        unmatched.append(fname)
        continue

    if not csn:
        unmatched.append(fname)
        continue

    groups[csn].append(fpath)

print(f"  文件总数: {len(os.listdir(SRC))}")
print(f"  有效 CSN: {len(groups)}")
print(f"  无法解析: {len(unmatched)}")
if unmatched[:5]:
    print(f"    示例: {unmatched[:5]}")

# ══════════════════════════════════════════════════════════════════
# 2. 统计分组情况
# ══════════════════════════════════════════════════════════════════

singles = sum(1 for v in groups.values() if len(v) == 1)
multiples = sum(1 for v in groups.values() if len(v) > 1)
multi_dist = Counter()
for v in groups.values():
    if len(v) > 1:
        multi_dist[len(v)] += 1

print(f"\n  单一文件 case: {singles}")
print(f"  多文件 case: {multiples}")
for k in sorted(multi_dist):
    print(f"    {k} 个文件: {multi_dist[k]} 组")

# ══════════════════════════════════════════════════════════════════
# 3. 合并逻辑 — 相同 csn 的文件互补缺失键
# ══════════════════════════════════════════════════════════════════

def deep_merge(base, other):
    """递归合并两个 dict, other 中的键补充 base 中缺失的键。已有键不覆盖。"""
    if not isinstance(base, dict) or not isinstance(other, dict):
        return base
    for key, val in other.items():
        if key not in base or base[key] is None or base[key] == {} or base[key] == []:
            base[key] = val
        elif isinstance(base[key], dict) and isinstance(val, dict):
            deep_merge(base[key], val)
        elif isinstance(base[key], list) and isinstance(val, list) and not base[key]:
            base[key] = val
    return base


merged_ok = 0
merge_fail = 0

# ══════════════════════════════════════════════════════════════════
# 4. 输出
# ══════════════════════════════════════════════════════════════════

if WRITE:
    if os.path.exists(DST):
        shutil.rmtree(DST)
    os.makedirs(DST, exist_ok=True)

    for csn, files in sorted(groups.items()):
        case_dir = os.path.join(DST, csn)
        os.makedirs(case_dir, exist_ok=True)

        # 合并所有文件
        merged = None
        for fp in files:
            try:
                data = json.load(open(fp, "r", encoding="utf-8"))
            except Exception:
                merge_fail += 1
                continue

            if merged is None:
                merged = data
            else:
                merged = deep_merge(merged, data)

        if merged is None:
            merge_fail += 1
            continue

        merged_ok += 1

        # 输出合并后的文件
        out_name = f"pingmesh-{csn}-全链路.json"
        json.dump(merged, open(os.path.join(case_dir, out_name), "w", encoding="utf-8"),
                  ensure_ascii=False)

        # ⚠️ 这个阶段只做合并, 不做 Collector 式的 info.json/label.json 提取
        # 后续用 perceive_and_filter.py 再做过滤 + Collector 转换

    print(f"\n写入完成: {merged_ok} case → {DST}")
    print(f"合并失败: {merge_fail}")

    # 快速统计
    total_size = sum(
        os.path.getsize(os.path.join(DST, csn, f"pingmesh-{csn}-全链路.json"))
        for csn in sorted(groups.keys())
        if os.path.exists(os.path.join(DST, csn, f"pingmesh-{csn}-全链路.json"))
    )
    print(f"总大小: {total_size / 1024 / 1024:.1f} MB")
else:
    print(f"\n>> DRY RUN — 将合并 {singles + multiples} 个 case")
    if multiples:
        print(f">> 其中 {multiples} 个 case 由多个文件合并")
    print(f">> 加 --write 执行写入")
