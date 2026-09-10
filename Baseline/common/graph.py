"""Deterministic device projection; never invents a path or an orientation."""
from __future__ import annotations

import math
from collections import Counter, defaultdict

ADAPTER_VERSION = "device_greedy_v1"


def reachable(root, edges):
    adjacency = defaultdict(set)
    for u, v in edges:
        adjacency[u].add(v)
    seen, stack = {root}, [root]
    while stack:
        for v in adjacency[stack.pop()]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def is_dag(edges):
    adjacency, indegree = defaultdict(set), defaultdict(int)
    for u, v in set(edges):
        adjacency[u].add(v)
        indegree[v] += 1
        indegree.setdefault(u, 0)
    pending = [u for u, n in indegree.items() if n == 0]
    count = 0
    while pending:
        count += 1
        for v in adjacency[pending.pop()]:
            indegree[v] -= 1
            if indegree[v] == 0:
                pending.append(v)
    return count == len(indegree)


def graph_validity(graph, incident, root):
    devices = {row["id"] for row in incident["devices"]}
    pairs = {(edge["source"], edge["target"]) for edge in graph.get("edges", [])}
    physical = {frozenset((e["u"], e["v"])) for e in incident["physical_links"]}
    nodes = {n if isinstance(n, str) else n["id"] for n in graph.get("nodes", [])}
    return {"dag": is_dag(pairs), "physical_edge_rate": sum(u != v and frozenset((u, v)) in physical for u, v in pairs) / len(pairs) if pairs else 1.0,
            "known_nodes": nodes <= devices and {x for pair in pairs for x in pair} <= nodes,
            "root_reachable": root in nodes and nodes <= reachable(root, pairs),
            "root_has_no_parent": all(v != root for _, v in pairs)}


def adapt_graph(native, incident, root, *, condition="oracle"):
    if condition not in {"oracle", "own_prediction", "shared_prediction"}:
        raise ValueError("Unknown root condition")
    devices = {n["id"] for n in incident["devices"]}
    base = {"adapter_version": ADAPTER_VERSION, "root": root, "graph_condition": condition, "nodes": [], "edges": [], "raw_projection": [], "removed": [], "undirected": []}
    if native.get("status", "ok") != "ok":
        return {**base, "status": native.get("status", "runtime_failure"), "reason": "native_graph_unavailable"}
    if root not in devices:
        return {**base, "status": "input_ineligible", "reason": "root_not_in_candidate_devices"}
    mapping = {n["id"]: n.get("device_id", n["id"]) for n in native.get("nodes", [])}
    mapping.update({d: mapping.get(d, d) for d in devices})
    projection = {}
    for index, edge in enumerate(native.get("edges", [])):
        u, v = mapping.get(edge.get("source")), mapping.get(edge.get("target"))
        detail = {"native_edge_index": index, "source": u, "target": v}
        if edge.get("directed", True) is not True:
            base["undirected"].append({**detail, "native_edge": edge})
            continue
        if u not in devices or v not in devices:
            base["removed"].append({**detail, "reason": "unmapped_device"})
            continue
        if u == v:
            base["removed"].append({**detail, "reason": "device_self_loop"})
            continue
        try:
            score = float(edge.get("score", 1.0))
        except (TypeError, ValueError):
            score = float("nan")
        if not math.isfinite(score) or score <= 0:
            base["removed"].append({**detail, "reason": "nonpositive_or_invalid_support"})
            continue
        row = projection.setdefault((u, v), {"source": u, "target": v, "score": score, "native_edge_indices": [], "evidence_ids": []})
        row["score"] = max(score, row["score"])
        row["native_edge_indices"].append(index)
        row["evidence_ids"] = sorted(set(row["evidence_ids"]) | set(edge.get("evidence_ids", [])))
    base["raw_projection"] = [projection[k] for k in sorted(projection)]
    raw_pairs = set(projection)
    base["projection_diagnostics"] = {"is_dag": is_dag(raw_pairs), "bidirectional_pairs": sum((v, u) in raw_pairs for u, v in raw_pairs) // 2,
                                      "unreachable_nodes": sorted(({x for pair in raw_pairs for x in pair} | {root}) - reachable(root, raw_pairs))}
    base["raw_validity"] = graph_validity({"edges": base["raw_projection"],
                                           "nodes": sorted({x for pair in raw_pairs for x in pair} | {root})}, incident, root)
    physical = {frozenset((e["u"], e["v"])) for e in incident["physical_links"]}
    chosen = []
    for pair, row in sorted(projection.items(), key=lambda kv: (-kv[1]["score"], *kv[0])):
        u, v = pair
        reason = "nonphysical" if frozenset(pair) not in physical else "incoming_root" if v == root else "cycle" if u in reachable(v, [(e["source"], e["target"]) for e in chosen]) else None
        if reason:
            base["removed"].append({**row, "reason": reason})
        else:
            chosen.append(row)
    reached = reachable(root, [(e["source"], e["target"]) for e in chosen])
    base["edges"] = [row for row in chosen if row["source"] in reached]
    base["removed"].extend({**row, "reason": "not_root_reachable"} for row in chosen if row["source"] not in reached)
    base["nodes"] = sorted(reached)
    base["status"] = "ok"
    base["validity"] = graph_validity(base, incident, root)
    base["removal_counts"] = dict(Counter(row["reason"] for row in base["removed"]))
    base["projected_edge_retention"] = len(base["edges"]) / len(raw_pairs) if raw_pairs else 1.0
    return base
