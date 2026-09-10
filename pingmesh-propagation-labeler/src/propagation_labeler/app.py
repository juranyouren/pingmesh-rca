#!/usr/bin/env python3
"""Local, dependency-free UI for labeling Pingmesh propagation graphs.

The server only binds to localhost by default.  It reads case inputs from the
node dataset and atomically writes evaluation-compatible labels to:

    <labels-root>/<case-id>/propagation_label.json

Inference results are deliberately hidden unless ``--hypothesis-view`` (or its
legacy alias ``--prediction-overlay``) is explicitly supplied.  This keeps the
default workflow suitable for blind ground-truth annotation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import threading
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import parse_qs, quote, urlparse


TOOL_VERSION = "2.2.0"
LABEL_SCHEMA_VERSION = "heterogeneous-propagation-label-v1"
LABEL_FILENAME = "propagation_label.json"
MAX_REQUEST_BYTES = 4 * 1024 * 1024

ROOT_SCOPES = {"device", "inter_device_link", "multiple_devices", "uncertain"}
DIAGNOSABILITY = {
    "fully_observed",
    "partially_observed",
    "unidentifiable",
    "out_of_scope",
}
CONFIDENCE = {"high", "medium", "low"}
NODE_ROLES = {"root", "root_endpoint", "propagation", "affected", "uncertain"}
NODE_MEMBERSHIPS = {"definite", "possible", "excluded", "unknown"}
DD_EDGE_STATES = {"definite", "possible", "explicit_no_direct", "unknown"}
EVENT_ROLES = {
    "initiating",
    "intermediate",
    "supporting",
    "concurrent",
    "irrelevant",
    "uncertain",
}
EVENT_STATES = {"definite", "possible", "excluded", "unknown"}
EE_EDGE_STATES = {"definite", "possible", "explicit_no_dependency", "unknown"}
EE_RELATIONS = {
    "dependency_or_evolution",
    "physical_to_protocol",
    "protocol_to_routing",
    "concurrent",
    "unrelated",
    "unknown",
}
EDGE_RELATIONS = {
    "physical_link",
    "control_plane",
    "routing_convergence",
    "inferred_impact",
    "unknown",
}
DIRECTION_STATUSES = {"confirmed", "likely", "unresolved"}
ANNOTATION_STATUSES = {"draft", "completed"}
IDENTIFIABILITY = {
    "identifiable",
    "partially_identifiable",
    "unidentifiable",
    "out_of_scope",
}
ANNOTATION_SCOPE_KEYS = {
    "device_nodes",
    "dd_candidate_pairs",
    "priority_ee_pairs",
    "all_ee_candidate_pairs",
}


class LabelerError(ValueError):
    """A user-facing input or dataset error."""


class RevisionConflict(LabelerError):
    """Raised when another browser tab changed a label after it was loaded."""


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as exc:
        raise LabelerError(f"JSON 读取失败: {path}: {exc}") from exc


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _stable_id(prefix: str, *parts: Any) -> str:
    value = "\x1f".join(str(part or "") for part in parts)
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _revision(path: Path) -> str:
    if not path.exists():
        return "new"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:20]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_endpoints(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            value = json.loads(stripped)
        except (TypeError, json.JSONDecodeError):
            value = stripped
    if isinstance(value, (list, tuple, set)):
        return list(dict.fromkeys(_text(item) for item in value if _text(item)))
    return [_text(value)] if _text(value) else []


_POD_NUMBER_RE = re.compile(r"(?:^|[^a-z0-9])pod[\s_-]*0*(\d+)", re.IGNORECASE)


def _parse_pod_number(value: Any) -> int | None:
    """Extract the numeric suffix immediately following a ``pod`` token."""

    match = _POD_NUMBER_RE.search(_text(value))
    if not match:
        return None
    return int(match.group(1))


def _canonical_topology_role(role: Any, name: Any = "") -> str:
    """Return a conservative Clos role without overriding an explicit role."""

    explicit = _text(role).upper()
    aliases = {
        "TOR": "LEAF",
        "TOP_OF_RACK": "LEAF",
        "TOP-OF-RACK": "LEAF",
    }
    if explicit:
        return aliases.get(explicit, explicit)
    lowered = _text(name).lower()
    if re.search(r"(?:^|[-_])(tor|leaf)(?:[-_]|$)", lowered):
        return "LEAF"
    if re.search(r"(?:^|[-_])(core|csw)(?:[-_]|$)", lowered):
        return "CORE"
    if re.search(r"(?:^|[-_])spine(?:[-_]|$)", lowered):
        return "SPINE"
    return "UNKNOWN"


def _topology_distances(
    adjacency: Mapping[str, set[str]], seeds: Sequence[str]
) -> dict[str, int]:
    distances: dict[str, int] = {}
    queue: list[str] = []
    for seed in seeds:
        if seed in adjacency and seed not in distances:
            distances[seed] = 0
            queue.append(seed)
    for current in queue:
        next_distance = distances[current] + 1
        for neighbor in sorted(adjacency.get(current, set())):
            if neighbor not in distances:
                distances[neighbor] = next_distance
                queue.append(neighbor)
    return distances


def _core_forwarding_overlay(
    display_nodes: list[dict[str, Any]],
    display_edges: list[dict[str, Any]],
    *,
    source_anchors: Sequence[str],
    sink_anchors: Sequence[str],
) -> dict[str, Any]:
    """Identify parallel CORE forwarding stages and conservative completions.

    Nodes at the same source-oriented CORE distance form one parallel stage.
    Only observed links between consecutive stages are retained. Missing
    cartesian pairs stay unknown: layer structure never authorizes fabric-edge
    completion. Disconnected source/sink CORE components are reported as a gap
    without creating a virtual bridge or any unobserved CORE--CORE edge.
    """

    by_id = {
        _text(item.get("device_id")): item
        for item in display_nodes
        if _text(item.get("device_id"))
    }
    adjacency: dict[str, set[str]] = {device_id: set() for device_id in by_id}
    for edge in display_edges:
        endpoint_a = _text(edge.get("endpoint_a"))
        endpoint_b = _text(edge.get("endpoint_b"))
        if endpoint_a in adjacency and endpoint_b in adjacency and endpoint_a != endpoint_b:
            adjacency[endpoint_a].add(endpoint_b)
            adjacency[endpoint_b].add(endpoint_a)

    core_ids = sorted(
        device_id
        for device_id, item in by_id.items()
        if item.get("topology_role") == "CORE" and not item.get("is_inferred")
    )
    if not core_ids:
        return {
            "layers": [],
            "connections": [],
            "virtual_node_count": 0,
            "inferred_edge_count": 0,
            "status": "not_available",
        }

    source_distances = _topology_distances(adjacency, source_anchors)
    sink_distances = _topology_distances(adjacency, sink_anchors)
    shared_core_ids = [
        device_id
        for device_id in core_ids
        if device_id in source_distances and device_id in sink_distances
    ]
    stage_groups: list[list[str]] = []
    if shared_core_ids:
        by_distance: dict[int, list[str]] = {}
        for device_id in shared_core_ids:
            by_distance.setdefault(source_distances[device_id], []).append(device_id)
        stage_groups = [sorted(by_distance[value]) for value in sorted(by_distance)]
        status = "connected_observed_only"
    else:
        source_core_ids = [device_id for device_id in core_ids if device_id in source_distances]
        sink_core_ids = [device_id for device_id in core_ids if device_id in sink_distances]
        source_groups: dict[int, list[str]] = {}
        sink_groups: dict[int, list[str]] = {}
        for device_id in source_core_ids:
            source_groups.setdefault(source_distances[device_id], []).append(device_id)
        for device_id in sink_core_ids:
            sink_groups.setdefault(sink_distances[device_id], []).append(device_id)
        stage_groups.extend(
            sorted(source_groups[value]) for value in sorted(source_groups)
        )
        stage_groups.extend(
            sorted(sink_groups[value]) for value in sorted(sink_groups, reverse=True)
        )
        status = "disconnected_observed_only" if source_groups and sink_groups else "one_sided"

    if not stage_groups:
        return {
            "layers": [],
            "connections": [],
            "virtual_node_count": 0,
            "inferred_edge_count": 0,
            "status": "not_orientable",
        }

    layers: list[dict[str, Any]] = []
    stage_index_by_device: dict[str, int] = {}
    final_index = len(stage_groups) - 1
    for index, device_ids in enumerate(stage_groups):
        if final_index == 0:
            layer_role = "shared_core"
        elif index == 0:
            layer_role = "source_core"
        elif index == final_index:
            layer_role = "sink_core"
        else:
            layer_role = "transit_core"
        layer_id = _stable_id("CORE_STAGE", *device_ids)
        for device_id in device_ids:
            stage_index_by_device[device_id] = index
            node = by_id[device_id]
            node["core_forwarding_layer_index"] = index
            node["core_forwarding_layer_id"] = layer_id
            node["core_forwarding_layer_role"] = layer_role
        layers.append(
            {
                "layer_id": layer_id,
                "layer_index": index,
                "layer_role": layer_role,
                "device_ids": device_ids,
                "device_count": len(device_ids),
                "is_inferred_stage": False,
            }
        )

    observed_pair_edges: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for edge in display_edges:
        if edge.get("is_inferred"):
            continue
        endpoint_a = _text(edge.get("endpoint_a"))
        endpoint_b = _text(edge.get("endpoint_b"))
        if endpoint_a in stage_index_by_device and endpoint_b in stage_index_by_device:
            observed_pair_edges.setdefault(tuple(sorted((endpoint_a, endpoint_b))), []).append(edge)

    connections: list[dict[str, Any]] = []
    inferred_edge_count = 0
    for index in range(len(stage_groups) - 1):
        left_ids = stage_groups[index]
        right_ids = stage_groups[index + 1]
        observed_pairs: list[tuple[str, str]] = []
        observed_edge_ids: list[str] = []
        for endpoint_a in left_ids:
            for endpoint_b in right_ids:
                pair = tuple(sorted((endpoint_a, endpoint_b)))
                rows = observed_pair_edges.get(pair, [])
                if rows:
                    observed_pairs.append((endpoint_a, endpoint_b))
                    observed_edge_ids.extend(
                        _text(row.get("edge_id"))
                        for row in rows
                        if _text(row.get("edge_id"))
                    )
        covered_left = {endpoint_a for endpoint_a, _ in observed_pairs}
        covered_right = {endpoint_b for _, endpoint_b in observed_pairs}
        endpoint_coverage = (
            bool(observed_pairs)
            and covered_left == set(left_ids)
            and covered_right == set(right_ids)
        )
        inferred_pairs: list[tuple[str, str]] = []
        if observed_pairs:
            possible_pair_count = len(left_ids) * len(right_ids)
            connections.append(
                {
                    "from_layer_id": layers[index]["layer_id"],
                    "to_layer_id": layers[index + 1]["layer_id"],
                    "from_layer_index": index,
                    "to_layer_index": index + 1,
                    "observed_pairs": [list(pair) for pair in observed_pairs],
                    "inferred_candidate_pairs": [list(pair) for pair in inferred_pairs],
                    "observed_edge_ids": sorted(set(observed_edge_ids)),
                    "possible_pair_count": possible_pair_count,
                    "observed_pair_count": len(observed_pairs),
                    "inferred_candidate_pair_count": len(inferred_pairs),
                    "observed_density": (
                        round(len(observed_pairs) / possible_pair_count, 6)
                        if possible_pair_count
                        else 0.0
                    ),
                    "endpoint_coverage": endpoint_coverage,
                }
            )

    return {
        "layers": layers,
        "connections": connections,
        "virtual_node_count": 0,
        "inferred_edge_count": inferred_edge_count,
        "status": status,
    }


def _topology_display_overlay(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    *,
    info: Mapping[str, Any] | None = None,
    source_anchors: Sequence[str] = (),
    sink_anchors: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a non-authoritative display overlay for collapsed Clos paths.

    Raw topology nodes and edges remain the only labelable physical objects. A
    direct LEAF--CORE observation is treated as a projection that may hide one
    or more SPINE devices. Connected LEAF--CORE components are expanded through
    one synthetic "SPINE set" node so annotators can see the likely layer while
    the exact hidden device count and identities remain explicitly unknown.
    """

    info = info or {}
    observed_nodes = [dict(item) for item in nodes]
    observed_edges = [dict(item) for item in edges]
    by_id = {
        _text(item.get("device_id")): item
        for item in observed_nodes
        if _text(item.get("device_id"))
    }
    for item in observed_nodes:
        item["topology_role"] = _canonical_topology_role(
            item.get("topology_role", item.get("role")), item.get("name")
        )
        pod_number = _parse_pod_number(item.get("name"))
        item["pod_number"] = pod_number
        item["pod_source"] = "device_name" if pod_number is not None else "unknown"
        item["is_inferred"] = False
        item["annotation_selectable"] = True

    pair_edges: dict[tuple[str, str], list[dict[str, Any]]] = {}
    leaf_core_pairs: set[tuple[str, str]] = set()
    projection_adjacency: dict[str, set[str]] = {}
    for edge in observed_edges:
        endpoint_a = _text(edge.get("endpoint_a"))
        endpoint_b = _text(edge.get("endpoint_b"))
        if not endpoint_a or not endpoint_b or endpoint_a == endpoint_b:
            continue
        key = tuple(sorted((endpoint_a, endpoint_b)))
        pair_edges.setdefault(key, []).append(edge)
        role_a = by_id.get(endpoint_a, {}).get("topology_role")
        role_b = by_id.get(endpoint_b, {}).get("topology_role")
        if {role_a, role_b} != {"LEAF", "CORE"}:
            continue
        leaf_core_pairs.add(key)
        projection_adjacency.setdefault(endpoint_a, set()).add(endpoint_b)
        projection_adjacency.setdefault(endpoint_b, set()).add(endpoint_a)

    # Connected components only use the LEAF--CORE projection. CORE--CORE links
    # therefore do not accidentally merge different pods.
    components: list[set[str]] = []
    remaining = set(projection_adjacency)
    while remaining:
        start = min(remaining)
        component: set[str] = set()
        queue = [start]
        while queue:
            current = queue.pop()
            if current in component:
                continue
            component.add(current)
            queue.extend(sorted(projection_adjacency.get(current, set()) - component))
        remaining -= component
        components.append(component)

    source_anchor_set = set(source_anchors)
    sink_anchor_set = set(sink_anchors)
    source_pod = _text(info.get("source_pod"))
    sink_pod = _text(info.get("sink_pod"))
    display_nodes = list(observed_nodes)
    display_edges = [
        {**edge, "is_inferred": False, "annotation_selectable": True}
        for edge in observed_edges
        if tuple(sorted((_text(edge.get("endpoint_a")), _text(edge.get("endpoint_b")))))
        not in leaf_core_pairs
    ]
    reconstructed_paths: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []

    for component in sorted(components, key=lambda values: tuple(sorted(values))):
        leaves = sorted(
            device_id
            for device_id in component
            if by_id.get(device_id, {}).get("topology_role") == "LEAF"
        )
        cores = sorted(component - set(leaves))
        if not leaves or not cores:
            continue
        pod_numbers = {
            by_id[device_id].get("pod_number")
            for device_id in component
            if by_id[device_id].get("pod_number") is not None
        }
        pod_number = next(iter(pod_numbers)) if len(pod_numbers) == 1 else None
        context_labels = []
        if set(leaves) & source_anchor_set:
            context_labels.append(source_pod or "source")
        if set(leaves) & sink_anchor_set:
            context_labels.append(sink_pod or "sink")
        context_label = " / ".join(dict.fromkeys(context_labels))
        virtual_id = _stable_id("VSPINE", *sorted(component))
        pod_label = f"Pod {pod_number}" if pod_number is not None else context_label
        virtual_name = f"隐藏 SPINE 集合（{pod_label}）" if pod_label else "隐藏 SPINE 集合"
        display_nodes.append(
            {
                "device_id": virtual_id,
                "name": virtual_name,
                "topology_role": "SPINE",
                "group_ids": [],
                "segment_ids": [],
                "evidence_ids": [],
                "alarm_count": 0,
                "log_count": 0,
                "is_source_anchor": False,
                "is_sink_anchor": False,
                "is_source_endpoint": False,
                "is_sink_endpoint": False,
                "pod_number": pod_number,
                "pod_source": "device_name_component" if pod_number is not None else "endpoint_context",
                "is_inferred": True,
                "annotation_selectable": False,
                "inference_kind": "collapsed_spine_set",
                "inference_confidence": "structural",
                "inference_note": (
                    "由观测到的 LEAF—CORE 直连按 Clos 层级展开；代表一个或多个被省略的 "
                    "SPINE，真实设备数量、名称和管理 IP 未知。"
                ),
            }
        )

        for endpoint in [*leaves, *cores]:
            supporting_edge_ids = sorted(
                {
                    _text(edge.get("edge_id"))
                    for other in projection_adjacency.get(endpoint, set()) & component
                    for edge in pair_edges.get(tuple(sorted((endpoint, other))), [])
                    if _text(edge.get("edge_id"))
                }
            )
            display_edges.append(
                {
                    "edge_id": _stable_id("VL", virtual_id, endpoint),
                    "endpoint_a": endpoint,
                    "endpoint_b": virtual_id,
                    "endpoint_a_port": "",
                    "endpoint_b_port": "",
                    "group_ids": [],
                    "segment_ids": [],
                    "is_inferred": True,
                    "annotation_selectable": False,
                    "inference_kind": "collapsed_leaf_core_projection",
                    "raw_projection_edge_ids": supporting_edge_ids,
                }
            )

        component_pair_count = 0
        for leaf in leaves:
            for core in cores:
                key = tuple(sorted((leaf, core)))
                if key not in leaf_core_pairs:
                    continue
                raw_edge_ids = sorted(
                    _text(edge.get("edge_id"))
                    for edge in pair_edges.get(key, [])
                    if _text(edge.get("edge_id"))
                )
                reconstructed_paths.append(
                    {
                        "endpoint_a": leaf,
                        "endpoint_b": core,
                        "raw_edge_ids": raw_edge_ids,
                        "display_path": [leaf, virtual_id, core],
                        "inference_kind": "collapsed_leaf_core_projection",
                    }
                )
                component_pair_count += 1
                if pod_number is not None:
                    for device_id in (leaf, core):
                        if by_id[device_id].get("pod_number") is None:
                            by_id[device_id]["pod_number"] = pod_number
                            by_id[device_id]["pod_source"] = "leaf_core_component"

        component_rows.append(
            {
                "virtual_node_id": virtual_id,
                "leaf_device_ids": leaves,
                "core_device_ids": cores,
                "pod_number": pod_number,
                "pod_context": context_label,
                "projected_pair_count": component_pair_count,
                "exact_hidden_device_count_known": False,
            }
        )

    core_forwarding = _core_forwarding_overlay(
        display_nodes,
        display_edges,
        source_anchors=source_anchors,
        sink_anchors=sink_anchors,
    )
    inferred_structure = bool(component_rows) or bool(
        core_forwarding["virtual_node_count"] or core_forwarding["inferred_edge_count"]
    )
    incomplete_core_fabric = core_forwarding["status"] == "disconnected_observed_only"
    return {
        "nodes": observed_nodes,
        "display_nodes": sorted(display_nodes, key=lambda item: _text(item.get("device_id"))),
        "display_edges": sorted(display_edges, key=lambda item: _text(item.get("edge_id"))),
        "reconstructed_paths": reconstructed_paths,
        "core_forwarding_layers": core_forwarding["layers"],
        "core_layer_connections": core_forwarding["connections"],
        "reconstruction": {
            "status": (
                "partial_structural_reconstruction"
                if inferred_structure
                else "incomplete_observed_topology"
                if incomplete_core_fabric
                else "not_needed"
            ),
            "method": "clos_layered_fabric_v2",
            "virtual_node_count": len(component_rows) + core_forwarding["virtual_node_count"],
            "projected_raw_pair_count": len(reconstructed_paths),
            "inferred_core_edge_count": core_forwarding["inferred_edge_count"],
            "core_forwarding_status": core_forwarding["status"],
            "exact_hidden_device_count_known": (
                False if inferred_structure or incomplete_core_fabric else None
            ),
            "components": component_rows,
            "core_forwarding_layers": core_forwarding["layers"],
            "core_layer_connections": core_forwarding["connections"],
            "warning": (
                "恢复层仅用于帮助理解和标注；虚拟节点不是原始设备，DD 边仍必须对应原始 task_topo。"
                if inferred_structure
                else "源侧与目的侧 CORE 子图在观测拓扑中断开；缺失连接保持未知，未生成推测 CORE 边。"
                if incomplete_core_fabric
                else ""
            ),
        },
    }


