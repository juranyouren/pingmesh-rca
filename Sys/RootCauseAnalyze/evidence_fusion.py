"""
Evidence Fusion Layer
=====================
将三个 Skill（topology_pagerank_rank / temporal_score_devices /
co_occurrence_alarm_check）的输出融合为紧凑的三段文本，消除重复，
彻底解决拼接进 SKILLED_PROMPT 后超长截断的问题。

设计原则：
  - Skill 本身不改（standalone / 消融实验保持完整），压缩只发生在这一层
  - 三个 skill 按 IP 合并成一张「候选设备综合证据表」
  - Top-K 候选的原始告警/日志只输出一次（名称+计数，不 dump 完整 dict）
  - info.json 只取关键字段，不再整体 dump

输出四段，前三段填入 SKILLED_PROMPT 的 {INFO} / {SKILLRET} / {NODES}：
  - info_brief        → 故障概况
  - evidence_str      → 候选设备综合证据表 + 共现告警警告
  - candidate_detail  → Top-K 候选紧凑详情（告警名 + 拓扑连接）
  - candidate_raw     → Top-K 候选完整原始数据（token 充足时由分析器填入 {NODES}，否则退回 candidate_detail）
"""

import os
import json

# ── 融合层常量 ────────────────────────────────────────────────────
CO_OCCUR_MAX_CHARS = 2000        # co_occurrence 警告文本上限
DETAIL_MAX_ALARMS_PER_NODE = 30  # 每个候选节点最多列多少条告警/日志名
RAW_DROP_FIELDS = ("node_sign", "type", "devicetype", "verified_hops_to")  # 原始 dump 时剔除的无用字段
INFO_KEYS = [                    # info.json 只保留这些关键字段
    "alarm_name", "alarm_time", "source_ip", "sink_ip",
    "src_tunnel_ip", "dst_tunnel_ip", "scenario_code",
    "analysis_type", "task_num", "alarm_description",
]


def _get_device_ip(node):
    return node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))


