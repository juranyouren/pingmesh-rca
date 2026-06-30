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

from Sys.RootCauseAnalyze.trust_trees.temporal_tree import assess_temporal_tree
from Sys.RootCauseAnalyze.trust_trees.topo_tree import assess_topo_tree


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


def _event_name(evt):
    if isinstance(evt, str):
        return evt
    if isinstance(evt, dict):
        return evt.get("alarm_name", evt.get("name", ""))
    return ""


def _event_ts(evt):
    if not isinstance(evt, dict):
        return None
    raw = evt.get("alarm_time") or evt.get("time")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _node_events(node):
    return node.get("alarms", []) + node.get("logs", []) if isinstance(node, dict) else []


def _node_alarm_weight(node, weights_dict):
    max_weight = 0
    hit_names = []
    for evt in _node_events(node):
        name = _event_name(evt)
        if not name:
            continue
        weight = weights_dict.get(str(name).lower(), 0)
        if weight > 0:
            max_weight = max(max_weight, weight)
            if name not in hit_names:
                hit_names.append(name)
    return max_weight, hit_names


def _source_sink_related(ip, node, source_ips, sink_ips):
    endpoints = set(source_ips + sink_ips)
    if ip in endpoints:
        return True
    neighbors = set(node.get("linked_to", []) + node.get("linked_from", []))
    return bool(neighbors & endpoints)


def _seed_type(node, max_weight, source_sink_related):
    if max_weight > 0:
        return "alarm_weight"
    if node.get("alarms"):
        return "alarm_count"
    if node.get("logs"):
        return "log"
    if source_sink_related:
        return "endpoint"
    return "baseline"


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


def _score_topo(node_list, infodta, weight_dirpath=None, directed=True):
    """
    PageRank scoring.
    """
    if nx is None:
        return {}

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

def _score_temporal(node_list, infodta=None, dirpath=""):
    """
    Run temporal scorer.
    """
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

    return scores


# ══════════════════════════════════════════════════════════════════════
# Score combiner
# ══════════════════════════════════════════════════════════════════════

SKILL_SCORER = {
    1: _score_topo,
    2: _score_temporal,
}


def _sorted_score_items(scores, top_k):
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:top_k]


def _combined_score_items(skill_id_to_scores, node_ips, top_k):
    if not skill_id_to_scores:
        return []
    combined = {}
    for ip in node_ips:
        vals = [scores.get(ip, 0) for scores in skill_id_to_scores.values()]
        combined[ip] = sum(vals) / len(vals)
    return sorted(combined.items(), key=lambda x: (-x[1], x[0]))[:top_k]


def _topo_details(node_list, infodta, scores, weight_dirpath, directed, top_k):
    weights_dict = _load_alarm_weights(weight_dirpath)
    source_ips, sink_ips = _parse_endpoint_ips(infodta)
    node_by_ip = {_get_device_ip(node): node for node in node_list if _get_device_ip(node) != "unknown"}
    scores = scores or {}

    fallback_scores = {}
    for ip, node in node_by_ip.items():
        max_weight, _hit_names = _node_alarm_weight(node, weights_dict)
        related = _source_sink_related(ip, node, source_ips, sink_ips)
        try:
            cross = float(node.get("cross", 0) or 0)
        except (TypeError, ValueError):
            cross = 0.0
        fallback_scores[ip] = max_weight + cross + len(node.get("alarms", [])) * 2.0 + len(node.get("logs", [])) * 0.5 + (0.5 if related else 0.0)

    ranking_scores = scores if scores else fallback_scores
    directed_scores = scores if directed else _score_topo(node_list, infodta, weight_dirpath=weight_dirpath, directed=True)
    undirected_scores = _score_topo(node_list, infodta, weight_dirpath=weight_dirpath, directed=False) if scores else {}
    directed_top3 = [ip for ip, _ in _sorted_score_items(directed_scores or {}, 3)]
    undirected_top3 = [ip for ip, _ in _sorted_score_items(undirected_scores or {}, 3)]

    rankings = []
    for rank, (ip, score) in enumerate(_sorted_score_items(ranking_scores or {}, top_k), 1):
        node = node_by_ip.get(ip, {})
        max_weight, hit_names = _node_alarm_weight(node, weights_dict)
        related = _source_sink_related(ip, node, source_ips, sink_ips)
        rankings.append({
            "rank": rank,
            "ip": ip,
            "pr_score": round(score, 6),
            "cross": node.get("cross", 0),
            "max_alarm_weight": max_weight,
            "high_weight_alarm_hit": max_weight > 0,
            "high_weight_alarms": hit_names[:10],
            "source_sink_related": related,
            "seed_type": _seed_type(node, max_weight, related),
        })

    block = {
        "num_devices_scored": len(scores),
        "top3": rankings[:3],
        "topk": rankings,
        "rankings": rankings,
        "diagnostics": {
            "pagerank_available": bool(scores),
            "directed_top3": directed_top3,
            "undirected_top3": undirected_top3,
        },
    }
    block["trust_tree"] = assess_topo_tree(block)
    return block


def _temporal_reference_time(infodta, dirpath):
    ref_time_ms = infodta.get("alarm_time") if isinstance(infodta, dict) else None
    if ref_time_ms is None and dirpath:
        for fname in os.listdir(dirpath) if os.path.isdir(dirpath) else []:
            if not fname.endswith("_info.json"):
                continue
            try:
                with open(os.path.join(dirpath, fname), encoding="utf-8") as f:
                    ref_time_ms = json.load(f).get("alarm_time")
                if ref_time_ms is not None:
                    break
            except Exception:
                pass
    try:
        return int(ref_time_ms) if ref_time_ms is not None else None
    except (TypeError, ValueError):
        return None