def _extract_device_ids(value: Any) -> list[str]:
    """Extract one or more device IDs from supported root-label shapes."""

    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Mapping):
        for key in ("ip", "mgmt_ip", "device_ip", "device_id"):
            device_id = _text(value.get(key))
            if device_id:
                return [device_id]
        return []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            for device_id in _extract_device_ids(item):
                if device_id not in result:
                    result.append(device_id)
        return result
    return []


def _source_root_devices(case_dir: Path) -> list[str]:
    """Read root devices from the case's v2 or legacy ground-truth label."""

    strict = _read_json(case_dir / "label_v2.json", default=None)
    if isinstance(strict, Mapping):
        result: list[str] = []
        for key in (
            "primary_root_cause",
            "primary_root_causes",
            "secondary_root_causes",
            "root_causes",
        ):
            for device_id in _extract_device_ids(strict.get(key)):
                if device_id not in result:
                    result.append(device_id)
        if result:
            return result

    legacy = _read_json(case_dir / "label.json", default=None)
    if not isinstance(legacy, list):
        return []
    result = []
    rows = sorted(
        (item for item in legacy if isinstance(item, Mapping)),
        key=lambda item: item.get("ranking", 999),
    )
    for row in rows:
        for device_id in _extract_device_ids(row.get("abnormal_node", [])):
            if device_id not in result:
                result.append(device_id)
    return result