def _load_nodes(dirpath):
    """读 nodes.json，归一化为 list。"""
    path = os.path.join(dirpath, "nodes.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if isinstance(data, dict):
        return list(data.values())
    return data if isinstance(data, list) else []


def _load_info(dirpath):
    path = os.path.join(dirpath, "info.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _safe_json_loads(text):
    """skill 返回值可能是 JSON 串，也可能是错误提示串；解析失败返回 None。"""
    if not isinstance(text, str):
        return text if isinstance(text, dict) else None
    try:
        return json.loads(text)
    except Exception:
        return None


def _extract_alarm_names(node):
    """提取节点的告警/日志名称（去重，保序）。"""
    names = []
    seen = set()
    for evt in node.get("alarms", []) + node.get("logs", []):
        if isinstance(evt, str):
            name = evt.strip()
        elif isinstance(evt, dict):
            name = str(evt.get("alarm_name", evt.get("name", ""))).strip()
        else:
            name = ""
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _build_info_brief(info):
    """从 info.json 只取关键字段，拼成紧凑文本。"""
    if not isinstance(info, dict):
        return "（无故障概况）"
    lines = []
    for k in INFO_KEYS:
        v = info.get(k)
        if v not in (None, "", "[]", "--"):
            lines.append(f"- {k}: {v}")
    return "\n".join(lines) if lines else "（无故障概况）"


def build_fused_evidence(node_list, info, dirpath,
                         skill_map=None, weight_dirpath=None,
                         co_occur_path=None, top_k=10):
    """
    融合三个 skill 的输出。

    Args:
        node_list: 节点列表（已归一化为 list）。为空则自动从 dirpath/nodes.json 读。
        info: info dict。为空则自动从 dirpath/info.json 读。
        dirpath: case 目录（temporal 需要它做时间戳 fallback）。
        skill_map: {executor_name: func}，通常传 SkillExecutor.skill_map。
                   缺省时尝试动态加载 SkillBank/skills。
        weight_dirpath: 告警权重文件路径。
        co_occur_path: 共现规则库路径。
        top_k: 证据表与候选详情保留的候选数。

    Returns:
        (evidence_str, info_brief, candidate_detail, candidate_raw) 四段文本。
        前三段紧凑；candidate_raw 是 Top-K 候选的完整原始数据（较大，供 token 充足时使用）。
    """
    if not node_list:
        node_list = _load_nodes(dirpath)
    if not info:
        info = _load_info(dirpath)
    if skill_map is None:
        skill_map = _lazy_load_skill_map()

    # ── 1. 跑三个 skill ──────────────────────────────────────────
    topo_ranking = _run_topo(skill_map, node_list, info, weight_dirpath)
    temporal_scores = _run_temporal(skill_map, node_list, info, dirpath)
    co_occur_text = _run_co_occur(skill_map, node_list, info, weight_dirpath, co_occur_path)

    # ── 2. 候选 IP 顺序：以 topo 排名为主 ────────────────────────
    if topo_ranking:
        candidate_ips = [r.get("ip") for r in topo_ranking[:top_k] if r.get("ip")]
    else:
        # topo 失败兜底：用节点原始顺序
        candidate_ips = [_get_device_ip(n) for n in node_list][:top_k]

    # ── 3. 告警权重 + 关键告警名（直接从节点扫，比抠字符串稳）──
    weights_dict = _load_alarm_weights(weight_dirpath)
    node_by_ip = {_get_device_ip(n): n for n in node_list}

    # ── 4. 拼证据表 ──────────────────────────────────────────────
    evidence_str = _build_evidence_table(
        candidate_ips, topo_ranking, temporal_scores,
        node_by_ip, weights_dict, co_occur_text)

    # ── 5. info 概况 ─────────────────────────────────────────────
    info_brief = _build_info_brief(info)

    # ── 6. Top-K 候选详情：紧凑版 + 完整原始版 ──────────────────
    candidate_detail = _build_candidate_detail(candidate_ips, node_by_ip)
    candidate_raw = _build_candidate_raw(candidate_ips, node_by_ip)

    return evidence_str, info_brief, candidate_detail, candidate_raw


def _lazy_load_skill_map():
    """缺省路径动态加载 skills，返回 {executor_name: func}。"""
    import importlib.util
    skills_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                              "..", "SkillBank", "skills")
    skills_dir = os.path.normpath(skills_dir)
    skill_map = {}
    if not os.path.isdir(skills_dir):
        return skill_map
    for fn in os.listdir(skills_dir):
        if fn.endswith(".py") and not fn.startswith("__"):
            try:
                spec = importlib.util.spec_from_file_location(fn[:-3], os.path.join(skills_dir, fn))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "EXECUTORS"):
                    skill_map.update(mod.EXECUTORS)
            except Exception:
                pass
    return skill_map


# ── 告警权重加载（与 topo._load_alarm_weights 同逻辑）─────────────
def _load_alarm_weights(weight_dirpath):
    weights = {"stachg_todwn": 100, "trunkdown": 100, "vlan接口down(dcn)": 100}
    if weight_dirpath and os.path.exists(weight_dirpath):
        try:
            with open(weight_dirpath, "r", encoding="utf-8") as f:
                for item in json.load(f):
                    if "alarm_name" in item and "alarm_priority" in item:
                        weights[str(item["alarm_name"]).lower()] = int(item["alarm_priority"])
        except Exception:
            pass
    return weights


def _node_max_weight(node, weights_dict):
    """返回 (最大告警权重, 命中的关键告警名列表)。"""
    max_w = 0
    hit = []
    for name in _extract_alarm_names(node):
        w = weights_dict.get(str(name).lower(), 0)
        if w > 0:
            if w > max_w:
                max_w = w
            hit.append(name)
    return max_w, hit


# ── 三个 skill 的调用封装（解析失败均安全降级）──────────────────
def _run_topo(skill_map, node_list, info, weight_dirpath):
    fn = skill_map.get("topology_pagerank_rank")
    if not fn:
        return []
    try:
        out = fn(node_list, info, weight_dirpath=weight_dirpath) if weight_dirpath \
            else fn(node_list, info)
    except Exception:
        return []
    parsed = _safe_json_loads(out)
    if isinstance(parsed, dict):
        return parsed.get("ranking", []) or []
    return []


