from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig, normalize_config
from Sys.utils.alarm_utils import event_name, node_events
from Sys.utils.case_utils import get_device_ip


_DESCRIPTION_KEYS = (
    "alarm_description",
    "description",
    "desc",
    "message",
    "content",
    "detail",
)
_TIME_KEYS = ("alarm_time", "time", "timestamp", "occur_time", "create_time")
_INTERFACE_PATTERNS = (
    re.compile(r"ifname\s*[=:：]\s*([A-Za-z0-9_.:/-]+)", re.I),
    re.compile(r"(?:interface|port|接口)\s*[=:：]\s*([A-Za-z0-9_.:/-]+)", re.I),
    re.compile(r"\b((?:100|40|25|10)?GE\d+(?:/\d+){1,3})\b", re.I),
)
_PEER_PATTERNS = (
    re.compile(r"(?:peer(?:address|ip)?|remote(?:device|ip)?|neighbor|对端)\s*[=:：]?\s*([A-Za-z0-9_.:-]+)", re.I),
)


def _stable_id(prefix: str, payload: str) -> str:
    return f"{prefix}-{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def _event_description(event: Any) -> str:
    if not isinstance(event, Mapping):
        return ""
    parts = [str(event.get(key, "") or "").strip() for key in _DESCRIPTION_KEYS]
    return " ".join(part for part in parts if part)


def _timestamp_ms(event: Any) -> int | None:
    if not isinstance(event, Mapping):
        return None
    raw = None
    for key in _TIME_KEYS:
        if event.get(key) not in (None, ""):
            raw = event.get(key)
            break
    if raw is None:
        return None
    try:
        value = int(float(raw))
        if abs(value) < 100_000_000_000:
            value *= 1000
        return value
    except (TypeError, ValueError):
        pass
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return int(parsed.timestamp() * 1000)
        except ValueError:
            return None
    return None


def _extract_first(patterns, text: str) -> str:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1).strip(" ,;。")
    return ""


def _event_type(text: str) -> Tuple[str, str]:
    lowered = text.lower()
    has_down = any(token in lowered for token in ("down", "todwn", "lost", "failure", "fault", "中断", "故障"))
    has_up = any(token in lowered for token in ("operstatus=up", "link up", "恢复", "recovered", "cleared"))
    if any(token in lowered for token in ("physical link", "operstatus=down", "trunkdown", "stachg_todwn", "接口down", "link down")):
        return "physical_link_down", "physical"
    if has_up and any(token in lowered for token in ("interface", "link", "port", "接口")):
        return "physical_link_up", "physical"
    if "bgp" in lowered and has_down:
        return "bgp_session_down", "control_plane"
    if "bfd" in lowered and has_down:
        return "bfd_session_down", "control_plane"
    if "lldp" in lowered:
        return "lldp_neighbor_change", "control_plane"
    if any(token in lowered for token in ("ospf", "isis", "route", "routing", "路由")):
        return "routing_change", "routing"
    if any(token in lowered for token in ("config", "configuration", "配置")):
        return "configuration_change", "management"
    if any(token in lowered for token in ("temperature", "fan", "power", "cpu", "memory", "温度", "风扇", "电源")):
        return "device_health", "device"
    if has_down and any(token in lowered for token in ("interface", "port", "link", "接口", "端口")):
        return "interface_state_down", "physical"
    return "generic_event", "unknown"


def _lifecycle(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("clear", "cleared", "recover", "resume", "恢复", "消除")):
        return "clear"
    return "raised"


def _scope(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("remote fault", "remotefault", "对端故障", "远端故障")):
        return "remote"
    if any(token in lowered for token in ("local fault", "localfault", "本端故障", "本地故障")):
        return "local"
    return "unknown"


def _quality(row: Mapping[str, Any]) -> Dict[str, float]:
    timestamp = 1.0 if row.get("timestamp_ms") is not None else 0.0
    description = 1.0 if row.get("description") else 0.0
    traceability = 1.0 if row.get("raw_evidence_id") else 0.0
    return {
        "timestamp": timestamp,
        "description": description,
        "object": 1.0 if row.get("object") else 0.0,
        "peer": 1.0 if row.get("peer_device") else 0.0,
        "traceability": traceability,
        "core": round(0.45 * timestamp + 0.25 * description + 0.30 * traceability, 6),
    }


