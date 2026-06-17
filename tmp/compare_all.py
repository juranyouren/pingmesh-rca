"""
全量对比 skill_pipeline vs evidence_fusion 的 skill_ips，
统计差异并输出不一致的 case。
"""

import json, os, sys
sys.path.insert(0, "/home/sbp/lixinyang/pingmesh")

from Sys.RootCauseAnalyze.skill_pipeline import rank_devices_by_skills
from Sys.RootCauseAnalyze.evidence_fusion import build_fused_evidence

data_root = sys.argv[1] if len(sys.argv) > 1 else "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"
wpath = "/home/sbp/lixinyang/pingmesh/data/weights/classified_alarms/all_alarms.json"

match_top1 = 0
match_top5 = 0
total = 0
mismatch_cases = []

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

    # Path A
    ips_a, _ = rank_devices_by_skills(nodes, info, dirpath, skill_ids=[1,2], directed=True, weight_dirpath=wpath)

    # Path B
    _, _, _, _, ips_b = build_fused_evidence(nodes, info, dirpath, weight_dirpath=wpath, top_k=5)

    total += 1
    if ips_a and ips_b:
        if ips_a[0] == ips_b[0]:
            match_top1 += 1
        if ips_a[:5] == ips_b[:5]:
            match_top5 += 1
        if ips_a[:5] != ips_b[:5]:
            mismatch_cases.append({
                "dir": dirpath,
                "a": ips_a[:5],
                "b": ips_b[:5] if ips_b else [],
            })

print(f"Total cases: {total}")
print(f"Top-1 match: {match_top1}/{total} = {match_top1/max(1,total)*100:.1f}%")
print(f"Top-5 match: {match_top5}/{total} = {match_top5/max(1,total)*100:.1f}%")
print(f"Mismatch cases: {len(mismatch_cases)}")

if mismatch_cases:
    print("\n--- First 10 mismatches ---")
    for mc in mismatch_cases[:10]:
        print(f"  {os.path.basename(mc['dir'])}")
        print(f"    A: {mc['a']}")
        print(f"    B: {mc['b']}")
