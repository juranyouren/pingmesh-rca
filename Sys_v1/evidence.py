from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Mapping, Sequence

from Sys.utils.alarm_utils import event_name, event_ts
from Sys.utils.case_utils import get_device_ip


EVIDENCE_SCHEMA_VERSION = "sys-v1-evidence-table-v1"


def _event_record(event: Any, *, kind: str) -> Dict[str, Any]:
    if isinstance(event, str):
        return {"kind": kind, "name": event, "timestamp": None}
    if not isinstance(event, dict):
        return {"kind": kind, "name": "", "timestamp": None}
    return {
        "kind": kind,
        "name": event_name(event),
        "timestamp": event_ts(event),
        "description": event.get("alarm_description", event.get("description", "")),
        "object": event.get("object", event.get("interface", event.get("if_name", ""))),
        "admin_status": event.get("admin_status", event.get("AdminStatus")),
        "oper_status": event.get("oper_status", event.get("OperStatus")),
    }


def load_semantic_cache(cache_dir: str | None, case_dir: str) -> Dict[str, Any]:
    """Load optional per-device semantic annotations.

    Supported files are ``<case-id>.json`` or ``<sha1(abs-case-path)>.json``.
    Supported payloads are either ``{ip: summary}`` or
    ``{"devices": [{"ip": ..., "semantic_summary": ...}]}``.
    """

    if not cache_dir:
        return {}
    case_id = os.path.basename(os.path.normpath(case_dir))
    path_hash = hashlib.sha1(os.path.abspath(case_dir).encode("utf-8")).hexdigest()
    candidates = [
        os.path.join(cache_dir, f"{case_id}.json"),
        os.path.join(cache_dir, f"{path_hash}.json"),
    ]
    payload: Any = None
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            break
        except (OSError, json.JSONDecodeError):
            payload = None
    if isinstance(payload, dict) and isinstance(payload.get("devices"), list):
        return {
            str(row.get("ip")): row.get("semantic_summary", row.get("semantic", ""))
            for row in payload["devices"]
            if isinstance(row, dict) and row.get("ip")
        }
    if isinstance(payload, dict):
        return {str(ip): value for ip, value in payload.items()}
    return {}


def build_evidence_table(
    node_list: Sequence[Dict[str, Any]],
    candidate_ips: Sequence[str],
    *,
    topology_scores: Mapping[str, float] | None = None,
    temporal_scores: Mapping[str, float] | None = None,
    temporal_features: Mapping[str, Mapping[str, Any]] | None = None,
    semantic_annotations: Mapping[str, Any] | None = None,
    max_events_per_device: int = 30,
) -> list[Dict[str, Any]]:
    node_by_ip = {
        ip: node
        for node in node_list
        if (ip := get_device_ip(node)) and ip != "unknown"
    }
    topology_scores = topology_scores or {}
    temporal_scores = temporal_scores or {}
    temporal_features = temporal_features or {}
    semantic_annotations = semantic_annotations or {}

    rows: list[Dict[str, Any]] = []
    for ip in candidate_ips:
        node = node_by_ip.get(ip, {})
        alarms = [
            _event_record(event, kind="alarm")
            for event in list(node.get("alarms", []))[:max_events_per_device]
        ]
        logs = [
            _event_record(event, kind="log")
            for event in list(node.get("logs", []))[:max_events_per_device]
        ]
        timestamps = [
            event["timestamp"]
            for event in [*alarms, *logs]
            if event.get("timestamp") is not None
        ]
        descriptions = [
            event.get("description")
            for event in [*alarms, *logs]
            if event.get("description")
        ]
        total_events = len(node.get("alarms", [])) + len(node.get("logs", []))
        rows.append(
            {
                "schema_version": EVIDENCE_SCHEMA_VERSION,
                "candidate_ip": ip,
                "role": node.get("role", "UNKNOWN"),
                "topology": {
                    "score": topology_scores.get(ip),
                    "cross": node.get("cross", 0),
                    "upstream": list(node.get("linked_from", []))[:10],
                    "downstream": list(node.get("linked_to", []))[:10],
                },
                "temporal": {
                    "score": temporal_scores.get(ip),
                    "features": dict(temporal_features.get(ip, {})),
                },
                "events": {
                    "alarm_count": len(node.get("alarms", [])),
                    "log_count": len(node.get("logs", [])),
                    "alarms": alarms,
                    "logs": logs,
                    "truncated": total_events > max_events_per_device * 2,
                },
                "semantic": {
                    "annotation": semantic_annotations.get(ip),
                    "available": ip in semantic_annotations,
                },
                "evidence_quality": {
                    "event_count": total_events,
                    "timestamp_coverage": (len(timestamps) / total_events if total_events else 0.0),
                    "description_coverage": (len(descriptions) / total_events if total_events else 0.0),
                    "semantic_available": ip in semantic_annotations,
                },
            }
        )
    return rows

def build_raw_review_context(
    node_list: Sequence[Dict[str, Any]],
    candidate_ips: Sequence[str],
    *,
    topology_scores: Mapping[str, float],
    max_events_per_device: int = 30,
) -> list[Dict[str, Any]]:
    """Build minimal M3 review context when M2 is ablated.

    This contains raw candidate facts only. It deliberately excludes temporal
    features and semantic annotations, so M1+M3 does not silently re-enable M2.
    """

    node_by_ip = {
        ip: node
        for node in node_list
        if (ip := get_device_ip(node)) and ip != "unknown"
    }
    rows = []
    for ip in candidate_ips:
        node = node_by_ip.get(ip, {})
        rows.append(
            {
                "candidate_ip": ip,
                "role": node.get("role", "UNKNOWN"),
                "topology_score": topology_scores.get(ip),
                "cross": node.get("cross", 0),
                "raw_alarms": list(node.get("alarms", []))[:max_events_per_device],
                "raw_logs": list(node.get("logs", []))[:max_events_per_device],
            }
        )
    return rows
