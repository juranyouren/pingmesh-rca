"""
Evidence Fusion Layer
=====================
将两个 Skill（topology_pagerank_rank / temporal_score_devices）的输出融合为结构化 JSON，
三个独立字典块注入 SKILLED_PROMPT，便于 LLM 解析。

输出三段（填入 {INFO} / {SKILLRET} / {NODES}）：
  - info_brief        → 故障概况
  - skill_ret         → JSON: {"topo": {...}, "temporal": {...}}  算法分析
  - candidate_detail  → JSON: {"devices": [{ip, role, cross, alarms, topology}]}  候选详情
"""

import os
import json

DETAIL_MAX_ALARMS_PER_NODE = 30
RAW_DROP_FIELDS = ("node_sign", "type", "devicetype", "verified_hops_to")
INFO_KEYS = [
    "alarm_name", "alarm_time", "source_ip", "sink_ip",
    "src_tunnel_ip", "dst_tunnel_ip", "scenario_code",
    "analysis_type", "task_num", "alarm_description",
]

TOPO_DESC = (
    "Personalized PageRank (directed) on physical topology graph. "
    "Initial weight = max alarm weight hits + cross_count * multiplier + source/sink proximity bonus. "
    "Higher score = device at topology bottleneck traversed by multiple anomaly paths."
)

TEMPORAL_DESC = (
    "Temporal suspicion score (0-1): "
    "Burst (0.40): alarms within +/-5min of fault time; "
    "Early Bird (0.35): 1/rank of device first alarm; "
    "Temporal Density (0.25): alarms/min capped at 20. "
    "Higher = alarms earlier, more concentrated = likely root cause."
)

def _get_device_ip(node):
    return node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))


def _load_nodes(dirpath):
    path = os.path.join(dirpath, "nodes.json")
    if not os.path.exists(path): return []
    try:
        data = json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        return []
    return list(data.values()) if isinstance(data, dict) else (data if isinstance(data, list) else [])


def _load_info(dirpath):
    path = os.path.join(dirpath, "info.json")
    if not os.path.exists(path): return {}
    try: return json.load(open(path, "r", encoding="utf-8"))
    except Exception: return {}


def _extract_alarm_names(node):
    names, seen = [], set()
    for evt in node.get("alarms", []) + node.get("logs", []):
        name = evt.strip() if isinstance(evt, str) else str(evt.get("alarm_name", evt.get("name", ""))).strip()
        if name and name not in seen:
            seen.add(name); names.append(name)
    return names


def _build_info_brief(info):
    if not isinstance(info, dict): return "（无故障概况）"
    lines = [f"- {k}: {v}" for k in INFO_KEYS if (v := info.get(k)) not in (None, "", "[]", "--")]
    return "\n".join(lines) if lines else "（无故障概况）"


def _load_alarm_weights(weight_dirpath):
    weights = {"stachg_todwn": 100, "trunkdown": 100, "vlan接口down(dcn)": 100}
    if weight_dirpath and os.path.exists(weight_dirpath):
        try:
            for item in json.load(open(weight_dirpath, "r", encoding="utf-8")):
                if "alarm_name" in item and "alarm_priority" in item:
                    weights[str(item["alarm_name"]).lower()] = int(item["alarm_priority"])
        except Exception: pass
    return weights


def _node_max_weight(node, weights_dict):
    max_w, hit = 0, []
    for name in _extract_alarm_names(node):
        if (w := weights_dict.get(str(name).lower(), 0)) > 0:
            if w > max_w: max_w = w
            hit.append(name)
    return max_w, hit


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

