from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple


DEFAULT_ALARM_WEIGHTS = {"stachg_todwn": 100, "trunkdown": 100, "vlan接口down(dcn)": 100}


def event_name(evt: Any) -> str:
    if isinstance(evt, str):
        return evt
    if isinstance(evt, dict):
        return str(evt.get("alarm_name", evt.get("name", ""))).strip()
    return ""


def event_ts(evt: Any) -> int | None:
    if not isinstance(evt, dict):
        return None
    raw = evt.get("alarm_time") or evt.get("time")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def node_events(node: Dict[str, Any]) -> List[Any]:
    return node.get("alarms", []) + node.get("logs", []) if isinstance(node, dict) else []


def extract_alarm_names(node: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    seen = set()
    for evt in node_events(node):
        name = event_name(evt)
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def load_alarm_weights(weight_path: str | None) -> Dict[str, int]:
    weights = dict(DEFAULT_ALARM_WEIGHTS)
    if weight_path and os.path.exists(weight_path):
        try:
            with open(weight_path, "r", encoding="utf-8") as f:
                for item in json.load(f):
                    if "alarm_name" in item and "alarm_priority" in item:
                        weights[str(item["alarm_name"]).lower()] = int(item["alarm_priority"])
        except Exception:
            pass
    return weights


def node_alarm_weight(node: Dict[str, Any], weights: Dict[str, int]) -> Tuple[int, List[str]]:
    max_weight = 0
    hit_names: List[str] = []
    for name in extract_alarm_names(node):
        weight = weights.get(str(name).lower(), 0)
        if weight > 0:
            max_weight = max(max_weight, weight)
            hit_names.append(name)
    return max_weight, hit_names