def _timestamp_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _case_graph_file(case_dir: Path) -> Path | None:
    candidates = sorted(case_dir.glob("*.json"))
    for path in candidates:
        if "pingmesh" in path.name.lower() and (
            "全链路" in path.name or "鍕ㄩ摼路" in path.name
        ):
            return path
    nodes_path = case_dir / "nodes.json"
    return nodes_path if nodes_path.exists() else None


def discover_cases(data_root: Path) -> dict[str, Path]:
    """Discover nested case folders and reject ambiguous duplicate case IDs."""

    data_root = data_root.resolve()
    if not data_root.is_dir():
        raise LabelerError(f"数据目录不存在: {data_root}")
    found: dict[str, Path] = {}
    duplicates: dict[str, list[Path]] = {}
    for dirpath, dirnames, filenames in os.walk(data_root):
        dirnames.sort()
        if "info.json" not in filenames:
            continue
        candidate = Path(dirpath).resolve()
        if not (candidate / "topology_context.json").exists() and not _case_graph_file(
            candidate
        ):
            continue
        case_id = candidate.name
        if case_id in found:
            duplicates.setdefault(case_id, [found[case_id]]).append(candidate)
        else:
            found[case_id] = candidate
    if duplicates:
        details = "; ".join(
            f"{case_id}: {', '.join(str(path) for path in paths)}"
            for case_id, paths in sorted(duplicates.items())
        )
        raise LabelerError(f"存在重复 case ID，无法安全保存: {details}")
    if not found:
        raise LabelerError(f"未找到包含 info.json 和拓扑的 case: {data_root}")
    return dict(sorted(found.items()))


def _normalise_raw_nodes(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, Mapping):
        values: Iterable[Any] = raw.values()
    elif isinstance(raw, list):
        values = raw
    else:
        values = []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, Mapping):
            continue
        device_id = _text(item.get("mgmt_ip", item.get("ip", item.get("device_id"))))
        if not device_id or device_id == "unknown" or device_id in seen:
            continue
        seen.add(device_id)
        result.append(
            {
                "device_id": device_id,
                "name": _text(item.get("name")) or device_id,
                "topology_role": _canonical_topology_role(
                    item.get("role"), item.get("name")
                ),
                "group_ids": list(item.get("group_ids", []))
                if isinstance(item.get("group_ids"), list)
                else [],
                "segment_ids": list(item.get("segment_ids", []))
                if isinstance(item.get("segment_ids"), list)
                else [],
                "linked_from": list(item.get("linked_from", []))
                if isinstance(item.get("linked_from"), list)
                else [],
                "linked_to": list(item.get("linked_to", []))
                if isinstance(item.get("linked_to"), list)
                else [],
                "alarms": list(item.get("alarms", []))
                if isinstance(item.get("alarms"), list)
                else [],
                "logs": list(item.get("logs", []))
                if isinstance(item.get("logs"), list)
                else [],
            }
        )
    return sorted(result, key=lambda item: item["device_id"])


def _evidence_row(device_id: str, source: str, index: int, raw: Mapping[str, Any]) -> dict[str, Any]:
    timestamp = raw.get("alarm_time", raw.get("timestamp", raw.get("time")))
    name = _text(raw.get("name", raw.get("alarm_name", raw.get("event_name"))))
    description = _text(raw.get("description", raw.get("alarm_description", raw.get("content"))))
    evidence_id = _stable_id("E", device_id, source, timestamp, name, description, index)
    return {
        "evidence_id": evidence_id,
        "device_id": device_id,
        "source": source,
        "timestamp": timestamp,
        "name": name or f"{source} {index + 1}",
        "description": description,
        "level": raw.get("alarm_level", raw.get("level")),
        "weight": raw.get("alarm_weight", raw.get("weight")),
        "details": dict(raw),
    }


