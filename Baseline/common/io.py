"""Whitelist conversion. This module never loads a label file implicitly."""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from .schema import SCHEMA_VERSION, input_fingerprint, iso_timestamp, parse_timestamp, stable_hash, validate_incident

CONTEXT_FIELDS = ("source_ip", "sink_ip", "source_az", "sink_az", "alarm_name", "alarm_time")


def read_json(path):
    with Path(path).open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def dump_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    target.write_text(text, encoding="utf-8")


def _first(row, keys):
    return next((row[key] for key in keys if row.get(key) not in (None, "", [])), None)


def _clock_value(row, key):
    value = row.get(key)
    # Exported occur_time=0 is an unset sentinel in these modern alarm exports.
    # Explicit canonical event_time/record_time may legitimately be epoch zero.
    if key in {"alarm_time", "occur_time", "confirm_time", "insert_time"} and value in (0, "0"):
        return None
    return value


def _first_clock(row, keys):
    return next((_clock_value(row, k) for k in keys if _clock_value(row, k) not in (None, "")), None)


def _observation_value(value):
    """Retain scalar measurements or scalar lists, never nested diagnostic objects."""
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, list):
        return [_observation_value(x) for x in value if not isinstance(x, (dict, list))]
    return None


def _coverage(value, timezone):
    if not isinstance(value, dict):
        return None
    result = {"complete": value.get("complete") is True}
    intervals = []
    for row in value.get("intervals", []):
        item = {key: iso_timestamp(row.get(key), timezone) for key in ("start", "end")}
        if any(v is None for v in item.values()):
            raise ValueError("Coverage interval needs valid start and end")
        if "device_ids" in row:
            if not isinstance(row["device_ids"], list) or any(not isinstance(x, str) for x in row["device_ids"]):
                raise ValueError("Coverage device_ids must be a string list")
            item["device_ids"] = sorted(set(row["device_ids"]))
        intervals.append(item)
    if intervals:
        result["intervals"] = intervals
    return result


def _list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [value]
        except ValueError:
            return [value]
    return []


def _segments(value):
    for group in value if isinstance(value, list) else []:
        for segment in group if isinstance(group, list) else [group]:
            if isinstance(segment, dict):
                yield segment


def _window(info, before_seconds, after_seconds, timezone):
    trigger = parse_timestamp(_clock_value(info, "alarm_time"), timezone)
    if trigger is None:
        raise ValueError("Missing/invalid trigger alarm_time; refusing label-derived or guessed window")
    if not all(math.isfinite(x) for x in (before_seconds, after_seconds)) or before_seconds < 0 or after_seconds < 0 or before_seconds + after_seconds <= 0:
        raise ValueError("Window durations must be nonnegative with positive total")
    return {"start": iso_timestamp(trigger - before_seconds), "end": iso_timestamp(trigger + after_seconds),
            "cutoff": iso_timestamp(trigger + after_seconds), "timezone": timezone}


