"""
比较同 case 的 skill_ips 在两条路径下是否一致:
  Path A: skill_pipeline.rank_devices_by_skills (消融用)
  Path B: evidence_fusion.build_fused_evidence (LLM推理用)

跑 3 个 case，逐 IP 对比得分。
"""

import json, os, sys
sys.path.insert(0, "/home/sbp/lixinyang/pingmesh")

from Sys.RootCauseAnalyze.skill_pipeline import (
    rank_devices_by_skills, _score_topo, _score_temporal
)
from Sys.RootCauseAnalyze.evidence_fusion import build_fused_evidence

data_root = "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"
wpath = "/home/sbp/lixinyang/pingmesh/data/weights/classified_alarms/all_alarms.json"

cases = []
for dirpath, _, filenames in os.walk(data_root):
    node_file = None
    for fn in filenames:
        if "全链路.json" in fn and "pingmesh" in fn:
            node_file = fn; break
    if not node_file: continue
    cases.append(dirpath)
    if len(cases) >= 3: break

for dirpath in cases:
    print(f"\n{'='*60}")
    print(f"CASE: {os.path.basename(dirpath)}")

    # Load data
    raw = json.load(open(os.path.join(dirpath,
        [f for f in os.listdir(dirpath) if "全链路.json" in f and "pingmesh" in f][0]),
        "r", encoding="utf-8"))
    nodes = list(raw.values()) if isinstance(raw, dict) else raw
    info_path = os.path.join(dirpath, "info.json")
    info = json.load(open(info_path, "r", encoding="utf-8")) if os.path.exists(info_path) else {}

    # --- Path A: skill_pipeline ---
    print("\n--- Path A: skill_pipeline.rank_devices_by_skills [1,2] ---")
    ips_a, details_a = rank_devices_by_skills(
        nodes, info, dirpath, skill_ids=[1,2], directed=True,
        weight_dirpath=wpath)
    print(f"Top-5: {ips_a[:5] if ips_a else 'EMPTY'}")

    # Individual scores (normalized)
    scores_pr_a = _score_topo(nodes, info, weight_dirpath=wpath, directed=True)
    scores_ts_a = _score_temporal(nodes, info, dirpath=dirpath)
    for ip in ips_a[:3]:
        pr = scores_pr_a.get(ip, -1)
        ts = scores_ts_a.get(ip, -1)
        print(f"  {ip}: PR={pr:.4f} TS={ts:.4f}")

    # --- Path B: evidence_fusion ---
    print("\n--- Path B: evidence_fusion.build_fused_evidence ---")
    sr, ib, det, raw_b, ips_b = build_fused_evidence(
        nodes, info, dirpath, weight_dirpath=wpath, top_k=5)
    print(f"Top-5: {ips_b[:5] if ips_b else 'EMPTY'}")

    # The fusion also calls _score_topo / _score_temporal internally
    # Let's verify the per-IP combined scores
    try:
        sr_j = json.loads(sr)
        for r in sr_j.get("combined_score_rankings", [])[:3]:
            ip = r["ip"]
            pr = scores_pr_a.get(ip, -1)
            ts = scores_ts_a.get(ip, -1)
            combined = (pr + ts) / 2 * 100
            print(f"  {ip}: combined={r['combined_score']} (expect {(pr+ts)/2*100:.1f})")
    except Exception as e:
        print(f"  Parse error: {e}")

    # --- Compare ---
    match = ips_a[:5] == ips_b[:5]
    print(f"\n>>> Top-5 MATCH: {match}")
    if not match:
        print(f"  Path A: {ips_a[:5]}")
        print(f"  Path B: {ips_b[:5]}")
        # 找出差异
        set_a = set(ips_a[:5])
        set_b = set(ips_b[:5])
        print(f"  Only in A: {set_a - set_b}")
        print(f"  Only in B: {set_b - set_a}")

    # Check gt from label.json
    label_path = os.path.join(dirpath, "label.json")
    if os.path.exists(label_path):
        labels = json.load(open(label_path, "r", encoding="utf-8"))
        if isinstance(labels, list):
            gts = []
            for lb in sorted(labels, key=lambda x: x.get("ranking", 999))[:3]:
                for an in lb.get("abnormal_node", []):
                    if an.get("ip") and an["ip"] not in gts:
                        gts.append(an["ip"])
            if gts:
                hit_a = sum(1 for g in gts if g in ips_a[:1])
                hit_b = sum(1 for g in gts if g in ips_b[:1])
                print(f"  GT={gts}")
                print(f"  Top-1 hit: A={hit_a} B={hit_b}")
