"""
Skill Pipeline — 纯算法评分流水线（不依赖 LLM / NPU）
======================================================
对每个 case 运行指定的 Skill，融合得分后输出 Top-K 排名，
结果格式与 LLM 推理完全兼容，可直接用 Scorer 评测。

组合策略：每种 Skill 的得分归一化到 [0,1]，等权平均后排序。

用法：
  python Sys/RootCauseAnalyze/skill_pipeline.py \
    -d /path/to/data -s 1 -o pr_only --directed

  # 测试不同 skill 组合的召回率
  python Sys/RootCauseAnalyze/skill_pipeline.py -s 1 3 -o topo_temporal
"""

import os
import json
import time
import importlib.util


# ══════════════════════════════════════════════════════════════════════
# Skill loading (shared with evidence_fusion — same lazy loader)
# ══════════════════════════════════════════════════════════════════════

def _load_skills(skills_dir=None):
    """Load SkillBank executors, return {executor_name: func}."""
    if skills_dir is None:
        skills_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "SkillBank", "skills")
    skills_dir = os.path.normpath(skills_dir)
    skill_map = {}
    if not os.path.isdir(skills_dir):
        return skill_map
    for fn in sorted(os.listdir(skills_dir)):
        if fn.endswith(".py") and not fn.startswith("__"):
            try:
                spec = importlib.util.spec_from_file_location(
                    fn[:-3], os.path.join(skills_dir, fn))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "EXECUTORS"):
                    skill_map.update(mod.EXECUTORS)
            except Exception:
                pass
    return skill_map


# ══════════════════════════════════════════════════════════════════════
# Per-skill scorers: return {device_ip: normalized_score [0,1]}
# ══════════════════════════════════════════════════════════════════════

def _get_device_ip(node):
    return node.get("mgmt_ip", node.get("ip", node.get("name", "unknown")))


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


def _parse_endpoint_ips(infodta):
    source_ips, sink_ips = [], []
    if infodta and isinstance(infodta, dict):
        try:
            src_val = infodta.get("source_ip", "[]")
            snk_val = infodta.get("sink_ip", "[]")
            source_ips = json.loads(src_val) if isinstance(src_val, str) else src_val
            sink_ips = json.loads(snk_val) if isinstance(snk_val, str) else snk_val
            if not isinstance(source_ips, list): source_ips = []
            if not isinstance(sink_ips, list): sink_ips = []
        except Exception:
            pass
    return source_ips, sink_ips


def _safe_json_loads(text):
    if isinstance(text, dict):
        return text
    try:
        return json.loads(text) if isinstance(text, str) else None
    except Exception:
        return None


# ── Skill 1: topology_pagerank_rank ─────────────────────────────

try:
    import networkx as nx
except ImportError:
    nx = None

try:
    from Sys.config import config as _cfg
    _DEFAULT_PAGERANK_ALPHA = _cfg.pagerank.alpha
except Exception:
    _DEFAULT_PAGERANK_ALPHA = 0.85