def _build(case_id, info, nodes, links, event_rows, *, before_seconds=300, after_seconds=300, timezone="Asia/Shanghai", window=None, group_id=None, group_verified=False, coverage=None):
    devices = {}
    aliases = {}
    for row in nodes:
        identifier = _first(row, ("id", "mgmt_ip", "ip", "device_id"))
        if identifier is None:
            continue
        identifier = str(identifier)
        device_type = _first(row, ("devicetype", "role", "type"))
        devices.setdefault(identifier, {"id": identifier, "type": str(device_type) if isinstance(device_type, (str, int)) else "UNK"})
        aliases[identifier] = identifier
        if row.get("name"):
            name = str(row["name"])
            if name in aliases and aliases[name] != identifier:
                raise ValueError("Ambiguous device name alias")
            aliases[name] = identifier
    physical = {}
    for row in links:
        u = str(_first(row, ("u", "src_ip", "endpoint_a")) or "")
        v = str(_first(row, ("v", "dst_ip", "endpoint_b")) or "")
        if not u or not v or u == v:
            continue
        u, v = sorted((aliases.get(u, u), aliases.get(v, v)))
        for identifier in (u, v):
            devices.setdefault(identifier, {"id": identifier, "type": "UNK"})
            aliases[identifier] = identifier
        evidence = row.get("evidence_ids") or [row.get("edge_id") or "phy-" + stable_hash([u, v, row.get("src_port_name"), row.get("dst_port_name")])[:16]]
        bucket = physical.setdefault((u, v), {"u": u, "v": v, "evidence_ids": []})
        bucket["evidence_ids"] = sorted(set(bucket["evidence_ids"]) | {str(x) for x in evidence})
    selected_window = window or _window(info, before_seconds, after_seconds, timezone)
    window = {key: iso_timestamp(selected_window.get(key), timezone) for key in ("start", "end", "cutoff")}
    window["timezone"] = selected_window.get("timezone", timezone)
    start = parse_timestamp(window["start"])
    cutoff = parse_timestamp(window["cutoff"])
    if start is None or cutoff is None:
        raise ValueError("Invalid window")
    excluded = Counter()
    time_diagnostics = Counter()
    events = {}
    for source, owner, row in event_rows:
        if not isinstance(row, dict):
            excluded["invalid_record"] += 1
            continue
        identifier = str(owner or _first(row, ("device_id", "alarm_ip_ad", "mgmt_ip", "device_ip", "alarm_ip_name")) or "")
        identifier = aliases.get(identifier, identifier)
        if identifier not in devices:
            excluded["unmapped_device"] += 1
            continue
        raw_t = _first_clock(row, ("event_time", "alarm_time", "occur_time", "time", "confirm_time", "timestamp"))
        raw_record = _first_clock(row, ("record_time", "ingest_time", "insert_time"))
        event_t = parse_timestamp(raw_t, timezone)
        record_t = parse_timestamp(raw_record, timezone)
        time_candidates = {k: parse_timestamp(_clock_value(row, k), timezone) for k in ("alarm_time", "occur_time") if row.get(k) is not None}
        if len(set(v for v in time_candidates.values() if v is not None)) > 1:
            time_diagnostics["alarm_vs_occur_time_conflicts"] += 1
        for k in ("alarm_time", "occur_time", "confirm_time", "insert_time"):
            if row.get(k) in (0, "0"):
                time_diagnostics[k + "_zero_sentinel"] += 1
        if event_t is not None and not start <= event_t <= cutoff:
            excluded["event_outside_window"] += 1
            continue
        if record_t is not None and record_t > cutoff:
            excluded["recorded_after_cutoff"] += 1
            continue
        event_type = str(_first(row, ("event_type", "alarm_name", "name", "event_name", "log_type")) or "UNK")
        event = {"device_id": identifier, "event_type": event_type, "event_time": iso_timestamp(event_t),
                 "record_time": iso_timestamp(record_t), "source": str(source).lower(),
                 "severity": _observation_value(_first(row, ("severity", "alarm_level", "level"))),
                 "message": _observation_value(_first(row, ("message", "description", "content", "alarm_description"))),
                 "observed_fields": sorted(key for key, val in {"event_time": event_t, "record_time": record_t,
                      "severity": _first(row, ("severity", "alarm_level", "level")),
                      "message": _first(row, ("message", "description", "content", "alarm_description"))}.items() if val is not None)}
        for field in ("related_device_ids", "link_endpoints"):
            values = row.get(field, [])
            event[field] = [aliases.get(str(x), str(x)) for x in values] if isinstance(values, list) else []
        # Only explicit peer fields are forwarded; no parsing predictions from text.
        peer = _first(row, ("peer_device_id", "peer_ip", "remote_ip"))
        if peer is not None:
            event["related_device_ids"].append(aliases.get(str(peer), str(peer)))
        event["related_device_ids"] = sorted(set(event["related_device_ids"]))
        explicit_id = row.get("event_id")
        event["event_id"] = str(explicit_id) if explicit_id else f"{source}:{identifier}:" + str(row.get("alarm_id") or stable_hash(event)[:20])
        key = event["event_id"]
        if key in events:
            if events[key] != event:
                raise ValueError(f"Conflicting records share event_id {key}; resolve source identity")
            excluded["exact_duplicate"] += 1
        events[key] = event
    context = {key: _observation_value(info[key]) for key in CONTEXT_FIELDS if key in info}
    result = {"schema_version": SCHEMA_VERSION, "case_id": str(case_id), "group_id": str(group_id or f"unverified:{case_id}"),
              "group_verified": group_verified is True, "window": window,
              "devices": sorted(devices.values(), key=lambda x: x["id"]),
              "physical_links": sorted(physical.values(), key=lambda x: (x["u"], x["v"])),
              "events": sorted(events.values(), key=lambda x: (x["event_time"] or "~", x["event_id"])),
              "endpoint_context": context, "observation_coverage": _coverage(coverage, timezone),
              "input_diagnostics": {"excluded_events": dict(excluded), "window_policy": "fixed_trigger_window" if not info.get("_normalized") else "explicit_window",
                                    "time_fields": dict(time_diagnostics),
                                    "event_time_priority": ["event_time", "alarm_time", "occur_time", "time", "confirm_time", "timestamp"],
                                    "raw_alarm_time_semantics": "exported alarm_time preferred; verify source semantics before temporal performance claims"}}
    validate_incident(result)
    result["input_hash"] = input_fingerprint(result)
    return result