def _fallback_topology(raw_nodes: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    node_ids = {str(item["device_id"]) for item in raw_nodes}
    pairs: set[tuple[str, str]] = set()
    for item in raw_nodes:
        device_id = str(item["device_id"])
        neighbors = [*item.get("linked_from", []), *item.get("linked_to", [])]
        for raw_neighbor in neighbors:
            neighbor = _text(raw_neighbor)
            if neighbor in node_ids and neighbor != device_id:
                pairs.add(tuple(sorted((device_id, neighbor))))
    edges = [
        {
            "edge_id": _stable_id("L", endpoint_a, endpoint_b),
            "endpoint_a": endpoint_a,
            "endpoint_b": endpoint_b,
            "endpoint_a_port": "",
            "endpoint_b_port": "",
            "group_ids": ["FALLBACK"],
            "segment_ids": ["FALLBACK"],
        }
        for endpoint_a, endpoint_b in sorted(pairs)
    ]
    nodes = [
        {
            key: item[key]
            for key in ("device_id", "name", "topology_role", "group_ids", "segment_ids")
        }
        for item in raw_nodes
    ]
    return nodes, edges


def _topology_sidecar(case_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    raw = _read_json(case_dir / "topology_context.json", default=None)
    if not isinstance(raw, Mapping):
        return None
    nodes = []
    for item in raw.get("nodes", []):
        if not isinstance(item, Mapping) or not _text(item.get("device_id")):
            continue
        nodes.append(
            {
                "device_id": _text(item.get("device_id")),
                "name": _text(item.get("name")) or _text(item.get("device_id")),
                "topology_role": _canonical_topology_role(
                    item.get("role", item.get("topology_role")), item.get("name")
                ),
                "group_ids": list(item.get("group_ids", [])),
                "segment_ids": list(item.get("segment_ids", [])),
                "pod_number": item.get("pod_number"),
            }
        )
    edges = []
    for item in raw.get("edges", []):
        if not isinstance(item, Mapping):
            continue
        endpoint_a = _text(item.get("endpoint_a"))
        endpoint_b = _text(item.get("endpoint_b"))
        if not endpoint_a or not endpoint_b or endpoint_a == endpoint_b:
            continue
        edges.append(
            {
                "edge_id": _text(item.get("edge_id")) or _stable_id("L", endpoint_a, endpoint_b),
                "endpoint_a": endpoint_a,
                "endpoint_b": endpoint_b,
                "endpoint_a_port": _text(item.get("endpoint_a_port")),
                "endpoint_b_port": _text(item.get("endpoint_b_port")),
                "group_ids": list(item.get("group_ids", [])),
                "segment_ids": list(item.get("segment_ids", [])),
            }
        )
    return sorted(nodes, key=lambda item: item["device_id"]), sorted(
        edges, key=lambda item: item["edge_id"]
    )


def _anchor_devices(
    endpoints: Sequence[str],
    node_ids: set[str],
    raw_nodes: Sequence[Mapping[str, Any]],
) -> list[str]:
    anchors = set(endpoints) & node_ids
    endpoint_set = set(endpoints)
    for item in raw_nodes:
        device_id = str(item["device_id"])
        neighbors = {
            _text(value)
            for value in [*item.get("linked_from", []), *item.get("linked_to", [])]
        }
        if neighbors & endpoint_set:
            anchors.add(device_id)
    return sorted(anchors)


def _case_evidence(raw_nodes: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    evidence: list[dict[str, Any]] = []
    by_device: dict[str, list[str]] = {}
    for node in raw_nodes:
        device_id = str(node["device_id"])
        rows: list[dict[str, Any]] = []
        for source, values in (("alarm", node.get("alarms", [])), ("log", node.get("logs", []))):
            for index, raw in enumerate(values):
                if isinstance(raw, Mapping):
                    rows.append(_evidence_row(device_id, source, index, raw))
        evidence.extend(rows)
        by_device[device_id] = [item["evidence_id"] for item in rows]
    return evidence, by_device


def _event_catalog(
    evidence: Sequence[Mapping[str, Any]],
    hypothesis: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return labelable Event nodes, preferring normalized M1 episodes."""

    hypothesis_events = (
        hypothesis.get("event_nodes", []) if isinstance(hypothesis, Mapping) else []
    )
    if isinstance(hypothesis_events, list) and hypothesis_events:
        result = []
        for raw in hypothesis_events:
            if not isinstance(raw, Mapping):
                continue
            evidence_id = _text(raw.get("evidence_id"))
            device_id = _text(raw.get("device_id"))
            if not evidence_id or not device_id:
                continue
            source_types = raw.get("source_types", [])
            source = _text(raw.get("source_type"))
            if not source and isinstance(source_types, list) and source_types:
                source = _text(source_types[0])
            result.append(
                {
                    **dict(raw),
                    "evidence_id": evidence_id,
                    "device_id": device_id,
                    "source": source or "event",
                    "name": _text(raw.get("event_name", raw.get("event_type")))
                    or evidence_id,
                    "description": _text(
                        raw.get("description", raw.get("object_or_interface"))
                    ),
                    "timestamp": raw.get("timestamp"),
                    "details": dict(raw),
                }
            )
        return sorted(result, key=lambda item: (item["device_id"], item["evidence_id"]))

    return [
        {
            **dict(item),
            "source_type": item.get("source"),
            "event_name": item.get("name"),
            "event_type": "generic_event",
            "fault_layer": "unknown",
            "onset_interval_ms": None,
            "incident_relevance": 1.0,
            "quality": {"normalised_episode": False},
        }
        for item in evidence
        if isinstance(item, Mapping)
        and _text(item.get("evidence_id"))
        and _text(item.get("device_id"))
    ]


def _hypothesis_records(raw: Any, path: Path) -> list[Mapping[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, Mapping)]
    if not isinstance(raw, Mapping):
        return []
    for key in ("records", "cases", "results"):
        values = raw.get(key)
        if isinstance(values, list):
            return [item for item in values if isinstance(item, Mapping)]
    if (
        raw.get("graph_type")
        or raw.get("edge_hypotheses")
        or raw.get("m1_candidate_graph")
        or raw.get("m2_probabilistic_graph")
        or raw.get("m3_reconstruction")
    ):
        return [{"case_id": raw.get("case_id") or path.stem, "hypothesis_graph": raw}]
    if any(
        key in raw
        for key in ("dir", "case_id", "hypothesis_graph", "propagation", "result")
    ):
        return [raw]
    records: list[Mapping[str, Any]] = []
    for case_id, value in raw.items():
        if isinstance(value, Mapping):
            records.append({"case_id": case_id, "hypothesis_graph": value})
    return records


def _record_hypothesis(record: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, str]:
    result = record.get("result")
    if isinstance(result, Mapping) and any(
        key in result
        for key in ("m1_candidate_graph", "m2_probabilistic_graph", "m3_reconstruction")
    ):
        return result, "heterogeneous_propagation"
    hypothesis = record.get("hypothesis_graph")
    fallback_hypothesis = hypothesis if isinstance(hypothesis, Mapping) else None
    if isinstance(hypothesis, Mapping) and any(
        key in hypothesis
        for key in ("m1_candidate_graph", "m2_probabilistic_graph", "m3_reconstruction")
    ):
        return hypothesis, "heterogeneous_propagation"
    if isinstance(hypothesis, Mapping) and any(
        key in hypothesis for key in ("nodes", "edge_hypotheses", "candidate_topology_edges")
    ):
        return hypothesis, "hypothesis_graph"
    propagation = record.get("propagation")
    if isinstance(propagation, Mapping):
        hypothesis = propagation.get("hypothesis_graph")
        if isinstance(hypothesis, Mapping):
            fallback_hypothesis = hypothesis
        if isinstance(hypothesis, Mapping) and any(
            key in hypothesis
            for key in ("nodes", "edge_hypotheses", "candidate_topology_edges")
        ):
            return hypothesis, "hypothesis_graph"
    selected = record.get("selected_propagation_graph")
    if not isinstance(selected, Mapping) and isinstance(propagation, Mapping):
        selected = propagation.get("selected_propagation_graph")
        if not isinstance(selected, Mapping) and propagation.get("nodes"):
            selected = propagation
    if isinstance(selected, Mapping):
        return selected, "selected_propagation_graph"
    if fallback_hypothesis is not None:
        return fallback_hypothesis, "hypothesis_graph"
    return None, ""


def _hypothesis_node(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, Mapping):
        device_id = _text(raw.get("device_id", raw.get("ip", raw.get("mgmt_ip"))))
        if not device_id:
            return None
        return {**dict(raw), "device_id": device_id}
    device_id = _text(raw)
    return {"device_id": device_id} if device_id else None


def _strip_typed_id(value: Any, prefix: str) -> str:
    text = _text(value)
    marker = f"{prefix}:"
    return text[len(marker) :] if text.startswith(marker) else text


def _root_devices_from_graph(graph: Mapping[str, Any]) -> list[str]:
    selected = graph.get("selected_root", {})
    if not isinstance(selected, Mapping):
        return []
    values = selected.get("root_devices", [])
    if isinstance(values, list):
        result = [_text(item) for item in values if _text(item)]
        if result:
            return result
    for key in ("device_id", "ip", "root_device"):
        value = _text(selected.get(key))
        if value:
            return [value]
    return []


def _normalise_heterogeneous_hypothesis(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten the active M1/M2/M3 artifact into the UI's review contract."""

    m1 = graph.get("m1_candidate_graph", {})
    m2 = graph.get("m2_probabilistic_graph", {})
    m3 = graph.get("m3_reconstruction", {})
    if not isinstance(m1, Mapping):
        m1 = {}
    if not isinstance(m2, Mapping):
        m2 = {}
    if not isinstance(m3, Mapping):
        m3 = {}

    device_nodes: list[dict[str, Any]] = []
    event_nodes: list[dict[str, Any]] = []
    for item in m1.get("nodes", []):
        if not isinstance(item, Mapping):
            continue
        node_type = _text(item.get("node_type"))
        if node_type == "device":
            node = _hypothesis_node(item)
            if node:
                device_nodes.append(node)
        elif node_type == "event":
            evidence_id = _text(item.get("evidence_id")) or _strip_typed_id(
                item.get("node_id"), "event"
            )
            device_id = _text(item.get("device_id"))
            if evidence_id and device_id:
                event_nodes.append(
                    {**dict(item), "evidence_id": evidence_id, "device_id": device_id}
                )

    evidence_map: dict[str, dict[str, Any]] = {}
    raw_evidence_map = m1.get("evidence_map", {})
    if isinstance(raw_evidence_map, Mapping):
        evidence_map.update(
            {
                str(key): dict(value)
                for key, value in raw_evidence_map.items()
                if isinstance(value, Mapping)
            }
        )
    for event in event_nodes:
        evidence_map.setdefault(str(event["evidence_id"]), dict(event))

    fixed_relations = [
        dict(item) for item in m1.get("relations", []) if isinstance(item, Mapping)
    ]
    candidate_topology_edges: list[dict[str, Any]] = []
    for item in fixed_relations:
        if item.get("relation_type") != "device_physical_adjacency":
            continue
        endpoint_a = _strip_typed_id(item.get("source"), "device")
        endpoint_b = _strip_typed_id(item.get("target"), "device")
        if endpoint_a and endpoint_b and endpoint_a != endpoint_b:
            candidate_topology_edges.append(
                {
                    "endpoint_a": endpoint_a,
                    "endpoint_b": endpoint_b,
                    "topology_edge_ids": list(item.get("topology_edge_ids", [])),
                }
            )

    dd_relations = [
        dict(item)
        for item in m2.get("device_relations", [])
        if isinstance(item, Mapping)
        and _text(item.get("endpoint_a"))
        and _text(item.get("endpoint_b"))
    ]
    ee_relations = [
        dict(item)
        for item in m2.get("event_relations", [])
        if isinstance(item, Mapping)
        and _text(item.get("endpoint_a"))
        and _text(item.get("endpoint_b"))
    ]

    device_graph = m3.get("device_propagation_graph", {})
    if not isinstance(device_graph, Mapping):
        device_graph = {}
    selected_dd_edges = [
        dict(item) for item in device_graph.get("edges", []) if isinstance(item, Mapping)
    ]
    event_graph = m3.get("event_explanation_graph", {})
    if not isinstance(event_graph, Mapping):
        event_graph = {}
    selected_ee_relations = [
        dict(item)
        for item in event_graph.get("relations", [])
        if isinstance(item, Mapping)
    ]
    selected_dd_directions = {
        (_text(item.get("from")), _text(item.get("to")))
        for item in selected_dd_edges
        if _text(item.get("from")) and _text(item.get("to"))
    }
    for relation in dd_relations:
        a, b = _text(relation.get("endpoint_a")), _text(relation.get("endpoint_b"))
        if (a, b) in selected_dd_directions:
            relation["m3_selected_state"] = f"{a}->{b}"
        elif (b, a) in selected_dd_directions:
            relation["m3_selected_state"] = f"{b}->{a}"
    selected_ee_directions = {
        (
            _strip_typed_id(item.get("source_evidence_id", item.get("source")), "event"),
            _strip_typed_id(item.get("target_evidence_id", item.get("target")), "event"),
        )
        for item in selected_ee_relations
    }
    for relation in ee_relations:
        a, b = _text(relation.get("endpoint_a")), _text(relation.get("endpoint_b"))
        if (a, b) in selected_ee_directions:
            relation["m3_selected_state"] = f"{a}->{b}"
        elif (b, a) in selected_ee_directions:
            relation["m3_selected_state"] = f"{b}->{a}"

    roots = _root_devices_from_graph(graph)
    if not roots:
        roots = _root_devices_from_graph(m3)
    summary = dict(graph.get("summary", {})) if isinstance(graph.get("summary"), Mapping) else {}
    summary.update(
        {
            "root_independent": True,
            "heterogeneous": True,
            "device_node_count": len(device_nodes),
            "event_node_count": len(event_nodes),
            "dd_relation_count": len(dd_relations),
            "ee_relation_count": len(ee_relations),
            "identifiability": (
                dict(m3.get("identifiability", {}))
                if isinstance(m3.get("identifiability"), Mapping)
                else {}
            ),
        }
    )
    return {
        "schema_version": _text(graph.get("schema_version")) or "heterogeneous-propagation-v0",
        "graph_type": "heterogeneous_propagation_graph",
        "graph_kind": "heterogeneous_propagation",
        "nodes": device_nodes,
        "device_nodes": device_nodes,
        "event_nodes": event_nodes,
        "candidate_topology_edges": candidate_topology_edges,
        "edge_hypotheses": dd_relations,
        "dd_relations": dd_relations,
        "ee_relations": ee_relations,
        "selected_dd_edges": selected_dd_edges,
        "selected_ee_relations": selected_ee_relations,
        "fixed_relations": fixed_relations,
        "evidence_grounding_relations": [
            dict(item)
            for item in m3.get("evidence_grounding_relations", [])
            if isinstance(item, Mapping)
        ],
        "symptom_explanation_relations": [
            dict(item)
            for item in m3.get("symptom_explanation_relations", [])
            if isinstance(item, Mapping)
        ],
        "affected_targets": [
            dict(item)
            for item in m1.get("affected_targets", [])
            if isinstance(item, Mapping)
        ],
        "source_anchors": list(m1.get("source_anchors", [])),
        "sink_anchors": list(m1.get("sink_anchors", [])),
        "evidence_map": evidence_map,
        "root_devices": roots,
        "root_potentials": [
            dict(item) for item in m2.get("root_potentials", []) if isinstance(item, Mapping)
        ],
        "root_graph_hypotheses": [
            dict(item) for item in m3.get("root_graph_hypotheses", []) if isinstance(item, Mapping)
        ],
        "summary": summary,
    }


def _normalise_hypothesis(graph: Mapping[str, Any], graph_kind: str) -> dict[str, Any]:
    if graph_kind == "heterogeneous_propagation":
        return _normalise_heterogeneous_hypothesis(graph)
    nodes = [node for item in graph.get("nodes", []) if (node := _hypothesis_node(item))]
    root = graph.get("root_hypothesis", {})
    roots = list(root.get("root_devices", [])) if isinstance(root, Mapping) else []
    if graph_kind == "selected_propagation_graph":
        hypotheses = []
        for item in graph.get("edges", []):
            if not isinstance(item, Mapping):
                continue
            source = _text(item.get("from"))
            target = _text(item.get("to"))
            if not source or not target:
                continue
            direction = {**dict(item), "from": source, "to": target, "state_probability": 1.0}
            hypotheses.append(
                {
                    "endpoint_a": source,
                    "endpoint_b": target,
                    "preferred_state": f"{source}->{target}",
                    "state_probabilities": {
                        "endpoint_a_to_b": 1.0,
                        "endpoint_b_to_a": 0.0,
                        "no_direct_propagation": 0.0,
                    },
                    "directions": [direction],
                    "legacy_selected_edge": True,
                }
            )
        return {
            "schema_version": _text(graph.get("schema_version")) or "legacy-selected-graph",
            "graph_type": "selected_propagation_graph",
            "graph_kind": graph_kind,
            "nodes": nodes,
            "device_nodes": nodes,
            "event_nodes": [],
            "candidate_topology_edges": [],
            "edge_hypotheses": hypotheses,
            "dd_relations": hypotheses,
            "ee_relations": [],
            "selected_dd_edges": [dict(item) for item in graph.get("edges", []) if isinstance(item, Mapping)],
            "selected_ee_relations": [],
            "affected_targets": [],
            "source_anchors": [],
            "sink_anchors": [],
            "evidence_map": {},
            "root_devices": roots,
            "summary": {"root_independent": False, "legacy_selected_graph": True},
        }

    topology_edges = [
        dict(item)
        for item in graph.get("candidate_topology_edges", [])
        if isinstance(item, Mapping)
        and _text(item.get("endpoint_a"))
        and _text(item.get("endpoint_b"))
    ]
    edge_hypotheses = [
        dict(item)
        for item in graph.get("edge_hypotheses", [])
        if isinstance(item, Mapping)
        and _text(item.get("endpoint_a"))
        and _text(item.get("endpoint_b"))
    ]
    evidence_map = graph.get("evidence_map", {})
    if not isinstance(evidence_map, Mapping):
        evidence_map = {}
    return {
        "schema_version": _text(graph.get("schema_version")) or "hypothesis-graph-v1",
        "graph_type": _text(graph.get("graph_type")) or "root_independent_hypothetical_propagation_graph",
        "graph_kind": graph_kind,
        "nodes": nodes,
        "device_nodes": nodes,
        "event_nodes": [],
        "candidate_topology_edges": topology_edges,
        "edge_hypotheses": edge_hypotheses,
        "dd_relations": edge_hypotheses,
        "ee_relations": [],
        "selected_dd_edges": [],
        "selected_ee_relations": [],
        "affected_targets": [dict(item) for item in graph.get("affected_targets", []) if isinstance(item, Mapping)],
        "source_anchors": list(graph.get("source_anchors", [])),
        "sink_anchors": list(graph.get("sink_anchors", [])),
        "evidence_map": {
            str(key): dict(value)
            for key, value in evidence_map.items()
            if isinstance(value, Mapping)
        },
        "root_devices": roots,
        "summary": dict(graph.get("summary", {})) if isinstance(graph.get("summary"), Mapping) else {},
    }


def _hypothesis_map(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    raw = _read_json(path, default=[])
    result: dict[str, dict[str, Any]] = {}
    for record in _hypothesis_records(raw, path):
        raw_case_id = record.get("case_id") or record.get("dir")
        if not raw_case_id:
            continue
        case_id = Path(str(raw_case_id)).name
        graph, graph_kind = _record_hypothesis(record)
        if graph is None:
            continue
        result[case_id] = _normalise_hypothesis(graph, graph_kind)
    return result


def _prediction_map(path: Path | None) -> dict[str, dict[str, Any]]:
    """Backward-compatible alias for integrations importing the old helper."""

    return _hypothesis_map(path)


def default_label(case_id: str, annotator: str = "") -> dict[str, Any]:
    return {
        "schema_version": LABEL_SCHEMA_VERSION,
        "case_id": case_id,
        "root_scope": "uncertain",
        "root_devices": [],
        "root_link": None,
        "diagnosability": "unidentifiable",
        "identifiability": "unidentifiable",
        "annotation_complete_scope": {
            "device_nodes": False,
            "dd_candidate_pairs": False,
            "priority_ee_pairs": False,
            "all_ee_candidate_pairs": False,
        },
        # ``nodes``/``edges`` remain as device-layer compatibility aliases for
        # the existing evaluators.  The explicit typed fields are canonical in
        # the v1 heterogeneous schema and are refreshed on every save.
        "nodes": [],
        "edges": [],
        "device_nodes": [],
        "dd_edges": [],
        "event_nodes": [],
        "ee_edges": [],
        "acceptable_hypotheses": [],
        "excluded_edges": [],
        "topology_overrides": {"virtual_nodes": [], "virtual_edges": []},
        "annotator_confidence": "low",
        "notes": "",
        "annotation_status": "draft",
        "annotation_metadata": {
            "annotator": annotator,
            "round": 1,
            "updated_at": None,
            "tool": "propagation_labeler",
            "tool_version": TOOL_VERSION,
        },
    }


def _seed_source_roots(
    label: dict[str, Any], source_roots: Sequence[str]
) -> dict[str, Any]:
    """Seed roots only when a propagation label has not already chosen them."""

    if label.get("root_devices") or label.get("root_link"):
        return label
    roots = list(dict.fromkeys(_text(item) for item in source_roots if _text(item)))
    if not roots:
        return label
    label["root_devices"] = roots
    label["root_scope"] = "device" if len(roots) == 1 else "multiple_devices"
    nodes = label.setdefault("nodes", [])
    existing = {
        _text(item.get("device_id")): item
        for item in nodes
        if isinstance(item, Mapping) and _text(item.get("device_id"))
    }
    for device_id in roots:
        node = existing.get(device_id)
        if node is None:
            node = {
                "device_id": device_id,
                "role": "root",
                "membership": "definite",
                "onset_interval": None,
                "evidence_ids": [],
                "note": "",
            }
            nodes.append(node)
            existing[device_id] = node
        else:
            node["role"] = "root"
            node["membership"] = "definite"
    return label


def _normalise_label(label: Mapping[str, Any], case_id: str) -> dict[str, Any]:
    """Upgrade v0/device-only labels and synchronize typed v1 aliases."""

    result = json.loads(json.dumps(label, ensure_ascii=False))
    source_schema_version = _text(result.get("schema_version"))
    result["schema_version"] = LABEL_SCHEMA_VERSION
    result["case_id"] = case_id

    raw_device_nodes = result.get("nodes")
    if not isinstance(raw_device_nodes, list):
        raw_device_nodes = result.get("device_nodes", [])
    device_nodes: list[dict[str, Any]] = []
    compatibility_nodes: list[dict[str, Any]] = []
    for raw in raw_device_nodes if isinstance(raw_device_nodes, list) else []:
        if not isinstance(raw, Mapping):
            continue
        device_id = _text(raw.get("device_id"))
        state = _text(raw.get("membership", raw.get("state"))) or "unknown"
        if state not in NODE_MEMBERSHIPS:
            state = "unknown"
        interval = raw.get("onset_interval", raw.get("onset_interval_ms"))
        common = {
            "device_id": device_id,
            "role": _text(raw.get("role")) or "uncertain",
            "state": state,
            "onset_interval_ms": interval,
            "evidence_ids": list(raw.get("evidence_ids", []))
            if isinstance(raw.get("evidence_ids"), list)
            else [],
            "note": _text(raw.get("note")),
        }
        device_nodes.append(common)
        compatibility_nodes.append(
            {
                **common,
                "membership": state,
                "onset_interval": interval,
            }
        )

    raw_dd_edges = result.get("edges")
    if not isinstance(raw_dd_edges, list):
        raw_dd_edges = result.get("dd_edges", [])
    dd_edges: list[dict[str, Any]] = []
    compatibility_edges: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_dd_edges if isinstance(raw_dd_edges, list) else [], 1):
        if not isinstance(raw, Mapping):
            continue
        source = _text(raw.get("from", raw.get("source")))
        target = _text(raw.get("to", raw.get("target")))
        state = _text(raw.get("membership", raw.get("state"))) or "unknown"
        if state == "impossible":
            state = "explicit_no_direct"
        if state not in DD_EDGE_STATES:
            state = "unknown"
        edge_id = _text(raw.get("edge_id", raw.get("dd_edge_id"))) or f"DD{index}"
        common = {
            "dd_edge_id": edge_id,
            "source": source,
            "target": target,
            "state": state,
            "relation": _text(raw.get("relation")) or "physical_link",
            "direction_status": _text(raw.get("direction_status")) or "unresolved",
            "lag_interval_ms": raw.get("lag_interval_ms"),
            "evidence_ids": list(raw.get("evidence_ids", []))
            if isinstance(raw.get("evidence_ids"), list)
            else [],
            "supporting_event_ids": list(raw.get("supporting_event_ids", []))
            if isinstance(raw.get("supporting_event_ids"), list)
            else [],
            "alternative_group": _text(raw.get("alternative_group")),
            "note": _text(raw.get("note")),
        }
        dd_edges.append(common)
        compatibility_edges.append(
            {
                **common,
                "edge_id": edge_id,
                "from": source,
                "to": target,
                "membership": state,
            }
        )

    event_nodes: list[dict[str, Any]] = []
    for raw in result.get("event_nodes", []) if isinstance(result.get("event_nodes"), list) else []:
        if not isinstance(raw, Mapping):
            continue
        event_nodes.append(
            {
                **dict(raw),
                "evidence_id": _text(raw.get("evidence_id")),
                "device_id": _text(raw.get("device_id")),
                "role": _text(raw.get("role")) or "uncertain",
                "state": _text(raw.get("state", raw.get("membership"))) or "unknown",
                "note": _text(raw.get("note")),
            }
        )

    ee_edges: list[dict[str, Any]] = []
    for index, raw in enumerate(
        result.get("ee_edges", []) if isinstance(result.get("ee_edges"), list) else [], 1
    ):
        if not isinstance(raw, Mapping):
            continue
        state = _text(raw.get("state", raw.get("membership"))) or "unknown"
        if state in {"impossible", "explicit_no_direct"}:
            state = "explicit_no_dependency"
        ee_edges.append(
            {
                **dict(raw),
                "ee_edge_id": _text(raw.get("ee_edge_id", raw.get("edge_id")))
                or f"EE{index}",
                "source_evidence_id": _text(
                    raw.get("source_evidence_id", raw.get("from", raw.get("source")))
                ),
                "target_evidence_id": _text(
                    raw.get("target_evidence_id", raw.get("to", raw.get("target")))
                ),
                "state": state,
                "relation": _text(raw.get("relation")) or "dependency_or_evolution",
                "direction_status": _text(raw.get("direction_status")) or "unresolved",
                "lag_interval_ms": raw.get("lag_interval_ms"),
                "supports_dd_edge_ids": list(raw.get("supports_dd_edge_ids", []))
                if isinstance(raw.get("supports_dd_edge_ids"), list)
                else [],
                "note": _text(raw.get("note")),
            }
        )

    identifiability = _text(result.get("identifiability"))
    legacy_diagnosability = _text(result.get("diagnosability"))
    if source_schema_version != LABEL_SCHEMA_VERSION and legacy_diagnosability in {"fully_observed", "partially_observed"} and identifiability in {
        "",
        "unidentifiable",
    }:
        identifiability = {
            "fully_observed": "identifiable",
            "partially_observed": "partially_identifiable",
        }[legacy_diagnosability]
    if identifiability not in IDENTIFIABILITY:
        identifiability = {
            "fully_observed": "identifiable",
            "partially_observed": "partially_identifiable",
            "unidentifiable": "unidentifiable",
            "out_of_scope": "out_of_scope",
        }.get(_text(result.get("diagnosability")), "unidentifiable")
    result["identifiability"] = identifiability
    result["diagnosability"] = {
        "identifiable": "fully_observed",
        "partially_identifiable": "partially_observed",
        "unidentifiable": "unidentifiable",
        "out_of_scope": "out_of_scope",
    }[identifiability]

    scope = result.get("annotation_complete_scope")
    if not isinstance(scope, Mapping):
        scope = {}
    result["annotation_complete_scope"] = {
        key: bool(scope.get(key, False)) for key in sorted(ANNOTATION_SCOPE_KEYS)
    }
    result["device_nodes"] = device_nodes
    result["dd_edges"] = dd_edges
    result["event_nodes"] = event_nodes
    result["ee_edges"] = ee_edges
    result["nodes"] = compatibility_nodes
    result["edges"] = compatibility_edges
    raw_overrides = result.get("topology_overrides")
    if not isinstance(raw_overrides, Mapping):
        raw_overrides = {}
    virtual_nodes = []
    for raw in raw_overrides.get("virtual_nodes", []):
        if not isinstance(raw, Mapping):
            continue
        device_id = _text(raw.get("device_id"))
        if not device_id:
            continue
        virtual_nodes.append(
            {
                "device_id": device_id,
                "name": _text(raw.get("name")) or "手工中转 CORE",
                "topology_role": "CORE",
                "is_inferred": True,
                "annotation_selectable": False,
                "inference_kind": "manual_transit_core",
                "note": _text(raw.get("note")),
            }
        )
    virtual_ids = {item["device_id"] for item in virtual_nodes}
    virtual_edges = []
    for index, raw in enumerate(raw_overrides.get("virtual_edges", []), 1):
        if not isinstance(raw, Mapping):
            continue
        endpoint_a = _text(raw.get("endpoint_a"))
        endpoint_b = _text(raw.get("endpoint_b"))
        if not endpoint_a or not endpoint_b or endpoint_a == endpoint_b:
            continue
        if endpoint_a not in virtual_ids and endpoint_b not in virtual_ids:
            continue
        virtual_edges.append(
            {
                "edge_id": _text(raw.get("edge_id")) or f"MANUAL-TOPO-{index}",
                "endpoint_a": endpoint_a,
                "endpoint_b": endpoint_b,
                "is_inferred": True,
                "annotation_selectable": False,
                "inference_kind": "manual_transit_core_link",
                "note": _text(raw.get("note")),
            }
        )
    result["topology_overrides"] = {
        "virtual_nodes": virtual_nodes,
        "virtual_edges": virtual_edges,
    }
    result.setdefault("acceptable_hypotheses", [])
    result.setdefault("excluded_edges", [])
    result.setdefault("notes", "")
    result.setdefault("annotation_status", "draft")
    result.setdefault("annotator_confidence", "low")
    return result


def _is_interval(value: Any) -> bool:
    if value in (None, []):
        return True
    if not isinstance(value, list) or len(value) != 2:
        return False
    try:
        low, high = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return False
    return 0 <= low <= high


def _has_cycle(edges: Sequence[tuple[str, str]]) -> bool:
    adjacency: dict[str, list[str]] = {}
    for source, target in edges:
        adjacency.setdefault(source, []).append(target)
        adjacency.setdefault(target, [])
    state: dict[str, int] = {}

    def visit(node: str) -> bool:
        state[node] = 1
        for neighbor in adjacency.get(node, []):
            if state.get(neighbor, 0) == 1:
                return True
            if state.get(neighbor, 0) == 0 and visit(neighbor):
                return True
        state[node] = 2
        return False

    return any(state.get(node, 0) == 0 and visit(node) for node in adjacency)


def validate_label(
    label: Mapping[str, Any],
    *,
    case_id: str,
    valid_device_ids: set[str] | None = None,
    topology_pairs: set[frozenset[str]] | None = None,
    valid_event_ids: set[str] | None = None,
    event_devices: Mapping[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for the typed DD/EE annotation schema."""

    value = _normalise_label(label, case_id)
    errors: list[str] = []
    warnings: list[str] = []
    completed = value.get("annotation_status") == "completed"
    if label.get("case_id") != case_id:
        errors.append("case_id 与当前 case 不一致")
    if value.get("root_scope") not in ROOT_SCOPES:
        errors.append("root_scope 取值无效")
    if value.get("identifiability") not in IDENTIFIABILITY:
        errors.append("identifiability 取值无效")
    if value.get("annotator_confidence") not in CONFIDENCE:
        errors.append("annotator_confidence 取值无效")
    if value.get("annotation_status") not in ANNOTATION_STATUSES:
        errors.append("annotation_status 取值无效")

    scope = value["annotation_complete_scope"]
    if not isinstance(scope, Mapping) or any(
        key not in ANNOTATION_SCOPE_KEYS for key in scope
    ):
        errors.append("annotation_complete_scope 取值无效")

    node_ids: set[str] = set()
    node_roles: dict[str, str] = {}
    for index, node in enumerate(value["device_nodes"], 1):
        device_id = _text(node.get("device_id"))
        if not device_id:
            errors.append(f"设备节点 {index} 缺少 device_id")
        elif device_id in node_ids:
            errors.append(f"设备节点重复: {device_id}")
        elif valid_device_ids is not None and device_id not in valid_device_ids:
            errors.append(f"设备节点不在本 case 拓扑中: {device_id}")
        node_ids.add(device_id)
        node_roles[device_id] = _text(node.get("role"))
        if node.get("role") not in NODE_ROLES:
            errors.append(f"设备节点 {device_id or index} 的 role 无效")
        if node.get("state") not in NODE_MEMBERSHIPS:
            errors.append(f"设备节点 {device_id or index} 的 state 无效")
        if not _is_interval(node.get("onset_interval_ms")):
            errors.append(f"设备节点 {device_id or index} 的 onset_interval_ms 无效")
        if not isinstance(node.get("evidence_ids", []), list):
            errors.append(f"设备节点 {device_id or index} 的 evidence_ids 必须是列表")

    dd_ids: set[str] = set()
    dd_pairs: set[tuple[str, str]] = set()
    dd_dag_edges: list[tuple[str, str]] = []
    for index, edge in enumerate(value["dd_edges"], 1):
        edge_id = _text(edge.get("dd_edge_id"))
        source, target = _text(edge.get("source")), _text(edge.get("target"))
        state = edge.get("state")
        if not edge_id:
            errors.append(f"DD 边 {index} 缺少 dd_edge_id")
        elif edge_id in dd_ids:
            errors.append(f"DD 边 ID 重复: {edge_id}")
        dd_ids.add(edge_id)
        if not source or not target or source == target:
            errors.append(f"DD 边 {edge_id or index} 的端点无效")
        if source not in node_ids or target not in node_ids:
            errors.append(f"DD 边 {edge_id or index} 的端点尚未加入设备节点标注")
        if (source, target) in dd_pairs:
            errors.append(f"重复 DD 有向边: {source} -> {target}")
        dd_pairs.add((source, target))
        if state not in DD_EDGE_STATES:
            errors.append(f"DD 边 {edge_id or index} 的 state 无效")
        if edge.get("relation") not in EDGE_RELATIONS:
            errors.append(f"DD 边 {edge_id or index} 的 relation 无效")
        if edge.get("direction_status") not in DIRECTION_STATUSES:
            errors.append(f"DD 边 {edge_id or index} 的 direction_status 无效")
        if not _is_interval(edge.get("lag_interval_ms")):
            errors.append(f"DD 边 {edge_id or index} 的 lag_interval_ms 无效")
        if not isinstance(edge.get("evidence_ids", []), list):
            errors.append(f"DD 边 {edge_id or index} 的 evidence_ids 必须是列表")
        if not isinstance(edge.get("supporting_event_ids", []), list):
            errors.append(f"DD 边 {edge_id or index} 的 supporting_event_ids 必须是列表")
        if state in {"definite", "possible"}:
            dd_dag_edges.append((source, target))
        if (
            topology_pairs is not None
            and source
            and target
            and frozenset((source, target)) not in topology_pairs
        ):
            errors.append(f"DD 边 {source} -> {target} 不在原始物理拓扑中")
        if state == "explicit_no_direct" and not scope.get("dd_candidate_pairs"):
            errors.append("使用 explicit_no_direct 前必须声明 DD 候选对已完整检查")
        if state == "definite" and not (
            edge.get("evidence_ids") or edge.get("supporting_event_ids")
        ):
            warnings.append(f"definite DD 边 {source} -> {target} 未绑定事件或原始证据")

    if _has_cycle(dd_dag_edges):
        errors.append("definite/possible DD 传播边构成了环，设备传播图必须是 DAG")

    # In simple mode annotators label only directed DD edges. Device membership
    # is derived from edge incidence, so a propagation device may also have
    # outgoing propagation edges. Completion only requires the selected graph
    # to start at a root and remain root-reachable.
    if completed:
        roots = {
            _text(item)
            for item in value.get("root_devices", [])
            if _text(item)
        }
        root_link = value.get("root_link")
        if isinstance(root_link, Mapping):
            roots.update(
                _text(root_link.get(key))
                for key in ("endpoint_a", "endpoint_b")
                if _text(root_link.get(key))
            )
        roots.update(
            device_id
            for device_id, role in node_roles.items()
            if role in {"root", "root_endpoint"}
        )
        outgoing: dict[str, set[str]] = {}
        for source, target in dd_dag_edges:
            outgoing.setdefault(source, set()).add(target)
        path_nodes = {device_id for edge in dd_dag_edges for device_id in edge}
        if path_nodes and not roots:
            errors.append("传播边必须从根因节点开始")

        reachable = set(roots)
        queue = list(roots)
        for current in queue:
            for target in sorted(outgoing.get(current, set())):
                if target not in reachable:
                    reachable.add(target)
                    queue.append(target)
        for device_id in sorted(path_nodes - reachable):
            errors.append(f"传播路径节点 {device_id} 无法从根因节点到达")

    event_ids: set[str] = set()
    for index, event in enumerate(value["event_nodes"], 1):
        evidence_id = _text(event.get("evidence_id"))
        device_id = _text(event.get("device_id"))
        if not evidence_id:
            errors.append(f"事件节点 {index} 缺少 evidence_id")
        elif evidence_id in event_ids:
            errors.append(f"事件节点重复: {evidence_id}")
        elif valid_event_ids is not None and evidence_id not in valid_event_ids:
            errors.append(f"事件节点不在本 case Evidence Episode 中: {evidence_id}")
        event_ids.add(evidence_id)
        if valid_device_ids is not None and device_id not in valid_device_ids:
            errors.append(f"事件节点 {evidence_id or index} 的 device_id 不在拓扑中")
        expected_device = event_devices.get(evidence_id) if event_devices else None
        if expected_device and device_id != expected_device:
            errors.append(f"事件节点 {evidence_id} 的观测设备与原始 Episode 不一致")
        if event.get("role") not in EVENT_ROLES:
            errors.append(f"事件节点 {evidence_id or index} 的 role 无效")
        if event.get("state") not in EVENT_STATES:
            errors.append(f"事件节点 {evidence_id or index} 的 state 无效")

    for edge in value["dd_edges"]:
        edge_id = _text(edge.get("dd_edge_id")) or "未知"
        for evidence_id in edge.get("supporting_event_ids", []):
            if evidence_id not in event_ids:
                errors.append(
                    f"DD 边 {edge_id} 引用了尚未加入事件节点标注的 supporting event: {evidence_id}"
                )

    ee_ids: set[str] = set()
    ee_pairs: set[tuple[str, str]] = set()
    ee_dag_edges: list[tuple[str, str]] = []
    for index, edge in enumerate(value["ee_edges"], 1):
        edge_id = _text(edge.get("ee_edge_id"))
        source = _text(edge.get("source_evidence_id"))
        target = _text(edge.get("target_evidence_id"))
        state = edge.get("state")
        if not edge_id:
            errors.append(f"EE 边 {index} 缺少 ee_edge_id")
        elif edge_id in ee_ids:
            errors.append(f"EE 边 ID 重复: {edge_id}")
        ee_ids.add(edge_id)
        if not source or not target or source == target:
            errors.append(f"EE 边 {edge_id or index} 的端点无效")
        if source not in event_ids or target not in event_ids:
            errors.append(f"EE 边 {edge_id or index} 的端点尚未加入事件节点标注")
        if (source, target) in ee_pairs:
            errors.append(f"重复 EE 有向边: {source} -> {target}")
        ee_pairs.add((source, target))
        if state not in EE_EDGE_STATES:
            errors.append(f"EE 边 {edge_id or index} 的 state 无效")
        if edge.get("relation") not in EE_RELATIONS:
            errors.append(f"EE 边 {edge_id or index} 的 relation 无效")
        if edge.get("direction_status") not in DIRECTION_STATUSES:
            errors.append(f"EE 边 {edge_id or index} 的 direction_status 无效")
        if not _is_interval(edge.get("lag_interval_ms")):
            errors.append(f"EE 边 {edge_id or index} 的 lag_interval_ms 无效")
        if not isinstance(edge.get("supports_dd_edge_ids", []), list):
            errors.append(f"EE 边 {edge_id or index} 的 supports_dd_edge_ids 必须是列表")
        for dd_edge_id in edge.get("supports_dd_edge_ids", []):
            if dd_edge_id not in dd_ids:
                errors.append(f"EE 边 {edge_id or index} 引用了不存在的 DD 边: {dd_edge_id}")
        if state in {"definite", "possible"}:
            ee_dag_edges.append((source, target))
        if state == "explicit_no_dependency" and not (
            scope.get("priority_ee_pairs") or scope.get("all_ee_candidate_pairs")
        ):
            errors.append("使用 explicit_no_dependency 前必须声明 EE 候选对已完整检查")

    if _has_cycle(ee_dag_edges):
        errors.append("definite/possible EE 关系构成了环，事件解释图必须是 DAG")

    root_devices = value.get("root_devices", [])
    if not isinstance(root_devices, list):
        errors.append("root_devices 必须是列表")
        root_devices = []
    root_devices = [_text(item) for item in root_devices if _text(item)]
    if valid_device_ids is not None:
        for device_id in root_devices:
            if device_id not in valid_device_ids:
                errors.append(f"根因设备不在本 case 拓扑中: {device_id}")
    root_scope = value.get("root_scope")
    if root_scope == "device" and len(root_devices) != 1:
        errors.append("device 根因必须且只能选择 1 台 root_device")
    if root_scope == "multiple_devices" and len(root_devices) < 2:
        errors.append("multiple_devices 根因至少需要 2 台 root_device")
    if root_scope == "inter_device_link":
        root_link = value.get("root_link")
        if not isinstance(root_link, Mapping):
            errors.append("链路根因需要设置 root_link")
        else:
            endpoint_a = _text(root_link.get("endpoint_a"))
            endpoint_b = _text(root_link.get("endpoint_b"))
            if not endpoint_a or not endpoint_b or endpoint_a == endpoint_b:
                errors.append("root_link 需要两个不同的端点")
            if topology_pairs is not None and frozenset((endpoint_a, endpoint_b)) not in topology_pairs:
                warnings.append("根因链路的两个端点在原始拓扑中不相邻")

    if completed:
        identifiability = value.get("identifiability")
        if identifiability in {"identifiable", "partially_identifiable"} and not value["device_nodes"]:
            errors.append("可评价 case 完成前至少需要标注 1 个设备节点")
        if identifiability == "identifiable" and not value["dd_edges"]:
            warnings.append("identifiable case 没有标注 DD 传播边，请再次确认")
        if root_scope == "uncertain" and identifiability not in {"unidentifiable", "out_of_scope"}:
            warnings.append("已完成标注，但根因作用域仍为 uncertain")
        if any(event.get("role") == "initiating" for event in value["event_nodes"]) is False:
            warnings.append("已完成标注，但没有标记 initiating event")
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))


class LabelingStore:
    def __init__(
        self,
        data_root: Path,
        labels_root: Path,
        *,
        annotator: str = "",
        predictions_path: Path | None = None,
        prediction_overlay: bool = False,
    ) -> None:
        self.data_root = data_root.resolve()
        self.labels_root = labels_root.resolve()
        self.labels_root.mkdir(parents=True, exist_ok=True)
        self.cases = discover_cases(self.data_root)
        self.annotator = annotator
        self.prediction_overlay = prediction_overlay
        self.predictions = _hypothesis_map(predictions_path) if prediction_overlay else {}
        self._bundle_cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def label_path(self, case_id: str) -> Path:
        self.case_dir(case_id)
        return self.labels_root / case_id / LABEL_FILENAME

    def case_dir(self, case_id: str) -> Path:
        try:
            return self.cases[case_id]
        except KeyError as exc:
            raise LabelerError(f"未知 case: {case_id}") from exc

    def _status(self, case_id: str) -> str:
        raw = _read_json(self.label_path(case_id), default=None)
        if isinstance(raw, Mapping):
            return _text(raw.get("annotation_status")) or "draft"
        return "unlabeled"

    def case_list(self) -> list[dict[str, Any]]:
        rows = []
        for index, (case_id, case_dir) in enumerate(self.cases.items(), 1):
            label_path = self.label_path(case_id)
            rows.append(
                {
                    "index": index,
                    "case_id": case_id,
                    "relative_path": str(case_dir.relative_to(self.data_root)),
                    "status": self._status(case_id),
                    "updated_at": datetime.fromtimestamp(label_path.stat().st_mtime).astimezone().isoformat(
                        timespec="seconds"
                    )
                    if label_path.exists()
                    else None,
                }
            )
        return rows

    def _build_bundle(self, case_id: str) -> dict[str, Any]:
        case_dir = self.case_dir(case_id)
        info = _read_json(case_dir / "info.json", default={})
        if not isinstance(info, Mapping):
            info = {}
        graph_path = _case_graph_file(case_dir)
        raw_graph = _read_json(graph_path, default={}) if graph_path else {}
        raw_nodes = _normalise_raw_nodes(raw_graph)
        sidecar = _topology_sidecar(case_dir)
        if sidecar is None:
            topology_nodes, topology_edges = _fallback_topology(raw_nodes)
            topology_source = "processed_nodes_fallback"
        else:
            topology_nodes, topology_edges = sidecar
            topology_source = "topology_context"

        raw_by_id = {str(item["device_id"]): item for item in raw_nodes}
        evidence, evidence_by_device = _case_evidence(raw_nodes)
        hypothesis = self.predictions.get(case_id) if self.prediction_overlay else None
        events = _event_catalog(evidence, hypothesis)
        source_endpoints = _parse_endpoints(info.get("source_ip"))
        sink_endpoints = _parse_endpoints(info.get("sink_ip"))
        node_ids = {str(item["device_id"]) for item in topology_nodes}
        source_root_devices = [
            device_id
            for device_id in _source_root_devices(case_dir)
            if device_id in node_ids
        ]
        source_anchors = _anchor_devices(source_endpoints, node_ids, raw_nodes)
        sink_anchors = _anchor_devices(sink_endpoints, node_ids, raw_nodes)
        enriched_nodes = []
        for item in topology_nodes:
            device_id = str(item["device_id"])
            raw = raw_by_id.get(device_id, {})
            enriched_nodes.append(
                {
                    **item,
                    "evidence_ids": evidence_by_device.get(device_id, []),
                    "alarm_count": len(raw.get("alarms", [])),
                    "log_count": len(raw.get("logs", [])),
                    "is_source_anchor": device_id in source_anchors,
                    "is_sink_anchor": device_id in sink_anchors,
                    "is_source_endpoint": device_id in source_endpoints,
                    "is_sink_endpoint": device_id in sink_endpoints,
                }
            )
        overlay = _topology_display_overlay(
            enriched_nodes,
            topology_edges,
            info=info,
            source_anchors=source_anchors,
            sink_anchors=sink_anchors,
        )
        return {
            "case_id": case_id,
            "info": {
                "alarm_name": info.get("alarm_name"),
                "alarm_time": info.get("alarm_time"),
                "source_ip": source_endpoints,
                "sink_ip": sink_endpoints,
                "scenario_code": info.get("scenario_code"),
                "alarm_description": info.get("alarm_description"),
                "source_pod": info.get("source_pod"),
                "sink_pod": info.get("sink_pod"),
                "source_az": info.get("source_az"),
                "sink_az": info.get("sink_az"),
            },
            "topology": {
                "nodes": overlay["nodes"],
                "edges": topology_edges,
                "display_nodes": overlay["display_nodes"],
                "display_edges": overlay["display_edges"],
                "reconstructed_paths": overlay["reconstructed_paths"],
                "core_forwarding_layers": overlay["core_forwarding_layers"],
                "core_layer_connections": overlay["core_layer_connections"],
                "reconstruction": overlay["reconstruction"],
                "source_anchors": source_anchors,
                "sink_anchors": sink_anchors,
                "source": topology_source,
            },
            "evidence": evidence,
            "events": events,
            "source_root_devices": source_root_devices,
            "hypothesis_graph": hypothesis,
        }

    def case_bundle(self, case_id: str) -> dict[str, Any]:
        with self._lock:
            if case_id not in self._bundle_cache:
                self._bundle_cache[case_id] = self._build_bundle(case_id)
            bundle = dict(self._bundle_cache[case_id])
            label_path = self.label_path(case_id)
            label = _read_json(label_path, default=None)
            if not isinstance(label, Mapping):
                label = default_label(case_id, self.annotator)
            else:
                label = _normalise_label(label, case_id)
            label = _seed_source_roots(
                label, bundle.get("source_root_devices", [])
            )
            bundle["label"] = label
            bundle["revision"] = _revision(label_path)
            errors, warnings = self.validate(case_id, label)
            bundle["validation"] = {"errors": errors, "warnings": warnings}
            return bundle

    def validate(self, case_id: str, label: Mapping[str, Any]) -> tuple[list[str], list[str]]:
        bundle = self._bundle_cache.get(case_id) or self._build_bundle(case_id)
        self._bundle_cache.setdefault(case_id, bundle)
        nodes = bundle["topology"]["nodes"]
        edges = bundle["topology"]["edges"]
        events = bundle.get("events", [])
        return validate_label(
            label,
            case_id=case_id,
            valid_device_ids={str(item["device_id"]) for item in nodes},
            topology_pairs={
                frozenset((str(item["endpoint_a"]), str(item["endpoint_b"])))
                for item in edges
            },
            valid_event_ids={
                str(item["evidence_id"])
                for item in events
                if isinstance(item, Mapping) and item.get("evidence_id")
            },
            event_devices={
                str(item["evidence_id"]): str(item.get("device_id", ""))
                for item in events
                if isinstance(item, Mapping) and item.get("evidence_id")
            },
        )

    def save_label(
        self,
        case_id: str,
        label: Mapping[str, Any],
        *,
        base_revision: str,
        force: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(label, Mapping):
            raise LabelerError("标注必须是 JSON 对象")
        with self._lock:
            path = self.label_path(case_id)
            current_revision = _revision(path)
            if not force and base_revision != current_revision:
                raise RevisionConflict("该标注已被另一个页面修改，请重新加载或确认覆盖")
            payload = _normalise_label(label, case_id)
            metadata = payload.get("annotation_metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                payload["annotation_metadata"] = metadata
            metadata.setdefault("annotator", self.annotator)
            metadata.setdefault("round", 1)
            metadata["updated_at"] = _timestamp_iso()
            metadata["tool"] = "propagation_labeler"
            metadata["tool_version"] = TOOL_VERSION
            errors, warnings = self.validate(case_id, payload)
            if errors:
                raise LabelerError("；".join(errors))
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            try:
                temp_path.write_bytes(_json_bytes(payload))
                os.replace(temp_path, path)
            finally:
                if temp_path.exists():
                    temp_path.unlink()
            return {
                "ok": True,
                "revision": _revision(path),
                "updated_at": metadata["updated_at"],
                "warnings": warnings,
                "status": payload.get("annotation_status", "draft"),
                "label": payload,
            }

    def summary(self) -> dict[str, Any]:
        cases = self.case_list()
        counts = {status: sum(row["status"] == status for row in cases) for status in (
            "unlabeled",
            "draft",
            "completed",
        )}
        return {"case_count": len(cases), "counts": counts, "cases": cases}


def make_handler(store: LabelingStore, ui_path: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "PropagationLabeler/2.0"

        def log_message(self, format_string: str, *args: Any) -> None:
            print(f"[{self.log_date_time_string()}] {format_string % args}")

        def _send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = _json_bytes(value)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _case_id(self, query: Mapping[str, list[str]]) -> str:
            case_id = _text((query.get("case_id") or [""])[0])
            if not case_id:
                raise LabelerError("缺少 case_id")
            store.case_dir(case_id)
            return case_id

        def do_GET(self) -> None:  # noqa: N802 - stdlib API name
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                if parsed.path == "/":
                    body = ui_path.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header(
                        "Content-Security-Policy",
                        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                        "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                        "connect-src 'self'",
                    )
                    self.end_headers()
                    self.wfile.write(body)
                elif parsed.path == "/api/config":
                    summary = store.summary()
                    self._send_json(
                        {
                            **summary,
                            "tool_version": TOOL_VERSION,
                            "prediction_overlay_enabled": store.prediction_overlay,
                            "hypothesis_view_enabled": store.prediction_overlay,
                            "labels_root": str(store.labels_root),
                        }
                    )
                elif parsed.path == "/api/case":
                    self._send_json(store.case_bundle(self._case_id(query)))
                elif parsed.path == "/api/summary":
                    self._send_json(store.summary())
                elif parsed.path == "/api/export":
                    case_id = self._case_id(query)
                    path = store.label_path(case_id)
                    if not path.exists():
                        raise LabelerError("当前 case 还没有已保存的标注")
                    body = path.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header(
                        "Content-Disposition",
                        f"attachment; filename*=UTF-8''{quote(case_id)}-{LABEL_FILENAME}",
                    )
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except LabelerError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # pragma: no cover - defensive HTTP boundary
                self._send_json({"error": f"服务器错误: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self) -> None:  # noqa: N802 - stdlib API name
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                if parsed.path != "/api/label":
                    self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
                case_id = self._case_id(query)
                content_length = int(self.headers.get("Content-Length", "0") or 0)
                if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
                    raise LabelerError("请求内容为空或超过 4 MiB")
                try:
                    request = json.loads(self.rfile.read(content_length).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise LabelerError("请求不是有效 JSON") from exc
                result = store.save_label(
                    case_id,
                    request.get("label"),
                    base_revision=_text(request.get("base_revision")),
                    force=bool(request.get("force", False)),
                )
                self._send_json(result)
            except RevisionConflict as exc:
                self._send_json(
                    {"error": str(exc), "code": "revision_conflict"}, HTTPStatus.CONFLICT
                )
            except LabelerError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
            except Exception as exc:  # pragma: no cover - defensive HTTP boundary
                self._send_json({"error": f"服务器错误: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    return Handler


def _default_path(relative: str) -> Path:
    return (Path.cwd() / relative).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="启动本地 Pingmesh 故障传播图人工标注工具",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=_default_path("data/node/nodes_labeled"),
        help="包含 case 子目录的数据根目录",
    )
    parser.add_argument(
        "--labels-root",
        type=Path,
        default=_default_path("data/propagation_labels"),
        help="标注输出根目录",
    )
    parser.add_argument("--annotator", default="", help="标注人匿名代号")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，建议保持本机地址")
    parser.add_argument("--port", type=int, default=0, help="监听端口，0 表示自动选择")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    parser.add_argument(
        "--predictions",
        "--hypotheses",
        dest="predictions",
        type=Path,
        default=None,
        help=(
            "可选的 heterogeneous_graphs.json、hypothesis_graph JSON "
            "或传播图 sidecar（压缩 res.json 不含 DD/EE 明细）"
        ),
    )
    parser.add_argument(
        "--prediction-overlay",
        "--hypothesis-view",
        dest="prediction_overlay",
        action="store_true",
        help="允许在界面中切换查看假设图（会引入锚定偏差）",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.prediction_overlay and args.predictions is None:
        raise SystemExit("假设图视角需要同时提供 --hypotheses（或 --predictions）")
    ui_path = Path(__file__).with_name("propagation_labeler_ui.html")
    if not ui_path.exists():
        raise SystemExit(f"标注界面文件缺失: {ui_path}")
    store = LabelingStore(
        args.data_root,
        args.labels_root,
        annotator=args.annotator,
        predictions_path=args.predictions,
        prediction_overlay=args.prediction_overlay,
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store, ui_path))
    actual_port = server.server_address[1]
    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{display_host}:{actual_port}/"
    print(f"传播图标注工具已启动: {url}")
    print(f"case: {len(store.cases)} | 标注输出: {store.labels_root}")
    if store.prediction_overlay:
        print("警告: 已允许切换查看假设图，不建议用于盲标真值。")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n标注工具已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