def _score_topo(node_list, infodta, weight_dirpath=None, directed=True,
                alarm_taxonomy=None, case_dir=""):
    """
    PageRank scoring. If alarm_taxonomy is provided, causal alarms get full weight,
    symptom alarms get reduced weight (0.3x), noise alarms get near-zero (0.05x).
    If case_dir has alarm_taxonomy.json, it is auto-loaded when no taxonomy is provided.
    """
    if nx is None:
        return {}

    # 若无显式 taxonomy, 尝试从 case 目录自动加载 per-case 分类
    tax = alarm_taxonomy
    if tax is None and case_dir:
        tax_path = os.path.join(case_dir, "alarm_taxonomy.json")
        if os.path.exists(tax_path):
            try: tax = json.load(open(tax_path, encoding="utf-8"))
            except Exception: pass

    weights_dict = _load_alarm_weights(weight_dirpath)
    source_ips, sink_ips = _parse_endpoint_ips(infodta)
    ip_set = set()
    node_by_ip = {}

    personalization = {}
    for nd in node_list:
        ip = _get_device_ip(nd)
        if not ip or ip == "unknown":
            continue
        ip_set.add(ip)
        node_by_ip[ip] = nd

        try: cross_count = int(nd.get("cross", 0))
        except Exception: cross_count = 0

        max_weight = 0
        for evt in nd.get("alarms", []) + nd.get("logs", []):
            name = evt if isinstance(evt, str) else evt.get("alarm_name", evt.get("name", ""))
            if name and (name_lower := str(name).lower()) in weights_dict:
                w = weights_dict[name_lower]
                # 三分类加权
                if tax and name in tax:
                    atype = tax[name].get("type", "symptom")
                    if atype == "causal":
                        w = w * 1.0            # 根因型: 全权重
                    elif atype == "symptom":
                        w = w * 0.3            # 继发型: 降权
                    else:
                        w = w * 0.05           # 噪声型: 几乎忽略
                if w > max_weight:
                    max_weight = w

        entity_score = 0.0
        if max_weight > 0:
            entity_score += float(max_weight)
        elif nd.get("alarms"):
            entity_score += len(nd["alarms"]) * 2.0
        elif nd.get("logs"):
            entity_score += 0.5
        if entity_score > 0 and cross_count > 0:
            entity_score += entity_score * cross_count * 0.5

        personalization[ip] = 0.1 + entity_score + (0.5 if ip in source_ips or ip in sink_ips else 0)

    if not ip_set:
        return {}

    if directed:
        G = nx.DiGraph()
        for ip, nd in node_by_ip.items():
            G.add_node(ip)
            for up in nd.get("linked_from", []):
                if up in ip_set:
                    G.add_edge(ip, up)
            for dn in nd.get("linked_to", []):
                if dn in ip_set:
                    G.add_edge(dn, ip)
    else:
        G = nx.Graph()
        for ip, nd in node_by_ip.items():
            G.add_node(ip)
            for nb in nd.get("linked_to", []) + nd.get("linked_from", []):
                G.add_edge(ip, nb)

    for n in G.nodes:
        if n not in personalization:
            personalization[n] = 0.1

    try:
        scores = nx.pagerank(G, alpha=_DEFAULT_PAGERANK_ALPHA, personalization=personalization)
    except Exception:
        return {}

    if not scores:
        return {}
    max_s = max(scores.values())
    return {ip: s / max_s for ip, s in scores.items()} if max_s > 0 else {}


# ── Skill 2: co_occurrence_alarm_check ──────────────────────────


# ── Skill 3: temporal_score_devices ─────────────────────────────

def _score_temporal(node_list, infodta=None, dirpath="", alarm_taxonomy=None):
    """
    Run temporal scorer. If alarm_taxonomy provided, devices with ONLY
    symptom/noise alarms get their temporal score heavily penalized (×0.1).
    If dirpath has alarm_taxonomy.json, it is auto-loaded when no taxonomy is provided.
    """
    # 若无显式 taxonomy, 尝试从 case 目录自动加载 per-case 分类
    tax = alarm_taxonomy
    if tax is None and dirpath:
        tax_path = os.path.join(dirpath, "alarm_taxonomy.json")
        if os.path.exists(tax_path):
            try: tax = json.load(open(tax_path, encoding="utf-8"))
            except Exception: pass

    skill_map = _load_skills()
    fn = skill_map.get("temporal_score_devices")
    if not fn:
        return {}
    try:
        out = fn(node_list, infodta or {}, dirpath=dirpath)
    except Exception:
        return {}
    parsed = _safe_json_loads(out)
    if not isinstance(parsed, dict):
        return {}
    raw = parsed.get("device_scores", {}) or {}
    if not raw:
        return {}
    max_s = max(v for v in raw.values() if isinstance(v, (int, float)))
    scores = {ip: s / max_s for ip, s in raw.items()
              if isinstance(s, (int, float))} if max_s > 0 else {}

    # 分类加权: 只有非 causal 告警的设备惩罚
    if tax:
        for nd in node_list:
            ip = _get_device_ip(nd)
            if ip not in scores or scores[ip] == 0:
                continue
            has_causal = any(
                tax.get(
                    (evt if isinstance(evt, str) else evt.get("alarm_name", evt.get("name", ""))).strip(),
                    {}).get("type") == "causal"
                for evt in nd.get("alarms", []) + nd.get("logs", [])
            )
            if not has_causal:
                scores[ip] = scores[ip] * 0.1  # 无根因型告警, 时序嫌疑大幅削弱

    return scores