def canonicalize_event(
    event: Any,
    *,
    device_id: str,
    source_type: str,
    source_index: int,
    device_lookup: Mapping[str, str] | None = None,
) -> Dict[str, Any]:
    name = event_name(event)
    description = _event_description(event)
    text = " ".join(part for part in (name, description) if part)
    event_type, fault_layer = _event_type(text)
    object_name = _extract_first(_INTERFACE_PATTERNS, text)
    peer_raw = _extract_first(_PEER_PATTERNS, text)
    lookup = device_lookup or {}
    peer_device = lookup.get(peer_raw, peer_raw if peer_raw in set(lookup.values()) else "")
    serialized = json.dumps(event, ensure_ascii=False, sort_keys=True) if isinstance(event, Mapping) else str(event)
    raw_id = _stable_id("RAW", f"{device_id}|{source_type}|{source_index}|{serialized}")
    row = {
        "raw_evidence_id": raw_id,
        "device_id": device_id,
        "source_type": source_type,
        "event_name": name,
        "description": description,
        "timestamp_ms": _timestamp_ms(event),
        "event_type": event_type,
        "fault_layer": fault_layer,
        "object_type": "interface" if object_name else "unknown",
        "object": object_name,
        "peer_device": peer_device,
        "peer_raw": peer_raw,
        "observation_scope": _scope(text),
        "lifecycle": _lifecycle(text),
        "parse_method": "rule",
        "parse_status": "success" if event_type != "generic_event" or object_name or peer_raw else "partial",
    }
    row["quality"] = _quality(row)
    return row


def _interval(offset_ms: int | None, uncertainty_ms: int) -> List[int] | None:
    if offset_ms is None:
        return None
    return [offset_ms - uncertainty_ms, offset_ms + uncertainty_ms]


def _episode_from_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    reference_time_ms: int | None,
    config: PropagationConfig,
    cleared_at: int | None = None,
) -> Dict[str, Any]:
    first = rows[0]
    timestamps = [int(row["timestamp_ms"]) for row in rows if row.get("timestamp_ms") is not None]
    onset = min(timestamps) if timestamps else None
    onset_offset = onset - reference_time_ms if onset is not None and reference_time_ms is not None else None
    end_offset = cleared_at - reference_time_ms if cleared_at is not None and reference_time_ms is not None else None
    raw_ids = sorted({str(row.get("raw_evidence_id")) for row in rows if row.get("raw_evidence_id")})
    identity = "|".join(
        [
            str(first.get("device_id", "")),
            str(first.get("event_type", "")),
            str(first.get("object", "")),
            str(first.get("peer_device", "")),
            str(onset or "missing"),
            *raw_ids,
        ]
    )
    quality_keys = ("timestamp", "description", "object", "peer", "traceability", "core")
    quality = {
        key: round(max(float(row.get("quality", {}).get(key, 0.0)) for row in rows), 6)
        for key in quality_keys
    }
    event_type = str(first.get("event_type", "generic_event"))
    within_window = onset_offset is not None and abs(onset_offset) <= config.event_window_ms
    relevance = 0.15
    if event_type != "generic_event":
        relevance += 0.45
    if within_window:
        relevance += 0.30
    # Interface/object details are not available in the target data and are
    # never required for incident relevance. An explicit peer remains an
    # optional direct-relation bonus.
    if first.get("peer_device"):
        relevance += 0.10
    if all(str(row.get("lifecycle")) == "clear" for row in rows):
        relevance *= 0.35
    return {
        "evidence_id": _stable_id("E", identity),
        "raw_evidence_ids": raw_ids,
        "device_id": str(first.get("device_id", "")),
        "source_types": sorted({str(row.get("source_type", "")) for row in rows}),
        "event_type": event_type,
        "fault_layer": str(first.get("fault_layer", "unknown")),
        "object_type": str(first.get("object_type", "unknown")),
        "object": str(first.get("object", "")),
        "peer_device": str(first.get("peer_device", "")),
        "observation_scope": str(first.get("observation_scope", "unknown")),
        "lifecycle": "raised_and_cleared" if cleared_at is not None else str(first.get("lifecycle", "raised")),
        "onset_time_ms": onset,
        "onset_interval_ms": _interval(onset_offset, config.timestamp_uncertainty_ms),
        "end_time_ms": cleared_at,
        "end_interval_ms": _interval(end_offset, config.timestamp_uncertainty_ms),
        "duplicate_count": len(rows),
        "parse_method": "rule",
        "parse_status": "success"
        if any(row.get("parse_status") == "success" for row in rows)
        else "partial",
        "quality": quality,
        "incident_relevance": round(min(relevance, 1.0), 6),
    }


