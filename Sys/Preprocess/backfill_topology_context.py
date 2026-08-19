from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

if __package__ in (None, ""):
    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

from Sys.RootCauseAnalyze.propagation.topology_context import (
    TOPOLOGY_SCHEMA_VERSION,
    build_topology_context,
)
from Sys.utils.case_utils import find_full_link_file


REPORT_SCHEMA_VERSION = "topology-context-backfill-report-v1"
SUCCESS_STATUSES = {"generated", "unchanged", "overwritten"}


def _case_dirs(cases_root: str) -> List[str]:
    rows = []
    for dirpath, _dirnames, filenames in os.walk(cases_root):
        if "info.json" in filenames and find_full_link_file(dirpath, filenames):
            rows.append(os.path.abspath(dirpath))
    return sorted(rows)


def _case_id_from_raw_name(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    match = re.search(r"(?:merged_)?pingmesh-(\d+)(?:-|$)", stem, flags=re.I)
    if match:
        return match.group(1)
    return stem if stem.isdigit() else ""


def _payload_case_id(payload: Mapping[str, Any]) -> str:
    full_link = payload.get("full_link")
    if not isinstance(full_link, Mapping) and isinstance(payload.get("task_topo"), Mapping):
        full_link = payload
    if isinstance(full_link, Mapping):
        task_info = full_link.get("task_info")
        if isinstance(task_info, Mapping):
            for key in ("csn", "case_id"):
                value = str(task_info.get(key, "") or "").strip()
                if value:
                    return value
    for key in ("csn", "case_id"):
        value = str(payload.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _load_json_strict(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _raw_index(raw_root: str) -> Tuple[Dict[str, List[str]], List[str]]:
    index: Dict[str, List[str]] = defaultdict(list)
    unreadable: List[str] = []
    unmatched = []
    for dirpath, _dirnames, filenames in os.walk(raw_root):
        for filename in sorted(filenames):
            if not filename.lower().endswith(".json"):
                continue
            path = os.path.abspath(os.path.join(dirpath, filename))
            case_id = _case_id_from_raw_name(path)
            if case_id:
                index[case_id].append(path)
            else:
                unmatched.append(path)

    for path in unmatched:
        try:
            payload = _load_json_strict(path)
        except Exception:
            unreadable.append(path)
            continue
        if isinstance(payload, Mapping):
            case_id = _payload_case_id(payload)
            if case_id:
                index[case_id].append(path)
    return {key: sorted(values) for key, values in index.items()}, sorted(unreadable)


def _raw_components(payload: Mapping[str, Any]) -> Tuple[Mapping[str, Any], Sequence[Any]]:
    full_link = payload.get("full_link")
    if not isinstance(full_link, Mapping) and isinstance(payload.get("task_topo"), Mapping):
        full_link = payload
    if not isinstance(full_link, Mapping):
        raise ValueError("full_link is missing")
    task_info = full_link.get("task_info")
    if not isinstance(task_info, Mapping):
        raise ValueError("full_link.task_info is missing")
    task_topo = full_link.get("task_topo")
    topo_value = task_topo.get("value") if isinstance(task_topo, Mapping) else None
    if not isinstance(topo_value, list) or not topo_value:
        raise ValueError("full_link.task_topo.value is missing or empty")
    return task_info, topo_value


def _segments(topo_value: Sequence[Any]) -> Iterable[Mapping[str, Any]]:
    for raw_group in topo_value:
        group = raw_group if isinstance(raw_group, list) else [raw_group]
        for segment in group:
            if isinstance(segment, Mapping):
                yield segment


def _canonical_edge_key(
    source: str,
    source_port: str,
    target: str,
    target_port: str,
) -> Tuple[str, str, str, str]:
    if (source, source_port) <= (target, target_port):
        return source, source_port, target, target_port
    return target, target_port, source, source_port


def _raw_nodes_and_edges(
    topo_value: Sequence[Any],
) -> Tuple[set[str], set[Tuple[str, str, str, str]]]:
    nodes: set[str] = set()
    edges: set[Tuple[str, str, str, str]] = set()
    for segment in _segments(topo_value):
        raw_nodes = segment.get("nodes", [])
        for raw in raw_nodes if isinstance(raw_nodes, list) else []:
            if not isinstance(raw, Mapping):
                continue
            device_id = str(raw.get("mgmt_ip", raw.get("ip", "")) or "")
            if device_id:
                nodes.add(device_id)
        raw_links = segment.get("links", [])
        for raw in raw_links if isinstance(raw_links, list) else []:
            if not isinstance(raw, Mapping):
                continue
            source = str(raw.get("src_ip", "") or "")
            target = str(raw.get("dst_ip", "") or "")
            if not source or not target or source == target:
                continue
            edges.add(
                _canonical_edge_key(
                    source,
                    str(raw.get("src_port_name", "") or ""),
                    target,
                    str(raw.get("dst_port_name", "") or ""),
                )
            )
    return nodes, edges


def _context_nodes_and_edges(
    context: Mapping[str, Any],
) -> Tuple[set[str], set[Tuple[str, str, str, str]], List[str]]:
    nodes = {
        str(item.get("device_id"))
        for item in context.get("nodes", [])
        if isinstance(item, Mapping) and item.get("device_id")
    }
    edges: set[Tuple[str, str, str, str]] = set()
    edge_ids = []
    for item in context.get("edges", []):
        if not isinstance(item, Mapping):
            continue
        edges.add(
            _canonical_edge_key(
                str(item.get("endpoint_a", "") or ""),
                str(item.get("endpoint_a_port", "") or ""),
                str(item.get("endpoint_b", "") or ""),
                str(item.get("endpoint_b_port", "") or ""),
            )
        )
        edge_id = str(item.get("edge_id", "") or "")
        if edge_id:
            edge_ids.append(edge_id)
    return nodes, edges, edge_ids


def _validate_context(
    context: Mapping[str, Any], topo_value: Sequence[Any]
) -> Dict[str, int]:
    if context.get("schema_version") != TOPOLOGY_SCHEMA_VERSION:
        raise ValueError("unsupported topology context schema")
    diagnostics = context.get("diagnostics")
    if not isinstance(diagnostics, Mapping) or diagnostics.get("source") != "raw_task_topo":
        raise ValueError("topology context is not sourced from raw_task_topo")
    raw_nodes, raw_edges = _raw_nodes_and_edges(topo_value)
    context_nodes, context_edges, edge_ids = _context_nodes_and_edges(context)
    if context_nodes != raw_nodes:
        raise ValueError("topology context nodes differ from raw task_topo")
    if context_edges != raw_edges:
        raise ValueError("topology context edges differ from raw task_topo")
    if len(edge_ids) != len(context_edges) or len(set(edge_ids)) != len(edge_ids):
        raise ValueError("topology context edge IDs are missing or duplicated")
    usable_edges = sum(
        1
        for endpoint_a, _port_a, endpoint_b, _port_b in context_edges
        if endpoint_a in context_nodes and endpoint_b in context_nodes
    )
    return {
        "node_count": len(context_nodes),
        "edge_count": len(context_edges),
        "usable_device_edge_count": usable_edges,
    }


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _without_provenance(context: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(dict(context))
    diagnostics = normalized.get("diagnostics")
    if isinstance(diagnostics, dict):
        diagnostics.pop("provenance", None)
    return normalized


def _atomic_save_json(path: str, payload: Any) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=parent,
            prefix=".topology-context-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def _build_case_context(case_id: str, raw_path: str) -> Tuple[Dict[str, Any], Dict[str, int]]:
    payload = _load_json_strict(raw_path)
    if not isinstance(payload, Mapping):
        raise ValueError("raw JSON root must be an object")
    payload_case_id = _payload_case_id(payload)
    if payload_case_id and payload_case_id != case_id:
        raise ValueError(
            f"raw payload case ID {payload_case_id} does not match case {case_id}"
        )
    task_info, topo_value = _raw_components(payload)
    context = build_topology_context(topo_value, task_info)
    counts = _validate_context(context, topo_value)
    context["diagnostics"] = {
        **dict(context.get("diagnostics", {})),
        "provenance": {
            "case_id": case_id,
            "raw_file": os.path.basename(raw_path),
            "raw_sha256": _sha256(raw_path),
            "generator": "backfill_topology_context.py",
        },
    }
    return context, counts


def backfill_topology_contexts(
    cases_root: str,
    raw_root: str,
    *,
    write: bool = False,
    overwrite: bool = False,
) -> Dict[str, Any]:
    cases_root = os.path.abspath(cases_root)
    raw_root = os.path.abspath(raw_root)
    if not os.path.isdir(cases_root):
        raise ValueError(f"cases root does not exist: {cases_root}")
    if not os.path.isdir(raw_root):
        raise ValueError(f"raw root does not exist: {raw_root}")

    case_dirs = _case_dirs(cases_root)
    case_paths_by_id: Dict[str, List[str]] = defaultdict(list)
    for case_dir in case_dirs:
        case_paths_by_id[os.path.basename(os.path.normpath(case_dir))].append(case_dir)
    raw_paths_by_id, unreadable_unmatched = _raw_index(raw_root)

    rows: List[Dict[str, Any]] = []
    for case_id in sorted(case_paths_by_id):
        case_paths = case_paths_by_id[case_id]
        if len(case_paths) != 1:
            for case_dir in case_paths:
                rows.append(
                    {
                        "case_id": case_id,
                        "case_dir": case_dir,
                        "status": "duplicate_case",
                        "reason": "more than one case directory has this basename",
                    }
                )
            continue
        case_dir = case_paths[0]
        raw_paths = raw_paths_by_id.get(case_id, [])
        if not raw_paths:
            rows.append(
                {
                    "case_id": case_id,
                    "case_dir": case_dir,
                    "status": "missing_raw",
                    "reason": "no raw JSON matched this case ID",
                }
            )
            continue
        if len(raw_paths) != 1:
            rows.append(
                {
                    "case_id": case_id,
                    "case_dir": case_dir,
                    "status": "duplicate_raw",
                    "reason": f"{len(raw_paths)} raw JSON files matched this case ID",
                    "raw_files": [os.path.basename(path) for path in raw_paths],
                }
            )
            continue

        raw_path = raw_paths[0]
        try:
            context, counts = _build_case_context(case_id, raw_path)
        except Exception as exc:
            rows.append(
                {
                    "case_id": case_id,
                    "case_dir": case_dir,
                    "raw_file": os.path.basename(raw_path),
                    "status": "invalid_raw",
                    "reason": str(exc),
                }
            )
            continue

        output_path = os.path.join(case_dir, "topology_context.json")
        had_output = os.path.exists(output_path)
        existing = None
        if had_output:
            try:
                existing = _load_json_strict(output_path)
            except Exception:
                existing = None
        common = {
            "case_id": case_id,
            "case_dir": case_dir,
            "raw_file": os.path.basename(raw_path),
            **counts,
        }
        if isinstance(existing, Mapping) and _without_provenance(existing) == _without_provenance(context):
            rows.append({**common, "status": "unchanged"})
            continue
        if had_output and not overwrite:
            rows.append(
                {
                    **common,
                    "status": "conflict",
                    "reason": "existing topology_context.json differs; use --overwrite",
                }
            )
            continue
        if not write:
            rows.append(
                {
                    **common,
                    "status": "would_overwrite" if had_output else "would_generate",
                }
            )
            continue
        try:
            _atomic_save_json(output_path, context)
        except Exception as exc:
            rows.append({**common, "status": "write_failed", "reason": str(exc)})
            continue
        rows.append({**common, "status": "overwritten" if had_output else "generated"})

    status_counts = Counter(str(row.get("status", "unknown")) for row in rows)
    valid_context_count = sum(
        count for status, count in status_counts.items() if status in SUCCESS_STATUSES
    )
    complete = bool(rows) and valid_context_count == len(rows)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "cases_root": cases_root,
        "raw_root": raw_root,
        "write": write,
        "overwrite": overwrite,
        "case_count": len(case_dirs),
        "indexed_raw_case_count": len(raw_paths_by_id),
        "unreadable_unmatched_raw_count": len(unreadable_unmatched),
        "valid_context_count": valid_context_count,
        "complete": complete,
        "status_counts": dict(sorted(status_counts.items())),
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill case topology_context.json files from raw full_link.task_topo."
    )
    parser.add_argument("--cases-root", required=True)
    parser.add_argument("--raw-root", required=True)
    parser.add_argument("--report", default=None)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Exit nonzero unless every discovered case has a verified context.",
    )
    args = parser.parse_args()

    report = backfill_topology_contexts(
        args.cases_root,
        args.raw_root,
        write=args.write,
        overwrite=args.overwrite,
    )
    if args.report:
        _atomic_save_json(args.report, report)
    summary = {key: value for key, value in report.items() if key != "cases"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.require_complete and not report["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
