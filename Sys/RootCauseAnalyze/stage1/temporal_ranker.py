from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

from Sys.RootCauseAnalyze.trust_trees.temporal_tree import assess_temporal_tree
from Sys.utils.alarm_utils import event_ts, node_events
from Sys.utils.case_utils import get_device_ip
from Sys.utils.ranking_utils import sorted_score_items


SKILL_META = {
    "skill_id": "2",
    "skill_name": "temporal_score_devices",
    "python_executor": "score_temporal",
    "target_error": "Temporal burst, early-bird, and density ranking.",
}


def temporal_reference_time(info: Dict[str, Any], dirpath: str) -> int | None:
    ref_time_ms = info.get("alarm_time") if isinstance(info, dict) else None
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


def temporal_density(timestamps: List[int]) -> float:
    if len(timestamps) < 2:
        return float(len(timestamps))
    span_ms = timestamps[-1] - timestamps[0]
    if span_ms <= 0:
        return float(len(timestamps))
    return len(timestamps) / max(span_ms / 60000.0, 0.001)


def temporal_feature_details(
    node_list: List[Dict[str, Any]],
    info: Dict[str, Any],
    dirpath: str,
) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Any]]:
    ref_time_ms = temporal_reference_time(info, dirpath)
    device_timestamps: Dict[str, List[int]] = {}
    for node in node_list:
        ip = get_device_ip(node)
        if ip == "unknown" or not ip:
            continue
        timestamps = sorted(ts for ts in (event_ts(evt) for evt in node_events(node)) if ts is not None)
        device_timestamps[ip] = timestamps

    all_first_ts = sorted(tss[0] for tss in device_timestamps.values() if tss)
    features: Dict[str, Dict[str, float]] = {}
    for ip, timestamps in device_timestamps.items():
        if not timestamps or ref_time_ms is None:
            burst = early = density = raw_score = 0.0
        else:
            burst = sum(1 for ts in timestamps if abs(ts - ref_time_ms) <= 300000) / len(timestamps)
            early = 1.0 / (all_first_ts.index(timestamps[0]) + 1) if timestamps[0] in all_first_ts else 0.0
            density_raw = temporal_density(timestamps)
            density = min(density_raw / 20.0, 1.0)
            raw_score = 0.40 * burst + 0.35 * early + 0.25 * density
        features[ip] = {
            "burst_score": round(burst, 6),
            "early_bird_score": round(early, 6),
            "density_score": round(density, 6),
            "raw_temporal_score": round(raw_score, 6),
            "timestamp_count": len(timestamps),
        }

    def top3_by(key: str) -> List[str]:
        return [
            ip
            for ip, _val in sorted(
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


def score_temporal(node_list: List[Dict[str, Any]], info: Dict[str, Any] | None = None, *, dirpath: str = "") -> Dict[str, float]:
    features, _diagnostics = temporal_feature_details(node_list, info or {}, dirpath)
    raw = {ip: vals["raw_temporal_score"] for ip, vals in features.items()}
    numeric = [value for value in raw.values() if isinstance(value, (int, float))]
    if not numeric:
        return {}
    max_score = max(numeric)
    return {ip: score / max_score for ip, score in raw.items() if isinstance(score, (int, float))} if max_score > 0 else {}


def temporal_details(
    node_list: List[Dict[str, Any]],
    info: Dict[str, Any],
    dirpath: str,
    scores: Dict[str, float],
    *,
    top_k: int,
) -> Dict[str, Any]:
    node_by_ip = {get_device_ip(node): node for node in node_list if get_device_ip(node) != "unknown"}
    features, diagnostics = temporal_feature_details(node_list, info, dirpath)

    rankings = []
    for rank, (ip, score) in enumerate(sorted_score_items(scores or {}, top_k), 1):
        node = node_by_ip.get(ip, {})
        rankings.append(
            {
                "rank": rank,
                "ip": ip,
                "score": round(score, 6),
                "total_alarms": len(node.get("alarms", [])),
                "total_logs": len(node.get("logs", [])),
                **features.get(ip, {}),
            }
        )

    block = {
        "num_devices_scored": len(scores or {}),
        "top3": rankings[:3],
        "topk": rankings,
        "rankings": rankings,
        "diagnostics": diagnostics,
    }
    block["trust_tree"] = assess_temporal_tree(block)
    return block
