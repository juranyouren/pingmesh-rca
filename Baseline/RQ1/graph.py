"""Topology-only projection retains undecided orientations and audit records."""
from __future__ import annotations

import math

from Baseline.common.graph import adapt_graph


def project(native, case):
    ids = {d["id"] for d in case["devices"]}
    mapping = {n["id"]: n.get("device_id", n["id"]) for n in native.get("nodes", [])}
    mapping.update({d: mapping.get(d, d) for d in ids})
    physical = {frozenset((e["u"], e["v"])) for e in case["physical_links"]}
    kept, removed = {}, []
    for index, e in enumerate(native.get("edges", [])):
        u, v = mapping.get(e.get("source")), mapping.get(e.get("target"))
        if u not in ids or v not in ids:
            reason = "unmapped_device"
        elif u == v:
            reason = "device_self_loop"
        elif frozenset((u, v)) not in physical:
            reason = "nonphysical"
        else:
            reason = None
        if reason:
            removed.append({"native_index": index, "reason": reason})
            continue
        if not isinstance(e.get("directed", True), bool):
            raise ValueError("directed must be boolean")
        directed = e.get("directed", True)
        score = float(e.get("score", 1.0))
        if not math.isfinite(score) or score < 0:
            raise ValueError("Non-finite or negative native edge support")
        if not directed:
            u, v = sorted((u, v))
        key = (u, v, directed)
        row = kept.setdefault(key, {"source": u, "target": v, "directed": directed,
                                    "score": score, "native_edge_indices": [], "evidence_ids": []})
        row["score"] = max(row["score"], score)
        row["native_edge_indices"].append(index)
        row["evidence_ids"] = sorted(set(row["evidence_ids"]) | set(e.get("evidence_ids", [])))
    return {"nodes": sorted(ids), "edges": [kept[k] for k in sorted(kept)], "removed": removed,
            "status": "ok", "adapter_version": "rq1-topology-only-v1"}


def device_graph(native, case, root, condition, view):
    topology = project(native, case)
    if view == "topology":
        return topology
    # Existing baseline adapter is intentionally separate from Ours' decoder.
    graph = adapt_graph({**topology, "nodes": [{"id": d} for d in topology["nodes"]]},
                        case, root, condition=condition)
    graph["topology_projection"] = topology
    return graph
