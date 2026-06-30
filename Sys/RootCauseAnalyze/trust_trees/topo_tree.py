from __future__ import annotations

from typing import Any, Dict, List

from .common import (
    as_float,
    ips_from_entries,
    normalize_entries,
    top1_largest_local_gap,
    top3_overlap,
    tree_result,
    truthy,
)


def _diagnostic_top3(topo: Dict[str, Any], key: str) -> List[str]:
    diagnostics = topo.get("diagnostics", {}) if isinstance(topo, dict) else {}
    value = diagnostics.get(key, [])
    return [ip for ip in value if isinstance(ip, str)] if isinstance(value, list) else []


def _top1_algorithm_evidence(top_entry: Dict[str, Any]) -> Dict[str, bool]:
    seed_type = str(top_entry.get("seed_type", "") or "").lower()
    return {
        "top1_high_weight_alarm": truthy(top_entry.get("high_weight_alarm_hit"))
        or as_float(top_entry.get("max_alarm_weight")) > 0,
        "top1_cross_positive": as_float(top_entry.get("cross")) > 0,
        "top1_source_sink_related": truthy(top_entry.get("source_sink_related"))
        or str(top_entry.get("endpoint_role", "") or "").lower() in {"source", "sink", "source_sink"},
        "top1_nonbaseline_seed": bool(seed_type) and seed_type != "baseline",
    }


def assess_topo_tree(topo: Dict[str, Any]) -> Dict[str, Any]:
    """Assess whether topology ranker evidence is strong, weak, or uncertain."""
    topo = topo if isinstance(topo, dict) else {}
    entries = normalize_entries(topo.get("rankings", []), "pr_score")
    topo_ips = ips_from_entries(entries)
    top_entry = entries[0] if entries else {}
    top_ip = top_entry.get("ip")

    directed_top3 = _diagnostic_top3(topo, "directed_top3") or topo_ips[:3]
    undirected_top3 = _diagnostic_top3(topo, "undirected_top3")
    overlap_n, overlap_ips = top3_overlap(directed_top3, undirected_top3)

    pagerank_available = topo.get("diagnostics", {}).get("pagerank_available", True)
    shape_checks = {
        "directed_undirected_top1_match": bool(directed_top3 and undirected_top3 and directed_top3[0] == undirected_top3[0]),
        "directed_top1_in_undirected_top3": bool(directed_top3 and directed_top3[0] in set(undirected_top3[:3])),
        "directed_undirected_top3_overlap_ge2": overlap_n >= 2,
        "top1_largest_local_gap": bool(pagerank_available) and top1_largest_local_gap(entries),
    }
    evidence_checks = _top1_algorithm_evidence(top_entry)

    ranking_shape_ok = any(shape_checks.values())
    algorithm_evidence_ok = any(evidence_checks.values())

    passed = [name for name, ok in {**shape_checks, **evidence_checks}.items() if ok]
    failed = [name for name, ok in {**shape_checks, **evidence_checks}.items() if not ok]
    if not ranking_shape_ok:
        failed.append("topo_ranking_shape_ok")
    if not algorithm_evidence_ok:
        failed.append("topo_algorithm_evidence_ok")

    if ranking_shape_ok and algorithm_evidence_ok:
        state = "strong"
    elif not ranking_shape_ok and not algorithm_evidence_ok:
        state = "weak"
    else:
        state = "uncertain"

    return tree_result(
        state=state,
        passed=passed,
        failed=failed,
        evidence={
            "top_ip": top_ip,
            "top_ips": topo_ips[:5],
            "directed_top3": directed_top3[:3],
            "undirected_top3": undirected_top3[:3],
            "directed_undirected_top3_overlap": overlap_ips,
            "ranking_shape_ok": ranking_shape_ok,
            "algorithm_evidence_ok": algorithm_evidence_ok,
            "pagerank_available": pagerank_available,
            "top_entry": top_entry,
        },
    )
