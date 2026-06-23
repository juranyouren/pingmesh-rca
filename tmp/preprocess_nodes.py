"""
pingmesh_extend 数据预处理
==========================
1. 扫描 data/pingmesh_extend, 识别文件名中的 csn
2. 相同 csn 的多个文件 → 合并 (互补缺失键)
3. 合并后输出到 data/nodes_extend (合并后的原始 JSON, 不做 Collector 转换)

用法:
  python tmp/preprocess_nodes.py [--write]
"""

import os, json, sys, shutil
from collections import defaultdict, Counter

SRC = "/home/sbp/lixinyang/pingmesh/data/pingmesh_extend"
DST = "/home/sbp/lixinyang/pingmesh/data/nodes_extend"
WRITE = "--write" in sys.argv


def extract_csn(fname):
    """
    pingmesh-756668925-xxx.json         → 756668925
    merged_pingmesh-756668925-xxx.json  → 756668925
    """
    name = fname.replace(".json", "")
    parts = name.split("-")

    if "merged" in parts and "pingmesh" in parts:
        idx = parts.index("pingmesh")
    elif "pingmesh" in parts:
        idx = parts.index("pingmesh")
    else:
        return None

    return parts[idx + 1] if idx + 1 < len(parts) else None


def deep_merge(base, other):
    """
    递归合并, other 中的键补充 base 中缺失的键。已有键不覆盖。
    """
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


# ══════════════════════════════════════════════════════════════════

print("=" * 60)
print(f"扫描: {SRC}")
print("=" * 60)

files = [f for f in os.listdir(SRC) if f.endswith(".json")]
print(f"JSON 文件数: {len(files)}")

groups = defaultdict(list)
unmatched = []

for fname in sorted(files):
    csn = extract_csn(fname)
    if csn:
        groups[csn].append(os.path.join(SRC, fname))
    else:
        unmatched.append(fname)

print(f"有效 CSN: {len(groups)}")
print(f"无法解析 CSN: {len(unmatched)}")
if unmatched:
    for u in unmatched[:10]:
        print(f"  - {u}")

# 分组统计
singles = sum(1 for v in groups.values() if len(v) == 1)
multi = sum(1 for v in groups.values() if len(v) > 1)
print(f"\n单文件 case: {singles}")
print(f"多文件 case: {multi}")
for k in sorted(set(len(v) for v in groups.values() if len(v) > 1)):
    print(f"  {k} 文件合并: {sum(1 for v in groups.values() if len(v) == k)} 组")

# ══════════════════════════════════════════════════════════════════

if WRITE:
    if os.path.exists(DST):
        shutil.rmtree(DST)
    os.makedirs(DST, exist_ok=True)

    ok = fail = 0
    for csn, fpaths in sorted(groups.items()):
        merged = None
        for fp in fpaths:
            try:
                data = json.load(open(fp, "r", encoding="utf-8"))
            except Exception:
                fail += 1
                merged = None
                break
            merged = deep_merge(merged, data) if merged is not None else data

        if merged is None:
            continue

        case_dir = os.path.join(DST, csn)
        os.makedirs(case_dir, exist_ok=True)
        out_name = f"pingmesh-{csn}-全链路.json"
        json.dump(merged, open(os.path.join(case_dir, out_name), "w", encoding="utf-8"),
                  ensure_ascii=False)
        ok += 1

    print(f"\n写入: {ok} case → {DST}  失败: {fail}")
else:
    print(f"\n>> DRY RUN — 加 --write 执行合并写入")
    print(f">> 将输出 {singles + multi} 个 case 到 {DST}")