def _temporal_density(timestamps):
    if len(timestamps) < 2:
        return float(len(timestamps))
    span_ms = timestamps[-1] - timestamps[0]
    if span_ms <= 0:
        return float(len(timestamps))
    return len(timestamps) / max(span_ms / 60000.0, 0.001)


def _temporal_feature_details(node_list, infodta, dirpath):
    ref_time_ms = _temporal_reference_time(infodta, dirpath)
    device_timestamps = {}
    for node in node_list:
        ip = _get_device_ip(node)
        if ip == "unknown" or not ip:
            continue
        timestamps = sorted(ts for ts in (_event_ts(evt) for evt in _node_events(node)) if ts is not None)
        device_timestamps[ip] = timestamps

    all_first_ts = sorted(tss[0] for tss in device_timestamps.values() if tss)
    features = {}
    for ip, timestamps in device_timestamps.items():
        if not timestamps or ref_time_ms is None:
            burst = early = density = raw_score = 0.0
        else:
            burst = sum(1 for ts in timestamps if abs(ts - ref_time_ms) <= 300000) / len(timestamps)
            early = 1.0 / (all_first_ts.index(timestamps[0]) + 1) if timestamps[0] in all_first_ts else 0.0
            density_raw = _temporal_density(timestamps)
            density = min(density_raw / 20.0, 1.0)
            raw_score = 0.40 * burst + 0.35 * early + 0.25 * density
        features[ip] = {
            "burst_score": round(burst, 6),
            "early_bird_score": round(early, 6),
            "density_score": round(density, 6),
            "raw_temporal_score": round(raw_score, 6),
            "timestamp_count": len(timestamps),
        }

    def top3_by(key):
        return [
            ip for ip, _val in sorted(
                ((ip, vals[key]) for ip, vals in features.items()),
                key=lambda item: (-item[1], item[0]),
            )[:3]
        ]

    diagnostics = {
        "ref_time_ms": ref_time_ms,
        "devices_with_timestamps": sum(1 for tss in device_timestamps.values() if tss),
        "burst_top3": top3_by("burst_score"),
        "early_top3": top3_by("early_bird_score"),
        "density_top3": top3_by("density_score"),
    }
    return features, diagnostics


def _temporal_details(node_list, infodta, dirpath, scores, top_k):
    node_by_ip = {_get_device_ip(node): node for node in node_list if _get_device_ip(node) != "unknown"}
    features, diagnostics = _temporal_feature_details(node_list, infodta, dirpath)

    rankings = []
    for rank, (ip, score) in enumerate(_sorted_score_items(scores or {}, top_k), 1):
        node = node_by_ip.get(ip, {})
        rankings.append({
            "rank": rank,
            "ip": ip,
            "score": round(score, 6),
            "total_alarms": len(node.get("alarms", [])),
            "total_logs": len(node.get("logs", [])),
            **features.get(ip, {}),
        })

    block = {
        "num_devices_scored": len(scores or {}),
        "top3": rankings[:3],
        "topk": rankings,
        "rankings": rankings,
        "diagnostics": diagnostics,
    }
    block["trust_tree"] = assess_temporal_tree(block)
    return block


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

    sorted_items = sorted(combined.items(), key=lambda x: (-x[1], x[0]))
    return [ip for ip, _ in sorted_items]


def rank_devices_by_skills(node_list, infodta, dirpath="",
                           skill_ids=(1, 2), directed=True,
                           weight_dirpath=None, top_k=5):
    """
    核心函数：对一组 skill 运行评分并融合排名。

    Args:
        ...
    """
    skill_id_to_scores = {}
    skill_details = {}
    all_ips = sorted({_get_device_ip(n) for n in node_list if _get_device_ip(n) != "unknown"})

    for sid in skill_ids:
        scorer = SKILL_SCORER.get(sid)
        if not scorer:
            continue
        try:
            if sid == 1:
                scores = scorer(node_list, infodta,
                                weight_dirpath=weight_dirpath, directed=directed)
            elif sid == 2:
                scores = scorer(node_list, infodta, dirpath=dirpath)
            else:
                scores = scorer(node_list, infodta)
        except Exception:
            scores = {}
        if scores:
            skill_id_to_scores[sid] = scores
        if sid == 1:
            skill_details[str(sid)] = _topo_details(node_list, infodta, scores, weight_dirpath, directed, top_k)
        elif sid == 2:
            skill_details[str(sid)] = _temporal_details(node_list, infodta, dirpath, scores, top_k)

    if 1 in skill_ids and "1" not in skill_details:
        skill_details["1"] = _topo_details(node_list, infodta, {}, weight_dirpath, directed, top_k)
    if 2 in skill_ids and "2" not in skill_details:
        skill_details["2"] = _temporal_details(node_list, infodta, dirpath, {}, top_k)

    ranked = _combine_scores(skill_id_to_scores, all_ips)
    combined_topk = [
        {"rank": rank, "ip": ip, "combined_score": round(score, 6)}
        for rank, (ip, score) in enumerate(_combined_score_items(skill_id_to_scores, all_ips, top_k), 1)
    ]
    skill_details["combined"] = {
        "top3": combined_topk[:3],
        "topk": combined_topk,
        "rankings": combined_topk,
    }
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
                       directed=True, top_k=5, weight_path=None):
    """
    遍历数据集，对每个 case 运行指定 skill 组合，输出 res.json。

    Args:
        weight_path: 告警权重文件路径，None 则从 config 读默认值
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
                weight_dirpath=_wpath, top_k=top_k)

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
    args = p.parse_args()

    variant = "dir" if args.directed else "undir"
    skill_tag = "_".join(str(s) for s in args.skills)
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
                       weight_path=args.weight_file)
