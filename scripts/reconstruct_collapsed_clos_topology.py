#!/usr/bin/env python3
"""Recover a conservative Clos topology overlay from cropped Pingmesh data.

The raw ``task_topo`` is kept intact.  The recovery overlay expands collapsed
LEAF--CORE projections and identifies parallel CORE forwarding stages. CORE
stage edges are never completed: only links observed in raw ``task_topo`` are
retained. Virtual SPINE sets are deliberately not real devices and must not be
used as propagation-label endpoints.

Examples::

    python scripts/reconstruct_collapsed_clos_topology.py \
        --input data/raw/pingmesh_labeled \
        --output .local/reconstructed_topology

    python scripts/reconstruct_collapsed_clos_topology.py \
        --input data/raw/pingmesh_labeled/pingmesh-8294294-全链路.json \
        --output .local/reconstructed_topology
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from Sys.RootCauseAnalyze.propagation.topology_context import (  # noqa: E402
    build_topology_context,
    parse_pod_number,
)


SCHEMA_VERSION = "clos-topology-reconstruction-v2"
_CASE_ID_RE = re.compile(r"(?:merged_)?pingmesh-(\d+)(?:-|$)", re.IGNORECASE)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}-{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def _canonical_role(role: Any, name: Any = "") -> str:
    explicit = _text(role).upper()
    aliases = {"TOR": "LEAF", "TOP_OF_RACK": "LEAF", "TOP-OF-RACK": "LEAF"}
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


def _case_id(path: Path, info: Mapping[str, Any]) -> str:
    # Prefer the stable pingmesh filename ID over task UUIDs embedded in
    # task_info; this keeps output names aligned with the existing case tree.
    match = _CASE_ID_RE.search(path.stem)
    if match:
        return match.group(1)
    for key in ("case_id", "csn", "task_id", "id"):
        value = _text(info.get(key))
        if value:
            return value
    return path.stem


def _load_raw_case(path: Path) -> tuple[str, Mapping[str, Any], Sequence[Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON: {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("JSON root must be an object")
    full_link = payload.get("full_link")
    if not isinstance(full_link, Mapping) and isinstance(payload.get("task_topo"), Mapping):
        full_link = payload
    if not isinstance(full_link, Mapping):
        raise ValueError("full_link is missing")
    info = full_link.get("task_info")
    if not isinstance(info, Mapping):
        info = {}
    task_topo = full_link.get("task_topo")
    topo_value = task_topo.get("value") if isinstance(task_topo, Mapping) else None
    if not isinstance(topo_value, list) or not topo_value:
        raise ValueError("full_link.task_topo.value is missing or empty")
    return _case_id(path, info), info, topo_value


def _normalise_nodes(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for raw in context.get("nodes", []):
        if not isinstance(raw, Mapping):
            continue
        device_id = _text(raw.get("device_id"))
        if not device_id:
            continue
        name = _text(raw.get("name")) or device_id
        pod_number = parse_pod_number(name)
        rows.append(
            {
                "device_id": device_id,
                "name": name,
                "topology_role": _canonical_role(raw.get("role"), name),
                "group_ids": list(raw.get("group_ids", [])),
                "segment_ids": list(raw.get("segment_ids", [])),
                "pod_number": pod_number,
                "pod_source": "device_name" if pod_number is not None else "unknown",
                "is_inferred": False,
                "annotation_selectable": True,
            }
        )
    return sorted(rows, key=lambda item: item["device_id"])


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
        for neighbor in sorted(adjacency.get(current, set())):
            if neighbor not in distances:
                distances[neighbor] = distances[current] + 1
                queue.append(neighbor)
    return distances


def _core_forwarding_overlay(
    display_nodes: list[dict[str, Any]],
    display_edges: list[dict[str, Any]],
    *,
    source_anchors: Sequence[str],
    sink_anchors: Sequence[str],
) -> dict[str, Any]:
    by_id = {item["device_id"]: item for item in display_nodes}
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
        grouped: dict[int, list[str]] = {}
        for device_id in shared_core_ids:
            grouped.setdefault(source_distances[device_id], []).append(device_id)
        stage_groups = [sorted(grouped[value]) for value in sorted(grouped)]
        status = "connected_observed_only"
    else:
        source_groups: dict[int, list[str]] = {}
        sink_groups: dict[int, list[str]] = {}
        for device_id in core_ids:
            if device_id in source_distances:
                source_groups.setdefault(source_distances[device_id], []).append(device_id)
            if device_id in sink_distances:
                sink_groups.setdefault(sink_distances[device_id], []).append(device_id)
        stage_groups.extend(sorted(source_groups[value]) for value in sorted(source_groups))
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
            by_id[device_id]["core_forwarding_layer_index"] = index
            by_id[device_id]["core_forwarding_layer_id"] = layer_id
            by_id[device_id]["core_forwarding_layer_role"] = layer_role
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
                rows = observed_pair_edges.get(tuple(sorted((endpoint_a, endpoint_b))), [])
                if rows:
                    observed_pairs.append((endpoint_a, endpoint_b))
                    observed_edge_ids.extend(
                        _text(row.get("edge_id"))
                        for row in rows
                        if _text(row.get("edge_id"))
                    )
        endpoint_coverage = (
            bool(observed_pairs)
            and {pair[0] for pair in observed_pairs} == set(left_ids)
            and {pair[1] for pair in observed_pairs} == set(right_ids)
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


def _reconstruct(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    *,
    info: Mapping[str, Any],
    source_anchors: Sequence[str],
    sink_anchors: Sequence[str],
) -> dict[str, Any]:
    observed_nodes = [dict(item) for item in nodes]
    observed_edges = [dict(item) for item in edges]
    by_id = {item["device_id"]: item for item in observed_nodes}

    pair_edges: dict[tuple[str, str], list[dict[str, Any]]] = {}
    projection_adjacency: dict[str, set[str]] = {}
    leaf_core_pairs: set[tuple[str, str]] = set()
    for edge in observed_edges:
        endpoint_a = _text(edge.get("endpoint_a"))
        endpoint_b = _text(edge.get("endpoint_b"))
        if not endpoint_a or not endpoint_b or endpoint_a == endpoint_b:
            continue
        key = tuple(sorted((endpoint_a, endpoint_b)))
        pair_edges.setdefault(key, []).append(edge)
        role_a = by_id.get(endpoint_a, {}).get("topology_role")
        role_b = by_id.get(endpoint_b, {}).get("topology_role")
        if {role_a, role_b} == {"LEAF", "CORE"}:
            leaf_core_pairs.add(key)
            projection_adjacency.setdefault(endpoint_a, set()).add(endpoint_b)
            projection_adjacency.setdefault(endpoint_b, set()).add(endpoint_a)

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

    source_set, sink_set = set(source_anchors), set(sink_anchors)
    source_pod, sink_pod = _text(info.get("source_pod")), _text(info.get("sink_pod"))
    display_nodes = list(observed_nodes)
    display_edges = [
        {**edge, "is_inferred": False, "annotation_selectable": True}
        for edge in observed_edges
        if tuple(sorted((_text(edge.get("endpoint_a")), _text(edge.get("endpoint_b")))))
        not in leaf_core_pairs
    ]
    reconstructed_paths: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []

    for component in sorted(components, key=lambda value: tuple(sorted(value))):
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
        context_labels: list[str] = []
        if set(leaves) & source_set:
            context_labels.append(source_pod or "source")
        if set(leaves) & sink_set:
            context_labels.append(sink_pod or "sink")
        context_label = " / ".join(dict.fromkeys(context_labels))
        virtual_id = _stable_id("VSPINE", *sorted(component))
        pod_label = f"Pod {pod_number}" if pod_number is not None else context_label
        display_nodes.append(
            {
                "device_id": virtual_id,
                "name": f"隐藏 SPINE 集合（{pod_label}）" if pod_label else "隐藏 SPINE 集合",
                "topology_role": "SPINE_SET",
                "group_ids": [],
                "segment_ids": [],
                "pod_number": pod_number,
                "pod_source": "device_name_component" if pod_number is not None else "endpoint_context",
                "is_inferred": True,
                "annotation_selectable": False,
                "inference_kind": "collapsed_spine_set",
                "inference_confidence": "structural",
                "inference_note": (
                    "由 LEAF—CORE 直连按 Clos 层级展开；代表一个或多个被省略的 SPINE，"
                    "真实设备数量、名称和管理 IP 未知。"
                ),
            }
        )

        for endpoint in [*leaves, *cores]:
            raw_projection_edge_ids = sorted(
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
                    "raw_projection_edge_ids": raw_projection_edge_ids,
                }
            )

        projected_pairs = 0
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
                projected_pairs += 1
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
                "projected_pair_count": projected_pairs,
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
    pod_assignments = [
        {
            "device_id": item["device_id"],
            "name": item["name"],
            "topology_role": item["topology_role"],
            "pod_number": item.get("pod_number"),
            "pod_source": item.get("pod_source", "unknown"),
        }
        for item in sorted(observed_nodes, key=lambda row: row["device_id"])
    ]
    return {
        "observed_topology": {"nodes": observed_nodes, "edges": observed_edges},
        "recovered_topology": {
            "nodes": sorted(display_nodes, key=lambda item: item["device_id"]),
            "edges": sorted(display_edges, key=lambda item: _text(item.get("edge_id"))),
        },
        "reconstructed_paths": reconstructed_paths,
        "core_forwarding_layers": core_forwarding["layers"],
        "core_layer_connections": core_forwarding["connections"],
        "pod_assignments": pod_assignments,
        "diagnostics": {
            "status": (
                "partial_structural_reconstruction"
                if inferred_structure
                else "incomplete_observed_topology"
                if incomplete_core_fabric
                else "not_needed"
            ),
            "method": "clos_layered_fabric_v2",
            "observed_node_count": len(observed_nodes),
            "observed_edge_count": len(observed_edges),
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
                "恢复拓扑仅用于结构理解；虚拟节点不是原始设备，原始 task_topo 才是事实边界。"
                if inferred_structure
                else "源侧与目的侧 CORE 子图在观测拓扑中断开；缺失连接保持未知，未生成推测 CORE 边。"
                if incomplete_core_fabric
                else ""
            ),
        },
    }


def reconstruct_file(path: Path) -> dict[str, Any]:
    case_id, info, topo_value = _load_raw_case(path)
    context = build_topology_context(topo_value, info)
    nodes = _normalise_nodes(context)
    result = _reconstruct(
        nodes,
        context.get("edges", []),
        info=info,
        source_anchors=context.get("source_anchors", []),
        sink_anchors=context.get("sink_anchors", []),
    )
    result.update(
        {
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "source_file": path.name,
            "info": {
                key: info.get(key)
                for key in (
                    "source_ip",
                    "sink_ip",
                    "source_pod",
                    "sink_pod",
                    "source_az",
                    "sink_az",
                    "alarm_time",
                )
                if key in info
            },
            "source_anchors": list(context.get("source_anchors", [])),
            "sink_anchors": list(context.get("sink_anchors", [])),
        }
    )
    return result


def _input_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise ValueError(f"input path does not exist: {path}")
    return sorted(
        candidate
        for candidate in path.rglob("*.json")
        if candidate.is_file() and not candidate.name.endswith(".reconstructed.json")
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="恢复裁剪 Pingmesh Clos 拓扑的结构推测层")
    parser.add_argument("--input", required=True, type=Path, help="原始 full_link JSON 或 JSON 目录")
    parser.add_argument("--output", required=True, type=Path, help="输出目录（每个输入 case 一个 JSON）")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有输出文件")
    args = parser.parse_args(argv)

    try:
        files = _input_files(args.input.resolve())
    except ValueError as exc:
        parser.error(str(exc))
    if not files:
        parser.error(f"no JSON files found under {args.input}")

    args.output.resolve().mkdir(parents=True, exist_ok=True)
    failures = 0
    written = 0
    for path in files:
        try:
            result = reconstruct_file(path)
            destination = args.output.resolve() / f"{result['case_id']}.reconstructed.json"
            if destination.exists() and not args.overwrite:
                raise ValueError(f"output exists (use --overwrite): {destination}")
            destination.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            diagnostics = result["diagnostics"]
            print(
                f"{result['case_id']}: {diagnostics['status']} | "
                f"nodes {diagnostics['observed_node_count']} + "
                f"{diagnostics['virtual_node_count']} hidden set(s) | "
                f"CORE stages {len(diagnostics['core_forwarding_layers'])} | "
                f"inferred CORE links {diagnostics['inferred_core_edge_count']} | "
                f"projected LEAF-CORE pairs {diagnostics['projected_raw_pair_count']}"
            )
            written += 1
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failures += 1
            print(f"ERROR {path.name}: {exc}", file=sys.stderr)

    print(f"written={written} failed={failures} output={args.output.resolve()}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