def normalize_incident(data):
    # Re-whitelist even an already normalized record to prevent a callers'
    # extra labels or proprietary rankings from entering a prompt/model.
    info = {**data.get("endpoint_context", {}), "_normalized": True}
    return _build(data["case_id"], info, data.get("devices", []), data.get("physical_links", []),
                  [(e.get("source", "alarm"), e.get("device_id"), e) for e in data.get("events", [])],
                  window=data.get("window"), timezone=data.get("window", {}).get("timezone", "Asia/Shanghai"),
                  group_id=data.get("group_id"), group_verified=data.get("group_verified", False), coverage=data.get("observation_coverage"))


def from_raw(data, *, case_id=None, **kwargs):
    full = data.get("full_link", data)
    info = full.get("task_info", {})
    case_id = case_id or info.get("task_id") or info.get("alarm_id")
    if not case_id:
        raise ValueError("Raw incident has no task identifier")
    segments = list(_segments(full.get("task_topo", {}).get("value")))
    nodes = [row for segment in segments for row in segment.get("nodes", []) if isinstance(row, dict)]
    links = [row for segment in segments for row in segment.get("links", []) if isinstance(row, dict)]
    logs = full.get("log_list", {})
    logs = logs.get("list", logs.get("data", [])) if isinstance(logs, dict) else logs
    rows = [("alarm", None, e) for e in full.get("alarm_list", [])]
    rows += [("log", None, e) for e in logs] if isinstance(logs, list) else []
    result = _build(case_id, info, nodes, links, rows, **kwargs)
    result["input_diagnostics"].update({"raw_trace_records": len(full.get("task_trace", [])), "trace_used": False,
                                      "cross_used": False, "precomputed_scores_used": False,
                                      "raw_log_rows": len(logs) if isinstance(logs, list) else 0})
    return result


def from_processed(path, **kwargs):
    path = Path(path)
    info = read_json(path / "info.json")
    files = sorted(path.glob("*全链路*.json")) or sorted(path.glob("nodes.json"))
    if not files:
        raise ValueError(f"No processed node file in {path}")
    nodes = read_json(files[0])
    if isinstance(nodes, dict) and "full_link" in nodes:
        raise ValueError("Raw full_link wrapper cannot be treated as processed nodes")
    nodes = list(nodes.values()) if isinstance(nodes, dict) else nodes
    context_path = path / "topology_context.json"
    if not context_path.exists():
        raise ValueError("Processed inputs require a topology_context.json sourced from raw topology")
    topology = read_json(context_path)
    if topology.get("diagnostics", {}).get("source") != "raw_task_topo":
        raise ValueError("Topology provenance must be raw_task_topo; inferred paths are not accepted")
    rows = []
    for node in nodes:
        owner = _first(node, ("mgmt_ip", "ip", "device_id"))
        for key, source in (("alarms", "alarm"), ("logs", "log")):
            rows.extend((source, owner, event) for event in node.get(key, []) if isinstance(event, dict))
    # Include silent/isolated devices in the verified raw topology, even when
    # the processed event table omitted them.
    candidate_nodes = nodes + [n for n in topology.get("nodes", []) if isinstance(n, dict)]
    return _build(path.name, info, candidate_nodes, topology.get("edges", []), rows, **kwargs)


def load_incidents(path, *, before_seconds=300, after_seconds=300, timezone="Asia/Shanghai"):
    path = Path(path)
    options = dict(before_seconds=before_seconds, after_seconds=after_seconds, timezone=timezone)
    if path.is_dir():
        folders = sorted({p.parent for p in path.rglob("info.json")})
        if folders:
            cases = [from_processed(folder, **options) for folder in folders]
        else:
            files = sorted(path.rglob("*pingmesh*.json"))
            cases = [case for file in files for case in load_incidents(file, **options)]
    elif path.suffix == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        cases = [normalize_incident(row) for row in rows]
    else:
        data = read_json(path)
        if isinstance(data, dict) and ("full_link" in data or "task_topo" in data):
            cases = [from_raw(data, **options)]
        else:
            rows = data.get("incidents", [data]) if isinstance(data, dict) else data
            cases = [normalize_incident(row) for row in rows]
    ids = [case["case_id"] for case in cases]
    if not cases:
        raise ValueError(f"No supported incidents found in {path}")
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate case_id; reconcile repeated exports before running")
    return sorted(cases, key=lambda x: x["case_id"])
