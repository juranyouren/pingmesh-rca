"""Adjacency, all-edges arrowhead endpoints, and SHD-1 on a fixed device domain."""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
import random

from Baseline.common.graph import is_dag

METRICS = ("Adj-P", "Adj-R", "Adj-F1", "AH-P", "AH-R", "AH-F1", "SHD")


def pair(u, v):
    return tuple(sorted((u, v)))


def pairs(rows, devices):
    output = set()
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError("Expected [source, target] pairs")
        u, v = row
        if u not in devices or v not in devices or u == v:
            raise ValueError("Label pair outside fixed input device domain or self-loop")
        output.add((u, v))
    return output


def graph_sets(graph):
    adj, heads = set(), set()
    for e in graph.get("edges", []):
        u, v = e["source"], e["target"]
        adj.add(pair(u, v))
        if e.get("directed", True):
            # (u,v) is the arrowhead at v on unordered pair {u,v}.
            heads.add((u, v))
    return adj, heads


def label_sets(label, case):
    devices = {d["id"] for d in case["devices"]}
    if "positive_edges" not in label:
        return None
    gold_heads = pairs(label["positive_edges"], devices)
    if not is_dag(gold_heads):
        raise ValueError("RQ1 reference must be a simple directed acyclic device graph")
    gold_adj = {pair(*e) for e in gold_heads}
    physical = {pair(e["u"], e["v"]) for e in case["physical_links"]}
    if not gold_adj <= physical:
        raise ValueError("Positive reference edge is absent from raw topology; reconcile labels/inputs")
    complete = label.get("graph_complete", False)
    universe = set(combinations(sorted(devices), 2))
    if complete:
        if label.get("positive_adjacencies") or label.get("allowed_edges"):
            raise ValueError("Complete DAG labels cannot contain unoriented or optional relations")
        return gold_adj, gold_heads, universe, {(u, v) for u in devices for v in devices if u != v}

    # Legacy directed masks do not imply that reverse orientation is known.
    known_heads = pairs(label.get("known_edge_mask", []), devices)
    if not gold_heads <= known_heads:
        raise ValueError("Partial positive_edges must belong to known_edge_mask")
    explicit_adj = {pair(*e) for e in pairs(label.get("positive_adjacencies", []), devices)}
    explicit_mask = {pair(*e) for e in pairs(label.get("known_adjacency_mask", []), devices)}
    if not explicit_adj <= explicit_mask:
        raise ValueError("positive_adjacencies require known_adjacency_mask")
    if not explicit_adj <= physical:
        raise ValueError("Positive adjacency is absent from raw topology")
    known_adj = gold_adj | {pair(u, v) for u, v in known_heads if (v, u) in known_heads}
    gold_adj |= explicit_adj
    if any((u, v) in known_heads and (v, u) in known_heads and
           (u, v) not in gold_heads and (v, u) not in gold_heads for u, v in gold_adj):
        raise ValueError("Positive adjacency contradicts two known-negative directions")
    known_adj |= explicit_mask
    allowed = {pair(*e) for e in pairs(label.get("allowed_edges", []), devices)}
    if allowed & gold_adj:
        raise ValueError("A relation cannot be both positive and optional")
    return gold_adj, gold_heads, known_adj - allowed, {e for e in known_heads if pair(*e) not in allowed}


def prf(pred, gold):
    tp, fp, fn = len(pred & gold), len(pred - gold), len(gold - pred)
    p = tp / (tp + fp) if tp + fp else float(not gold)
    r = tp / (tp + fn) if tp + fn else 1.0
    return (p, r, 2 * p * r / (p + r) if p + r else 0.0), {"tp": tp, "fp": fp, "fn": fn}


def shd_one(pred_adj, pred_heads, gold_adj, gold_heads):
    """Simple relation-state edit: addition/deletion/reorientation each costs 1.

    For directed DAGs this is ordinary SHD with reversal cost 1. For an
    undirected or two-arrow relation, replacement by the reference orientation
    costs 1. This mixed-graph extension is explicit, not a guessed direction.
    """
    return len(pred_adj ^ gold_adj) + sum(
        {h for h in pred_heads if pair(*h) == p} != {h for h in gold_heads if pair(*h) == p}
        for p in pred_adj & gold_adj)


def evaluate(prediction, label, case):
    scope = label_sets(label, case)
    row = {"case_id": case["case_id"], "group_id": case["group_id"],
           "status": prediction["status"], "label_scope": "complete" if label.get("graph_complete") else "partial",
           "metrics": {}, "counts": {}}
    if scope is None:
        row["label_scope"] = "unavailable"
        return row
    gold_adj, gold_heads, adj_mask, head_mask = scope
    adj, heads = graph_sets(prediction.get("device_graph") or {})
    success = prediction["status"] == "ok"
    for prefix, pred, gold, mask in (("Adj", adj, gold_adj, adj_mask), ("AH", heads, gold_heads, head_mask)):
        if not mask and not label.get("graph_complete"):
            continue
        values, counts = prf(pred & mask, gold & mask)
        row["metrics"].update(zip((prefix + "-P", prefix + "-R", prefix + "-F1"), values if success else (0.0, 0.0, 0.0)))
        # A failed prediction is not an empty graph; confusion counts are unavailable.
        row["counts"][prefix] = counts if success else None
    if success and label.get("graph_complete"):
        row["metrics"]["SHD"] = shd_one(adj, heads, gold_adj, gold_heads)
    row["shd_status"] = "available" if "SHD" in row["metrics"] else "prediction_failed" if not success else "partial_reference"
    allowed = {pair(*e) for e in label.get("allowed_edges", [])}
    row["unknown_predictions"] = {"adjacencies": len(adj - adj_mask - allowed),
                                   "arrowheads": sum(pair(*h) not in allowed for h in heads - head_mask)}
    row["neutral_predictions"] = {"adjacencies": len(adj & allowed),
                                   "arrowheads": sum(pair(*h) in allowed for h in heads)}
    row["scoring_domain"] = {"adjacencies": len(adj_mask), "arrowheads": len(head_mask)}
    return row


def aggregate(rows, *, bootstrap_samples=1000, seed=20260920):
    """Average windows within incident, then average incidents (equal weight)."""
    out = {"n_cases": len(rows), "n_groups": len({r["group_id"] for r in rows}),
           "statuses": dict(Counter(r["status"] for r in rows)), "metrics": {}}
    for metric in METRICS:
        groups = defaultdict(list)
        for row in rows:
            if metric in row["metrics"]:
                groups[row["group_id"]].append(row["metrics"][metric])
        values = [sum(groups[g]) / len(groups[g]) for g in sorted(groups)]
        ci = None
        if len(values) >= 2 and bootstrap_samples:
            rng = random.Random(seed)
            samples = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(bootstrap_samples))
            ci = [samples[int(q * (len(samples) - 1))] for q in (0.025, 0.975)]
        mean = sum(values) / len(values) if values else None
        # Never make a method with failed graphs look better by dropping SHD failures.
        withheld = metric == "SHD" and any(r["status"] != "ok" for r in rows)
        out["metrics"][metric] = {"mean": None if withheld else mean, "ci95": None if withheld else ci,
                                   "n_cases": sum(map(len, groups.values())), "n_groups": len(groups),
                                   "successful_only_mean": mean if metric == "SHD" else None,
                                   "status": "withheld_due_to_failures" if withheld else "available" if values else "unavailable"}
    return out
