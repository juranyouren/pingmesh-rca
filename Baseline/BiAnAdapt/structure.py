"""Observable-only input projection, paper topology summary, and timeline."""

from __future__ import annotations

from collections import deque
from itertools import combinations
import math
from typing import Any

from Baseline.common import parse_timestamp
from Baseline.common.schema import iso_timestamp


EVENT_FIELDS = (
    "event_id", "device_id", "event_type", "event_time", "record_time",
    "severity", "message", "source",
)
ENDPOINT_FIELDS = (
    "source_ip", "sink_ip", "trigger_time", "alarm_time",
    "analysis_from_time", "analysis_to_time", "source_az", "sink_az", "alarm_name",
)


class InputIneligible(ValueError):
    pass


class BudgetExceeded(RuntimeError):
    pass


def _scalar(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value if value is None or isinstance(value, (str, int, float, bool)) else None


def _context_value(value: Any) -> Any:
    """Some real exports encode source/sink endpoints as lists; keep scalar lists."""
    if isinstance(value, list):
        return [item for raw in value if (item := _scalar(raw)) is not None]
    return _scalar(value)


def observable_input(incident: dict[str, Any], message_chars: int) -> dict[str, Any]:
    """Rebuild every nested object: arbitrary extra/label fields cannot pass through."""
    if not isinstance(incident, dict) or not incident.get("case_id"):
        raise InputIneligible("incident requires case_id")
    devices = [{"id": str(d["id"]), "type": _scalar(d.get("type"))}
               for d in incident.get("devices", []) if isinstance(d, dict) and d.get("id")]
    candidates = {d["id"] for d in devices}
    if not candidates or len(candidates) != len(devices):
        raise InputIneligible("candidate devices must be nonempty and unique")
    devices.sort(key=lambda d: d["id"])
    window_in = incident.get("window") or {}
    window = {k: _scalar(window_in.get(k)) for k in ("start", "end", "cutoff", "timezone")}
    window["timezone"] = window["timezone"] or "Asia/Shanghai"
    try:
        start, end, cutoff = [parse_timestamp(window.get(k), window["timezone"])
                              for k in ("start", "end", "cutoff")]
    except (ValueError, TypeError):
        raise InputIneligible("window timezone is invalid or unavailable") from None
    if None in (start, end, cutoff) or not start <= cutoff <= end or start == end:
        raise InputIneligible("window requires start < end and start <= cutoff <= end")
    window.update({k: iso_timestamp(v) for k, v in (("start", start), ("end", end), ("cutoff", cutoff))})
    events, seen, excluded, truncated, invalid_times = [], set(), [], [], []
    for raw in incident.get("events", []):
        if not isinstance(raw, dict):
            raise InputIneligible("event must be an object")
        eid, did = raw.get("event_id"), raw.get("device_id")
        if not eid or not did or str(eid) in seen:
            raise InputIneligible("events require unique IDs and a device ID")
        seen.add(str(eid))
        if str(did) not in candidates:
            excluded.append(str(eid))
            continue
        row = {key: _scalar(raw.get(key)) for key in EVENT_FIELDS}
        row.update(event_id=str(eid), device_id=str(did), source=str(raw.get("source") or "UNK"))
        row["event_type"] = str(row.get("event_type") or "UNK")
        event_ts = parse_timestamp(row.get("event_time"), window["timezone"])
        record_ts = parse_timestamp(row.get("record_time"), window["timezone"])
        if (event_ts is not None and not start <= event_ts <= cutoff) or (record_ts is not None and record_ts > cutoff):
            raise InputIneligible("event is outside the permitted observation window or recorded after cutoff")
        for field, value in (("event_time", event_ts), ("record_time", record_ts)):
            if row.get(field) not in (None, "") and value is None:
                invalid_times.append({"event_id": str(eid), "field": field})
            row[field] = iso_timestamp(value)
        if isinstance(row["message"], str) and len(row["message"]) > message_chars:
            row["message"] = row["message"][:message_chars] + " [message truncated]"
            truncated.append(str(eid))
        for field in ("related_device_ids", "link_endpoints"):
            # These optional lists must already refer to observed candidate IDs.
            values = raw.get(field, [])
            values = values if isinstance(values, list) else []
            row[field] = sorted({str(x) for x in values
                                 if isinstance(x, (str, int)) and str(x) in candidates})
        events.append(row)
    links = []
    for raw in incident.get("physical_links", []):
        u, v = str(raw.get("u", "")), str(raw.get("v", ""))
        if u in candidates and v in candidates and u != v:
            links.append({"u": u, "v": v, "evidence_ids": [str(e) for e in raw.get("evidence_ids", [])
                                                                      if isinstance(e, (str, int))]})
    endpoint_raw = incident.get("endpoint_context") or {}
    endpoint = {k: _context_value(endpoint_raw[k]) for k in ENDPOINT_FIELDS if k in endpoint_raw}
    # Coverage metadata is intentionally not blindly copied; unknown is conservative.
    return {
        "devices": devices, "physical_links": links, "window": window,
        "endpoint_context": endpoint, "events": events,
        "coverage_statement": "Event absence does not establish normality; complete observation is not assumed.",
        "input_audit": {"excluded_unmapped_event_ids": excluded, "message_truncated_event_ids": truncated,
                        "invalid_timestamp_fields_mapped_to_unknown": invalid_times},
    }


def build_timeline(events: list[dict], timezone: str) -> dict[str, Any]:
    rows, unknown, record_only = [], [], []
    groups: dict[float, list[str]] = {}
    for event in events:
        value = dict(event)
        event_ts = parse_timestamp(event.get("event_time"), timezone)
        record_ts = parse_timestamp(event.get("record_time"), timezone)
        value["event_epoch_seconds"] = event_ts
        value["record_epoch_seconds"] = record_ts
        if event_ts is None:
            unknown.append(event["event_id"])
            if record_ts is not None:
                record_only.append(event["event_id"])
        else:
            groups.setdefault(event_ts, []).append(event["event_id"])
        rows.append(value)
    # Unknown event times are not silently replaced by collection/record times.
    rows.sort(key=lambda r: (r["event_epoch_seconds"] is None,
                            r["event_epoch_seconds"] or 0, r["event_id"]))
    return {
        "events": rows, "unknown_event_time_ids": unknown,
        "record_time_only_ids": record_only,
        "simultaneous_groups": [sorted(ids) for _, ids in sorted(groups.items()) if len(ids) > 1],
        "semantics": "event-time ordering; ties do not imply causal order; unknown event times remain unknown",
    }


def paper_topology_summary(devices: list[dict], links: list[dict], suspects: list[str],
                           path_budget: int = 10000) -> dict[str, Any]:
    """§4.2: all shortest paths, remove paths with internal suspect, union remaining.

    Device-group aggregation is disabled because the common v1 input has no verified
    original device-group field. Degree/type/hop are never invented as device groups.
    """
    adjacency = {d["id"]: set() for d in devices}
    provenance: dict[tuple[str, str], set[str]] = {}
    for edge in links:
        u, v = edge["u"], edge["v"]
        adjacency[u].add(v)
        adjacency[v].add(u)
        provenance.setdefault(tuple(sorted((u, v))), set()).update(edge["evidence_ids"])
    suspect_set = set(suspects)
    kept, removed, disconnected, examined = [], [], [], 0
    for start, target in combinations(sorted(suspects), 2):
        distance, parents, queue = {start: 0}, {start: []}, deque([start])
        while queue:
            node = queue.popleft()
            for neighbor in sorted(adjacency[node]):
                next_distance = distance[node] + 1
                if neighbor not in distance:
                    distance[neighbor], parents[neighbor] = next_distance, [node]
                    queue.append(neighbor)
                elif distance[neighbor] == next_distance:
                    parents[neighbor].append(node)
        if target not in distance:
            disconnected.append([start, target])
            continue
        stack = [(target, [target])]
        while stack:
            node, reverse_path = stack.pop()
            if node == start:
                examined += 1
                if examined > path_budget:
                    raise BudgetExceeded("topology all-shortest-path enumeration exceeds configured budget")
                path = list(reversed(reverse_path))
                if suspect_set.intersection(path[1:-1]):
                    removed.append(path)
                else:
                    kept.append(path)
            else:
                for parent in sorted(parents[node], reverse=True):
                    stack.append((parent, reverse_path + [parent]))
    projected = sorted({tuple(sorted((u, v))) for path in kept for u, v in zip(path, path[1:])})
    return {
        "suspects": list(suspects), "retained_shortest_paths": kept,
        "removed_paths_with_internal_suspect": removed, "disconnected_suspect_pairs": disconnected,
        "nodes": sorted(suspect_set.union(*(set(path) for path in kept))),
        "physical_links": [{"u": u, "v": v, "evidence_ids": sorted(provenance[(u, v)])}
                           for u, v in projected],
        "group_aggregation": "disabled: original device-group identity unavailable in common v1 input",
        "semantics": "undirected physical context only; shortest paths are neither measured probes nor propagation predictions",
    }