def _run_temporal(skill_map, node_list, info, dirpath):
    fn = skill_map.get("temporal_score_devices")
    if not fn:
        return {}
    try:
        out = fn(node_list, info, dirpath=dirpath)
    except Exception:
        return {}
    parsed = _safe_json_loads(out)
    if isinstance(parsed, dict):
        return parsed.get("device_scores", {}) or {}
    return {}


def _run_co_occur(skill_map, node_list, info, weight_dirpath, co_occur_path):
    fn = skill_map.get("co_occurrence_alarm_check")
    if not fn:
        return ""
    try:
        kwargs = {}
        if weight_dirpath:
            kwargs["dirpath"] = weight_dirpath
        if co_occur_path:
            kwargs["co_occur_path"] = co_occur_path
        out = fn(node_list, info, **kwargs)
    except Exception:
        return ""
    if not isinstance(out, str):
        return ""
    # 只保留命中共现规则的警告段（含 🚨 / ⚠️ 标记），否则丢弃（证据表已含权重列）
    if "🚨" in out or "⚠️" in out:
        return out[:CO_OCCUR_MAX_CHARS]
    return ""


# ── 拼证据表 ──────────────────────────────────────────────────────
def _build_evidence_table(candidate_ips, topo_ranking, temporal_scores,
                          node_by_ip, weights_dict, co_occur_text):
    topo_by_ip = {r.get("ip"): r for r in topo_ranking}

    header = "排名 | IP | 角色 | PR分(有向) | PR分(无向) | 时序分 | 告警权重 | Cross | 关键告警"
    sep = "-" * len(header)
    rows = [header, sep]

    for rank, ip in enumerate(candidate_ips, 1):
        tr = topo_by_ip.get(ip, {})
        node = node_by_ip.get(ip, {})
        role = tr.get("role") or node.get("role", "UNKNOWN")
        pr_dir = tr.get("score_directed", tr.get("score", "—"))
        pr_undir = tr.get("score_undirected", "—")
        ts = temporal_scores.get(ip, "—")
        if isinstance(ts, (int, float)):
            ts = round(ts, 3)
        cross = node.get("cross", tr.get("cross", "—"))
        max_w, hit_alarms = _node_max_weight(node, weights_dict)
        w_str = max_w if max_w > 0 else "—"
        alarm_str = ", ".join(hit_alarms[:3]) if hit_alarms else "—"
        rows.append(f"{rank} | {ip} | {role} | {pr_dir} | {pr_undir} | {ts} | {w_str} | {cross} | {alarm_str}")

    table = "\n".join(rows)

    if co_occur_text:
        table += "\n\n【高危告警组合警告（历史错案反思生成）】\n" + co_occur_text

    return table


# ── Top-K 候选原始详情 ────────────────────────────────────────────
def _build_candidate_detail(candidate_ips, node_by_ip):
    """紧凑版：告警/日志名 + 拓扑连接（linked_from/linked_to）。"""
    blocks = []
    for ip in candidate_ips:
        node = node_by_ip.get(ip)
        if not node:
            continue
        names = _extract_alarm_names(node)
        if not names:
            detail = "（无告警/日志）"
        else:
            shown = names[:DETAIL_MAX_ALARMS_PER_NODE]
            detail = "; ".join(shown)
            if len(names) > DETAIL_MAX_ALARMS_PER_NODE:
                detail += f" ...（共 {len(names)} 条，已截断）"
        # 拓扑连接对根因推理至关重要，紧凑版也带上
        lf = node.get("linked_from", [])
        lt = node.get("linked_to", [])
        topo = ""
        if lf or lt:
            topo = f" | 上游={lf} 下游={lt}"
        blocks.append(f"[{ip}] (role={node.get('role', 'UNKNOWN')}, cross={node.get('cross', 0)}): 告警=[{detail}]{topo}")
    return "\n".join(blocks) if blocks else "（无候选设备详情）"


def _build_candidate_raw(candidate_ips, node_by_ip):
    """完整版：Top-K 候选节点的完整原始 dict（剔除无用字段），供 token 充足时填入 prompt。"""
    raw = {}
    for ip in candidate_ips:
        node = node_by_ip.get(ip)
        if not node:
            continue
        raw[ip] = {k: v for k, v in node.items() if k not in RAW_DROP_FIELDS}
    if not raw:
        return "（无候选设备详情）"
    return json.dumps(raw, ensure_ascii=False, indent=2)


