from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from Sys.utils.case_utils import get_device_ip
from Sys.utils.io_utils import load_json


TOPOLOGY_SCHEMA_VERSION = "topology-context-v1"
_POD_NUMBER_RE = re.compile(r"(?:^|[^a-z0-9])pod[\s_-]*0*(\d+)", re.IGNORECASE)


def parse_pod_number(value: Any) -> int | None:
    """Extract the numeric suffix immediately following a ``pod`` name token."""

    match = _POD_NUMBER_RE.search(str(value or "").strip())
    return int(match.group(1)) if match else None


def parse_endpoint_values(value: Any) -> List[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except Exception:
            parsed = stripped
        value = parsed
    if isinstance(value, (tuple, list, set)):
        output: List[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in output:
                output.append(text)
        return output
    text = str(value or "").strip()
    return [text] if text else []


def _stable_id(prefix: str, parts: Iterable[Any]) -> str:
    payload = "\x1f".join(str(part or "") for part in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _iter_segments(topo_value: Any):
    if not isinstance(topo_value, list):
        return
    for group_index, raw_group in enumerate(topo_value):
        segments = raw_group if isinstance(raw_group, list) else [raw_group]
        for segment_index, segment in enumerate(segments):
            if isinstance(segment, Mapping):
                yield group_index, segment_index, segment


def _endpoint_anchors(
    endpoints: Sequence[str],
    device_ids: Set[str],
    raw_edges: Sequence[Mapping[str, Any]],
) -> List[str]:
    anchors: Set[str] = set()
    endpoint_set = set(endpoints)
    anchors.update(endpoint_set & device_ids)
    for edge in raw_edges:
        src = str(edge.get("src_ip", "") or "")
        dst = str(edge.get("dst_ip", "") or "")
        if src in endpoint_set and dst in device_ids:
            anchors.add(dst)
        if dst in endpoint_set and src in device_ids:
            anchors.add(src)
    return sorted(anchors)


def build_topology_context(
    topo_value: Any,
    info: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Preserve factual topology context without assigning causal direction."""

    info = info or {}
    nodes: Dict[str, Dict[str, Any]] = {}
    group_segments: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    segment_rows = list(_iter_segments(topo_value) or [])

    for group_index, segment_index, segment in segment_rows:
        group_id = f"GROUP_{group_index + 1:03d}"
        segment_id = f"SEG_{group_index + 1:03d}_{segment_index + 1:03d}"
        group_segments[group_index].append(
            {
                "segment_id": segment_id,
                "path_name": str(segment.get("path_name", "") or ""),
            }
        )
        for raw_node in segment.get("nodes", []) if isinstance(segment.get("nodes"), list) else []:
            if not isinstance(raw_node, Mapping):
                continue
            device_id = str(raw_node.get("mgmt_ip", raw_node.get("ip", "")) or "")
            if not device_id:
                continue
            row = nodes.setdefault(
                device_id,
                {
                    "device_id": device_id,
                    "name": str(raw_node.get("name", "") or ""),
                    "role": str(raw_node.get("role", "") or ""),
                    "pod_number": parse_pod_number(raw_node.get("name")),
                    "group_ids": [],
                    "segment_ids": [],
                },
            )
            if group_id not in row["group_ids"]:
                row["group_ids"].append(group_id)
            if segment_id not in row["segment_ids"]:
                row["segment_ids"].append(segment_id)

    edge_buckets: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    raw_edges: List[Mapping[str, Any]] = []
    for group_index, segment_index, segment in segment_rows:
        group_id = f"GROUP_{group_index + 1:03d}"
        segment_id = f"SEG_{group_index + 1:03d}_{segment_index + 1:03d}"
        links = segment.get("links", [])
        for raw_link in links if isinstance(links, list) else []:
            if not isinstance(raw_link, Mapping):
                continue
            src = str(raw_link.get("src_ip", "") or "")
            dst = str(raw_link.get("dst_ip", "") or "")
            if not src or not dst or src == dst:
                continue
            src_port = str(raw_link.get("src_port_name", "") or "")
            dst_port = str(raw_link.get("dst_port_name", "") or "")
            raw_edges.append(raw_link)
            if (src, src_port) <= (dst, dst_port):
                endpoint_a, port_a, endpoint_b, port_b = src, src_port, dst, dst_port
            else:
                endpoint_a, port_a, endpoint_b, port_b = dst, dst_port, src, src_port
            key = (endpoint_a, port_a, endpoint_b, port_b)
            bucket = edge_buckets.setdefault(
                key,
                {
                    "edge_id": _stable_id("L", key),
                    "endpoint_a": endpoint_a,
                    "endpoint_b": endpoint_b,
                    "endpoint_a_port": port_a,
                    "endpoint_b_port": port_b,
                    "raw_orientations": [],
                    "group_ids": [],
                    "segment_ids": [],
                    "raw_link_keys": [],
                },
            )
            orientation = {"src": src, "dst": dst}
            if orientation not in bucket["raw_orientations"]:
                bucket["raw_orientations"].append(orientation)
            if group_id not in bucket["group_ids"]:
                bucket["group_ids"].append(group_id)
            if segment_id not in bucket["segment_ids"]:
                bucket["segment_ids"].append(segment_id)
            raw_key = str(raw_link.get("key", "") or "")
            if raw_key and raw_key not in bucket["raw_link_keys"]:
                bucket["raw_link_keys"].append(raw_key)

    device_ids = set(nodes)
    source_endpoints = parse_endpoint_values(info.get("source_ip"))
    sink_endpoints = parse_endpoint_values(info.get("sink_ip"))
    topology_groups = [
        {
            "group_id": f"GROUP_{group_index + 1:03d}",
            "segments": group_segments[group_index],
        }
        for group_index in sorted(group_segments)
    ]
    edges = sorted(edge_buckets.values(), key=lambda item: item["edge_id"])
    return {
        "schema_version": TOPOLOGY_SCHEMA_VERSION,
        "source_endpoints": source_endpoints,
        "sink_endpoints": sink_endpoints,
        "source_anchors": _endpoint_anchors(source_endpoints, device_ids, raw_edges),
        "sink_anchors": _endpoint_anchors(sink_endpoints, device_ids, raw_edges),
        "topology_groups": topology_groups,
        "nodes": [nodes[key] for key in sorted(nodes)],
        "edges": edges,
        "diagnostics": {
            "source": "raw_task_topo",
            "device_count": len(nodes),
            "edge_count": len(edges),
            "group_count": len(topology_groups),
        },
    }


def topology_context_from_nodes(
    node_list: Sequence[Mapping[str, Any]],
    info: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a loss-aware fallback context for old preprocessed cases."""

    info = info or {}
    device_rows: Dict[str, Dict[str, Any]] = {}
    raw_pairs: Set[Tuple[str, str]] = set()
    device_ids = {
        get_device_ip(dict(node))
        for node in node_list
        if get_device_ip(dict(node)) not in ("", "unknown")
    }
    for raw_node in node_list:
        node = dict(raw_node)
        device_id = get_device_ip(node)
        if not device_id or device_id == "unknown":
            continue
        device_rows[device_id] = {
            "device_id": device_id,
            "name": str(node.get("name", "") or ""),
            "role": str(node.get("role", "") or ""),
            "pod_number": parse_pod_number(node.get("name")),
            "group_ids": ["FALLBACK"],
            "segment_ids": ["FALLBACK"],
        }
        for neighbor in list(node.get("linked_to", [])) + list(node.get("linked_from", [])):
            neighbor = str(neighbor or "")
            if neighbor and neighbor != device_id:
                raw_pairs.add(tuple(sorted((device_id, neighbor))))

    edges = []
    for endpoint_a, endpoint_b in sorted(raw_pairs):
        edges.append(
            {
                "edge_id": _stable_id("L", (endpoint_a, endpoint_b, "fallback")),
                "endpoint_a": endpoint_a,
                "endpoint_b": endpoint_b,
                "endpoint_a_port": "",
                "endpoint_b_port": "",
                "raw_orientations": [],
                "group_ids": ["FALLBACK"],
                "segment_ids": ["FALLBACK"],
                "raw_link_keys": [],
            }
        )

    source_endpoints = parse_endpoint_values(info.get("source_ip"))
    sink_endpoints = parse_endpoint_values(info.get("sink_ip"))
    pseudo_raw_edges = [
        {"src_ip": edge[0], "dst_ip": edge[1]}
        for edge in raw_pairs
    ]
    return {
        "schema_version": TOPOLOGY_SCHEMA_VERSION,
        "source_endpoints": source_endpoints,
        "sink_endpoints": sink_endpoints,
        "source_anchors": _endpoint_anchors(source_endpoints, device_ids, pseudo_raw_edges),
        "sink_anchors": _endpoint_anchors(sink_endpoints, device_ids, pseudo_raw_edges),
        "topology_groups": [{"group_id": "FALLBACK", "segments": []}],
        "nodes": [device_rows[key] for key in sorted(device_rows)],
        "edges": edges,
        "diagnostics": {
            "source": "processed_nodes_fallback",
            "device_count": len(device_rows),
            "edge_count": len(edges),
            "group_count": 1,
            "missing_fields": ["ports", "raw_link_keys", "raw_orientation"],
        },
    }


def load_topology_context(
    dirpath: str,
    *,
    node_list: Sequence[Mapping[str, Any]] | None = None,
    info: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    path = os.path.join(dirpath, "topology_context.json") if dirpath else ""
    data = load_json(path, default=None) if path else None
    if isinstance(data, dict) and data.get("schema_version") == TOPOLOGY_SCHEMA_VERSION:
        return data
    return topology_context_from_nodes(node_list or [], info or {})


def physical_adjacency(context: Mapping[str, Any]) -> Dict[str, Set[str]]:
    device_ids = {
        str(node.get("device_id"))
        for node in context.get("nodes", [])
        if isinstance(node, Mapping) and node.get("device_id")
    }
    adjacency: Dict[str, Set[str]] = {device_id: set() for device_id in device_ids}
    for edge in context.get("edges", []):
        if not isinstance(edge, Mapping):
            continue
        a = str(edge.get("endpoint_a", "") or "")
        b = str(edge.get("endpoint_b", "") or "")
        if a in device_ids and b in device_ids and a != b:
            adjacency[a].add(b)
            adjacency[b].add(a)
    return adjacency


def topology_edges_between(
    context: Mapping[str, Any],
    a: str,
    b: str,
) -> List[Dict[str, Any]]:
    pair = {a, b}
    rows = []
    for raw in context.get("edges", []):
        if not isinstance(raw, Mapping):
            continue
        if {str(raw.get("endpoint_a", "")), str(raw.get("endpoint_b", ""))} == pair:
            rows.append(dict(raw))
    return sorted(rows, key=lambda item: str(item.get("edge_id", "")))