# ══════════════════════════════════════════════════════════════════════
# Score combiner
# ══════════════════════════════════════════════════════════════════════

SKILL_SCORER = {
    1: _score_topo,
    2: _score_temporal,
}


def _combine_scores(skill_id_to_scores, node_ips):
    """
    每项 Skill 得分归一化到 [0,1] 后等权平均，返回按得分降序排列的 IP 列表。
    """
    if not skill_id_to_scores:
        return node_ips[:5] if node_ips else []

    combined = {}
    for ip in node_ips:
        vals = [scores.get(ip, 0) for scores in skill_id_to_scores.values()]
        combined[ip] = sum(vals) / len(vals)

    sorted_items = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    return [ip for ip, _ in sorted_items]


def rank_devices_by_skills(node_list, infodta, dirpath="",
                           skill_ids=(1, 2), directed=True,
                           weight_dirpath=None, top_k=5,
                           alarm_taxonomy=None):
    """
    核心函数：对一组 skill 运行评分并融合排名。

    Args:
        ...
        alarm_taxonomy: 告警分类字典 {name: {type, severity}}，
                        None 时保持原方案不变
    """
    skill_id_to_scores = {}
    skill_details = {}

    for sid in skill_ids:
        scorer = SKILL_SCORER.get(sid)
        if not scorer:
            continue
        try:
            if sid == 1:
                scores = scorer(node_list, infodta,
                                weight_dirpath=weight_dirpath, directed=directed,
                                alarm_taxonomy=alarm_taxonomy, case_dir=dirpath)
            elif sid == 2:
                scores = scorer(node_list, infodta, dirpath=dirpath,
                                alarm_taxonomy=alarm_taxonomy)
            else:
                scores = scorer(node_list, infodta)
        except Exception:
            scores = {}
        if scores:
            skill_id_to_scores[sid] = scores
            skill_details[str(sid)] = {
                "num_devices_scored": len(scores),
                "top3": sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3],
            }

    all_ips = list({_get_device_ip(n) for n in node_list if _get_device_ip(n) != "unknown"})
    ranked = _combine_scores(skill_id_to_scores, all_ips)
    return ranked[:top_k], skill_details


# ══════════════════════════════════════════════════════════════════════
# Batch pipeline + CLI
# ══════════════════════════════════════════════════════════════════════

def _read_gt_ips(dirpath: str):
    """从 label.json 提取 gt IP（与 Score_N 一致）。"""
    label_path = os.path.join(dirpath, "label.json")
    if not os.path.exists(label_path): return []
    try:
        labels = json.load(open(label_path, encoding="utf-8"))
    except Exception: return []
    if not isinstance(labels, list): return []
    labels_sorted = sorted(labels, key=lambda x: x.get("ranking", 999))
    gt_ips = []
    for lb in labels_sorted[:3]:
        for an in lb.get("abnormal_node", []):
            ip = an.get("ip")
            if ip and ip not in gt_ips: gt_ips.append(ip)
    return gt_ips


def _find_full_link_file(dirpath, filenames):
    for f in filenames:
        if "全链路.json" in f and "pingmesh" in f:
            return f
    return None