def build_fused_evidence(node_list, info, dirpath,
                         skill_map=None, weight_dirpath=None, top_k=10,
                         alarm_taxonomy=None):
    """
    Returns: (skill_ret, info_brief, candidate_detail, candidate_raw, skill_ips)
    alarm_taxonomy: 告警分类字典 {name: {type, severity}}, None 时原方案不变
    """
    if not node_list: node_list = _load_nodes(dirpath)
    if not info: info = _load_info(dirpath)
    if skill_map is None: skill_map = _lazy_load_skill_map()

    # ── 1. 核心评分（与 skill_pipeline 一致）──
    from Sys.RootCauseAnalyze.skill_pipeline import _score_topo, _score_temporal
    norm_pr = _score_topo(node_list, info, weight_dirpath=weight_dirpath, directed=True,
                          alarm_taxonomy=alarm_taxonomy)
    norm_ts = _score_temporal(node_list, info, dirpath=dirpath,
                              alarm_taxonomy=alarm_taxonomy)

    # ── 2. 综合分 & 排序 ──
    all_ips = list({_get_device_ip(n) for n in node_list if _get_device_ip(n) != "unknown"})
    combined = {ip: (norm_pr.get(ip, 0) + norm_ts.get(ip, 0)) / 2.0 for ip in all_ips}
    candidate_ips = sorted(combined, key=combined.get, reverse=True)[:top_k]

    # ── 3. 告警权重 & node lookup ──
    weights_dict = _load_alarm_weights(weight_dirpath)
    node_by_ip = {_get_device_ip(n): n for n in node_list}

    # ── 4. Topo 结构化字典 ──
    topo_ranking = _run_topo(skill_map, node_list, info, weight_dirpath)
    topo_by_ip = {r.get("ip"): r for r in topo_ranking}
    topo_list = []
    for rank, ip in enumerate(candidate_ips, 1):
        tr = topo_by_ip.get(ip, {})
        node = node_by_ip.get(ip, {})
        topo_list.append({
            "rank": rank,
            "ip": ip,
            "role": tr.get("role") or node.get("role", "UNKNOWN"),
            "pr_score": round(norm_pr.get(ip, 0) * 100, 1),
            "cross": node.get("cross", tr.get("cross", 0)),
        })

    # ── 5. Temporal 结构化字典 ──
    from Sys.RootCauseAnalyze.skill_pipeline import _score_temporal as _ts
    temporal_list = []
    for rank, ip in enumerate(candidate_ips, 1):
        node = node_by_ip.get(ip, {})
        raw_vals = _compute_temporal_raw(node)
        temporal_list.append({
            "rank": rank,
            "ip": ip,
            "score": round(norm_ts.get(ip, 0) * 100, 1),
        } | raw_vals)

    # ── 6. 组装 skill_ret JSON ──
    skill_ret = json.dumps({
        "topo": {"description": TOPO_DESC, "rankings": topo_list},
        "temporal": {"description": TEMPORAL_DESC, "rankings": temporal_list},
        "combined_score_rankings": [{
            "rank": i + 1,
            "ip": ip,
            "combined_score": round(combined[ip] * 100, 1),
            "role": (topo_by_ip.get(ip, {}) or {}).get("role") or node_by_ip.get(ip, {}).get("role", "UNKNOWN"),
        } for i, ip in enumerate(candidate_ips)],
    }, ensure_ascii=False, indent=2)

    # ── 7. info 概况 ──
    info_brief = _build_info_brief(info)

    # ── 8. 候选设备详情 JSON ──
    devices_detail = []
    for ip in candidate_ips:
        node = node_by_ip.get(ip)
        if not node: continue
        names = _extract_alarm_names(node)
        max_w, high_alarms = _node_max_weight(node, weights_dict)
        devices_detail.append({
            "ip": ip,
            "role": node.get("role", "UNKNOWN"),
            "cross": node.get("cross", 0),
            "alarm_count": len(names),
            "alarms": names[:DETAIL_MAX_ALARMS_PER_NODE],
            "high_severity_alarms": high_alarms[:10],
            "topology": {
                "upstream": node.get("linked_from", [])[:10],
                "downstream": node.get("linked_to", [])[:10],
            },
        })
    candidate_detail = json.dumps({"devices": devices_detail}, ensure_ascii=False, indent=2)

    # ── 9. raw 版本（token 充足时备用）──
    candidate_raw = _build_candidate_raw(candidate_ips, node_by_ip)

    return skill_ret, info_brief, candidate_detail, candidate_raw, candidate_ips


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def _compute_temporal_raw(node):
    """简单统计: 设备上的告警/日志数量。"""
    alarms = node.get("alarms", []) if isinstance(node, dict) else []
    logs = node.get("logs", []) if isinstance(node, dict) else []
    return {"total_alarms": len(alarms), "total_logs": len(logs)}


def _lazy_load_skill_map():
    import importlib.util
    skills_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "SkillBank", "skills"))
    skill_map = {}
    if not os.path.isdir(skills_dir): return skill_map
    for fn in os.listdir(skills_dir):
        if fn.endswith(".py") and not fn.startswith("__"):
            try:
                spec = importlib.util.spec_from_file_location(fn[:-3], os.path.join(skills_dir, fn))
                mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
                if hasattr(mod, "EXECUTORS"): skill_map.update(mod.EXECUTORS)
            except Exception: pass
    return skill_map


def _run_topo(skill_map, node_list, info, weight_dirpath):
    fn = skill_map.get("topology_pagerank_rank")
    if not fn: return []
    try:
        out = fn(node_list, info, weight_dirpath=weight_dirpath) if weight_dirpath else fn(node_list, info)
    except Exception: return []
    if isinstance(out, dict): return out.get("ranking", out.get("ip", [])) or []
    try:
        parsed = json.loads(out)
        return parsed.get("ranking", parsed.get("ip", [])) if isinstance(parsed, dict) else []
    except Exception: return []


def _build_candidate_raw(candidate_ips, node_by_ip):
    raw = {ip: {k: v for k, v in node_by_ip.get(ip, {}).items() if k not in RAW_DROP_FIELDS}
           for ip in candidate_ips if ip in node_by_ip}
    return json.dumps(raw, ensure_ascii=False, indent=2) if raw else "{}"
