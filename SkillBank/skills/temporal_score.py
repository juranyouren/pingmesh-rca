SKILL_META = {
    "skill_id": "5",
    "skill_name": "temporal_score_devices",
    "target_error": "纯拓扑 PageRank 忽略了告警的时间维度——根因设备的告警往往最先触发且集中爆发，而级联设备的告警延迟出现且分散。缺少时间信号导致根因设备排名偏低。",
    "python_executor": "temporal_score_devices",
    "trigger_conditions": {
        "logic": "当 case 中的告警/日志包含 alarm_time 时间戳时触发，计算每个设备的时间维度嫌疑度。",
        "rules": ["node_list 不为空", "至少部分节点包含 alarm_time 字段"],
        "negative_rules": ["如果所有告警都没有时间戳，跳过此技能"]
    },
    "execution_instructions": "1. 以故障触发时间 (info.alarm_time) 为参考点，计算每个设备告警的 Burst Score（前 5 分钟集中度）、Early Bird Score（最早告警排名）、Temporal Density（单位时间密度）。2. 综合三个特征输出设备时序嫌疑度排序。3. 结合 Skill 4 (告警权重) 的结果，将时序得分与告警权重相乘或加权求和，更新 PageRank personalization 向量。"
}

import os
import json
from collections import defaultdict


def _get_device_ip(node):
    """Extract device IP (mgmt_ip > ip > name)."""
    return node.get("mgmt_ip", node.get("ip", node.get("name", "")))


def _extract_timestamps_from_node(node):
    """
    Extract sorted list of alarm/log timestamps (millisecond epoch) from a device node.
    Handles both the in-node alarms/logs fields and aggregated alarm structures.
    """
    timestamps = []
    for evt in node.get("alarms", []) + node.get("logs", []):
        if not isinstance(evt, dict):
            continue
        ts = evt.get("alarm_time") or evt.get("time")
        if ts:
            try:
                timestamps.append(int(ts))
            except (ValueError, TypeError):
                pass
    return sorted(timestamps)


def _read_label_timestamps(dirpath):
    """
    Fallback: read alarm timestamps from label.json for root cause devices only.
    Returns {device_ip: [timestamps]}.
    """
    result = defaultdict(list)
    label_path = os.path.join(dirpath, "label.json")
    if not os.path.exists(label_path):
        return result
    try:
        with open(label_path, "r", encoding="utf-8") as f:
            labels = json.load(f)
    except Exception:
        return result
    if not isinstance(labels, list):
        return result

    for item in labels:
        for node in item.get("abnormal_node", []):
            ip = node.get("ip", "")
            if not ip:
                continue
            for evt in node.get("alarms", []) + node.get("syslogs", []):
                if not isinstance(evt, dict):
                    continue
                ts = evt.get("alarm_time")
                if ts:
                    try:
                        result[ip].append(int(ts))
                    except (ValueError, TypeError):
                        pass
    return result


def _compute_burst_score(timestamps, ref_time, window_ms=300000):
    """
    Burst Score: proportion of alarms that fire within `window_ms` of the reference time.
    Root cause devices typically have concentrated alarm bursts near the fault onset.
    Returns 0.0 ~ 1.0.
    """
    if not timestamps:
        return 0.0
    in_window = sum(1 for t in timestamps if abs(t - ref_time) <= window_ms)
    return in_window / len(timestamps)


def _compute_early_bird_score(device_first_ts, all_first_timestamps):
    """
    Early Bird Score: 1 / rank of this device's earliest alarm among all devices.
    If this device's first alarm is the earliest overall → score ≈ 1.0.
    Returns 0.0 ~ 1.0.
    """
    if device_first_ts is None or not all_first_timestamps:
        return 0.0
    sorted_ts = sorted(all_first_timestamps)
    try:
        rank = sorted_ts.index(device_first_ts) + 1
    except ValueError:
        rank = len(sorted_ts)
    return 1.0 / rank


def _compute_temporal_density(timestamps):
    """
    Temporal Density: alarms per minute during the active interval.
    High density → burst-like behavior → more likely root cause.
    Returns float (alarms/minute).
    """
    if len(timestamps) < 2:
        return float(len(timestamps))
    span_ms = timestamps[-1] - timestamps[0]
    if span_ms <= 0:
        return float(len(timestamps))
    span_min = span_ms / 60000.0
    return len(timestamps) / max(span_min, 0.001)


def temporal_score_devices(
    node_list: list,
    info: dict = {},
    dirpath: str = "",
    ref_time_ms: int = None,
    window_ms: int = 300000
) -> str:
    """
    Compute temporal suspicion scores for each device.

    Three features:
      1. Burst Score    — concentration of alarms near fault reference time
      2. Early Bird     — how early this device's first alarm appears
      3. Temporal Density — alarms per minute (burst density)

    Args:
        node_list: list of device node dicts
        info: case info dict (contains alarm_time as fault reference)
        dirpath: path to case directory (for fallback label.json reading)
        ref_time_ms: override reference timestamp (default: info["alarm_time"])
        window_ms: burst detection window in ms (default 5 min)

    Returns:
        JSON string: {"device_scores": {ip: score}, "top_devices": [...]}
    """
    # ── 1. Determine reference time ──────────────────────────────
    if ref_time_ms is None:
        ref_time_ms = info.get("alarm_time")
    if ref_time_ms is None:
        # try reading from *_info.json as fallback
        for fname in os.listdir(dirpath) if dirpath else []:
            if fname.endswith("_info.json"):
                try:
                    with open(os.path.join(dirpath, fname), "r") as f:
                        extra = json.load(f)
                    ref_time_ms = extra.get("alarm_time")
                    break
                except Exception:
                    pass

    # ── 2. Collect per-device timestamps ─────────────────────────
    device_timestamps = {}   # ip → [timestamps]
    for nd in node_list:
        ip = _get_device_ip(nd)
        if ip == "unknown" or not ip:
            continue
        tss = _extract_timestamps_from_node(nd)
        device_timestamps[ip] = tss

    # fallback: enrich with label.json
    if dirpath:
        label_ts = _read_label_timestamps(dirpath)
        for ip, tss in label_ts.items():
            if ip in device_timestamps:
                device_timestamps[ip] = sorted(set(device_timestamps[ip] + tss))
            else:
                device_timestamps[ip] = sorted(tss)

    # ── 3. Compute global reference values ───────────────────────
    all_first_ts = []
    for tss in device_timestamps.values():
        if tss:
            all_first_ts.append(tss[0])

    # ── 4. Compute per-device temporal features ──────────────────
    scores = {}
    for ip, tss in device_timestamps.items():
        if not tss:
            scores[ip] = 0.0
            continue

        burst = _compute_burst_score(tss, ref_time_ms, window_ms)
        early = _compute_early_bird_score(tss[0], all_first_ts)
        density = _compute_temporal_density(tss)

        # Normalize density to ~0-1 range (empirical cap at 20 alarms/min)
        norm_density = min(density / 20.0, 1.0)

        # Combined score: burst (0.4) + early_bird (0.35) + density (0.25)
        combined = 0.40 * burst + 0.35 * early + 0.25 * norm_density
        scores[ip] = round(combined, 4)

    # ── 5. Build output ──────────────────────────────────────────
    sorted_devices = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_devices = [{"ip": ip, "temporal_score": sc} for ip, sc in sorted_devices[:10]]

    result = {
        "device_scores": scores,
        "top_devices": top_devices,
        "ref_time_ms": ref_time_ms,
        "total_devices_scored": len(scores)
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Skill executor interface ──────────────────────────────────────
EXECUTORS = {
    "temporal_score_devices": temporal_score_devices
}