def build_evidence_episodes(
    node_list: Sequence[Mapping[str, Any]],
    info: Mapping[str, Any] | None = None,
    *,
    config: PropagationConfig | Mapping[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    cfg = normalize_config(config)
    info = info or {}
    try:
        reference_time_ms = int(float(info.get("alarm_time")))
        if abs(reference_time_ms) < 100_000_000_000:
            reference_time_ms *= 1000
    except (TypeError, ValueError):
        reference_time_ms = None

    device_lookup: Dict[str, str] = {}
    for raw_node in node_list:
        node = dict(raw_node)
        device_id = get_device_ip(node)
        if not device_id or device_id == "unknown":
            continue
        device_lookup[device_id] = device_id
        if node.get("name"):
            device_lookup[str(node["name"])] = device_id

    canonical_rows: List[Dict[str, Any]] = []
    for raw_node in sorted(node_list, key=lambda item: get_device_ip(dict(item))):
        node = dict(raw_node)
        device_id = get_device_ip(node)
        if not device_id or device_id == "unknown":
            continue
        alarms = node.get("alarms", []) if isinstance(node.get("alarms"), list) else []
        logs = node.get("logs", []) if isinstance(node.get("logs"), list) else []
        for source_type, events in (("alarm", alarms), ("log", logs)):
            for index, event in enumerate(events):
                canonical_rows.append(
                    canonicalize_event(
                        event,
                        device_id=device_id,
                        source_type=source_type,
                        source_index=index,
                        device_lookup=device_lookup,
                    )
                )

    grouped: Dict[Tuple[str, str, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in canonical_rows:
        key = (
            row["device_id"],
            row["event_type"],
            row["object"].lower(),
            row["peer_device"].lower(),
            row["observation_scope"],
        )
        grouped[key].append(row)

    episodes: List[Dict[str, Any]] = []
    for key in sorted(grouped):
        rows = sorted(
            grouped[key],
            key=lambda row: (
                row.get("timestamp_ms") is None,
                row.get("timestamp_ms") or 0,
                row["raw_evidence_id"],
            ),
        )
        active: List[Dict[str, Any]] = []
        last_active_ts: int | None = None
        for row in rows:
            ts = row.get("timestamp_ms")
            if row["lifecycle"] == "clear":
                if active:
                    active_with_clear = [*active, row]
                    episodes.append(
                        _episode_from_rows(
                            active_with_clear,
                            reference_time_ms=reference_time_ms,
                            config=cfg,
                            cleared_at=ts,
                        )
                    )
                    active = []
                    last_active_ts = None
                else:
                    episodes.append(
                        _episode_from_rows([row], reference_time_ms=reference_time_ms, config=cfg)
                    )
                continue
            if (
                active
                and ts is not None
                and last_active_ts is not None
                and ts - last_active_ts > cfg.dedup_window_ms
            ):
                episodes.append(
                    _episode_from_rows(active, reference_time_ms=reference_time_ms, config=cfg)
                )
                active = []
            active.append(row)
            if ts is not None:
                last_active_ts = ts
        if active:
            episodes.append(_episode_from_rows(active, reference_time_ms=reference_time_ms, config=cfg))

    return sorted(
        episodes,
        key=lambda row: (
            row.get("onset_time_ms") is None,
            row.get("onset_time_ms") or 0,
            row.get("device_id", ""),
            row.get("evidence_id", ""),
        ),
    )
