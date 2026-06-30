from __future__ import annotations

from typing import Any, Dict, List

from .common import as_float, ips_from_entries, normalize_entries, top1_largest_local_gap, tree_result


def _diagnostic_top3(temporal: Dict[str, Any], key: str) -> List[str]:
    diagnostics = temporal.get("diagnostics", {}) if isinstance(temporal, dict) else {}
    value = diagnostics.get(key, [])
    return [ip for ip in value if isinstance(ip, str)] if isinstance(value, list) else []


def assess_temporal_tree(temporal: Dict[str, Any]) -> Dict[str, Any]:
    """Assess whether temporal ranker evidence is strong, weak, or uncertain."""
    temporal = temporal if isinstance(temporal, dict) else {}
    diagnostics = temporal.get("diagnostics", {}) if isinstance(temporal.get("diagnostics"), dict) else {}
    entries = normalize_entries(temporal.get("rankings", []), "score")
    temporal_ips = ips_from_entries(entries)
    top_entry = entries[0] if entries else {}
    top_ip = top_entry.get("ip")

    burst_top3 = _diagnostic_top3(temporal, "burst_top3")
    early_top3 = _diagnostic_top3(temporal, "early_top3")
    density_top3 = _diagnostic_top3(temporal, "density_top3")
    supported_by = [
        name
        for name, ips in (
            ("burst", burst_top3),
            ("early", early_top3),
            ("density", density_top3),
        )
        if top_ip and top_ip in set(ips[:3])
    ]

    top_event_count = as_float(top_entry.get("total_alarms")) + as_float(top_entry.get("total_logs"))
    temporal_data_available = (
        diagnostics.get("ref_time_ms") is not None
        and as_float(diagnostics.get("devices_with_timestamps")) >= 2
        and top_event_count > 0
    )
    top1_supported_by_two = len(supported_by) >= 2
    burst_or_density = "burst" in supported_by or "density" in supported_by
    ranking_shape_ok = top1_largest_local_gap(entries) or top1_supported_by_two
    algorithm_evidence_ok = top1_supported_by_two and burst_or_density

    checks = {
        "temporal_data_available": temporal_data_available,
        "top1_largest_local_gap": top1_largest_local_gap(entries),
        "top1_supported_by_two_temporal_subsignals": top1_supported_by_two,
        "top1_has_burst_or_density_support": burst_or_density,
    }
    passed = [name for name, ok in checks.items() if ok]
    failed = [name for name, ok in checks.items() if not ok]
    if not ranking_shape_ok:
        failed.append("temporal_ranking_shape_ok")
    if not algorithm_evidence_ok:
        failed.append("temporal_algorithm_evidence_ok")

    if temporal_data_available and ranking_shape_ok and algorithm_evidence_ok:
        state = "strong"
    elif (not temporal_data_available) or (not ranking_shape_ok and not algorithm_evidence_ok):
        state = "weak"
    else:
        state = "uncertain"

    return tree_result(
        state=state,
        passed=passed,
        failed=failed,
        evidence={
            "top_ip": top_ip,
            "top_ips": temporal_ips[:5],
            "ref_time_ms": diagnostics.get("ref_time_ms"),
            "devices_with_timestamps": diagnostics.get("devices_with_timestamps", 0),
            "top_event_count": top_event_count,
            "supported_by": supported_by,
            "burst_top3": burst_top3[:3],
            "early_top3": early_top3[:3],
            "density_top3": density_top3[:3],
            "ranking_shape_ok": ranking_shape_ok,
            "algorithm_evidence_ok": algorithm_evidence_ok,
            "top_entry": top_entry,
        },
    )