def run_skill_pipeline(data_root, output_dir, skill_ids=(1, 2),
                       directed=True, top_k=5, weight_path=None,
                       alarm_taxonomy=None):
    """
    遍历数据集，对每个 case 运行指定 skill 组合，输出 res.json。

    Args:
        weight_path: 告警权重文件路径，None 则从 config 读默认值
        alarm_taxonomy: 告警分类字典 {name: {type, severity}}，
                        None 时保持原方案不变
    """
    if weight_path:
        _wpath = weight_path
    else:
        try:
            from Sys.config import config
            _wpath = config.data.alarm_weights
        except Exception:
            _wpath = None

    mode_desc = "topo+temporal"
    if alarm_taxonomy:
        mode_desc += "_classified"

    print(f"Skill Pipeline ({mode_desc}, top_k={top_k})")
    print(f"扫描目录: {data_root}")

    start_time = time.time()
    results = []
    case_count = 0

    for dirpath, _dirnames, filenames in os.walk(data_root):
        node_file = _find_full_link_file(dirpath, filenames)
        if not (node_file and "info.json" in filenames):
            continue

        try:
            node_path = os.path.join(dirpath, node_file)
            info_path = os.path.join(dirpath, "info.json")
            raw = json.load(open(node_path, "r", encoding="utf-8"))
            node_list = list(raw.values()) if isinstance(raw, dict) else raw
            info = json.load(open(info_path, "r", encoding="utf-8"))

            predicted_ips, details = rank_devices_by_skills(
                node_list, info, dirpath,
                skill_ids=skill_ids, directed=directed,
                weight_dirpath=_wpath, top_k=top_k,
                alarm_taxonomy=alarm_taxonomy)

            mock_response = json.dumps({
                "reasoning": f"纯算法流水线 ({mode_desc})，skill_ids={list(skill_ids)}。",
                "ip": predicted_ips,
                "skill_details": details,
            }, ensure_ascii=False, indent=2)

            mock_str = f"```json\n{mock_response}\n```"

            results.append({
                "dir": dirpath,
                "prompt": f"SKILL_PIPELINE_{mode_desc.upper()}",
                "draft_response": mock_str,
                "response": mock_str,
                "skill_ips": predicted_ips,
                "gt_ips": _read_gt_ips(dirpath),
            })
            case_count += 1

        except Exception as e:
            print(f"[Error] {dirpath}: {e}")

    os.makedirs(output_dir, exist_ok=True)
    res_path = os.path.join(output_dir, "res.json")
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    elapsed = time.time() - start_time
    print(f"完成！共 {case_count} 个 case，耗时 {elapsed:.2f}s")
    print(f"结果: {res_path}")
    return res_path


if __name__ == "__main__":
    import argparse

    try:
        from Sys.config import config
        _data = config.data.nodes_labeled
        _res = config.data.results
        _default_skills = config.skill.skill_ids
    except Exception:
        _data = "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"
        _res = "/home/sbp/lixinyang/pingmesh/data/res"
        _default_skills = [1, 2]

    p = argparse.ArgumentParser(description="Skill Pipeline — 纯算法 Skill 评分流水线（不依赖 LLM）")
    p.add_argument("--data-root", "-d", default=_data, help="数据根目录")
    p.add_argument("--output-dir", "-o", default=None,
                   help="结果输出子目录名（相对于 results）")
    p.add_argument("--skills", "-s", nargs="*", type=int, default=_default_skills,
                   help="启用的 Skill ID 列表")
    p.add_argument("--directed", action="store_true", default=True,
                   help="Skill 1 使用有向 PageRank（默认: 有向）")
    p.add_argument("--top-k", "-k", type=int, default=5,
                   help="输出的预测 IP 数量 (default: 5)")
    p.add_argument("--weight-file", "-w", default=None,
                   help="告警权重文件路径（默认: config.data.alarm_weights）")
    p.add_argument("--taxonomy", "-t", default=None,
                   help="告警分类 taxonomy 文件路径 (alarm_taxonomy.json)")
    args = p.parse_args()

    # 加载 taxonomy
    taxonomy = None
    if args.taxonomy and os.path.exists(args.taxonomy):
        taxonomy = json.load(open(args.taxonomy, "r", encoding="utf-8"))
        print(f"已加载 taxonomy: {len(taxonomy)} 条")
    elif args.taxonomy:
        print(f"WARNING: taxonomy 文件不存在: {args.taxonomy}")

    variant = "dir" if args.directed else "undir"
    skill_tag = "_".join(str(s) for s in args.skills)
    if taxonomy:
        skill_tag += "_classified"
    if args.weight_file:
        wtag = os.path.splitext(os.path.basename(args.weight_file))[0]
        skill_tag += f"__{wtag}"
    timenow = int(time.time())

    if args.output_dir:
        out_dir = os.path.join(_res, args.output_dir)
    else:
        out_dir = os.path.join(_res, f"skillpipe_{skill_tag}_{variant}_{timenow}")

    run_skill_pipeline(args.data_root, out_dir,
                       skill_ids=args.skills,
                       directed=args.directed,
                       top_k=args.top_k,
                       weight_path=args.weight_file,
                       alarm_taxonomy=taxonomy)
