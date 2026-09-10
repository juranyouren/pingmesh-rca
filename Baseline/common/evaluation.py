"""Scores explicit canonical labels; legacy 'possible' labels are never guessed."""
from __future__ import annotations

import random
from collections import Counter, defaultdict

from .io import read_json
from .graph import graph_validity
from .schema import STATUSES, input_fingerprint


def _pairs(rows):
    return {(str(e[0]), str(e[1])) for e in rows}


def load_labels(path):
    payload = read_json(path)
    rows = payload.get("labels", [payload]) if isinstance(payload, dict) else payload
    output = {}
    for row in rows:
        case_id = row.get("case_id")
        if not case_id or case_id in output:
            raise ValueError("Canonical labels need unique case_id values")
        if "graph_complete" in row and not isinstance(row["graph_complete"], bool):
            raise ValueError("graph_complete must be an explicit boolean")
        if row.get("root_status", "unknown") not in {"confirmed", "unknown", "ambiguous"}:
            raise ValueError("root_status must be confirmed/unknown/ambiguous")
        if row.get("root_status") == "confirmed" and (not isinstance(row.get("root_device"), str) or not row["root_device"]):
            raise ValueError("Confirmed root needs one nonempty device ID")
        for field in ("positive_nodes", "known_node_mask"):
            if not isinstance(row.get(field, []), list) or any(not isinstance(n, str) or not n for n in row.get(field, [])):
                raise ValueError(f"{field} requires nonempty string IDs")
        if row.get("graph_complete") and ("positive_edges" not in row or "positive_nodes" not in row):
            raise ValueError("Complete graph labels require explicit positive_edges and positive_nodes, even if empty")
        for field in ("positive_edges", "known_edge_mask", "allowed_edges"):
            values = row.get(field, [])
            if any(not isinstance(e, list) or len(e) != 2 or not all(isinstance(x, str) and x for x in e) for e in values):
                raise ValueError(f"{field} requires [source, target] string pairs")
        if not row.get("graph_complete", False):
            if not _pairs(row.get("positive_edges", [])) <= _pairs(row.get("known_edge_mask", [])):
                raise ValueError("Partial graph positive_edges must be in the explicit known_edge_mask")
            if not set(row.get("positive_nodes", [])) <= set(row.get("known_node_mask", [])):
                raise ValueError("Partial graph positive_nodes must be in the known_node_mask")
        elif row.get("allowed_edges"):
            raise ValueError("Optional allowed edges require partial/set-valued evaluation, not exact graph_complete")
        if row.get("root_device") and row.get("root_status") != "confirmed":
            raise ValueError("Root evaluation requires an explicitly confirmed single root")
        output[case_id] = row
    return output


def _scores(predicted, reference):
    hit = len(predicted & reference)
    precision = hit / len(predicted) if predicted else float(not reference)
    recall = hit / len(reference) if reference else 1.0
    return {"precision": precision, "recall": recall, "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def evaluate_case(prediction, label, incident, task="root"):
    case_id = incident["case_id"]
    if prediction.get("case_id") != case_id or label.get("case_id") != case_id:
        raise ValueError("Prediction, label and input case IDs differ")
    if task not in {"root", "oracle", "shared", "full"}:
        raise ValueError("Unknown evaluation task")
    if prediction.get("status") not in STATUSES:
        raise ValueError("Unknown prediction status")
    if prediction.get("task", task) != task:
        raise ValueError("Prediction task differs from evaluation task")
    if prediction.get("input_hash", input_fingerprint(incident)) != input_fingerprint(incident):
        raise ValueError("Prediction was generated on different input")
    root = label.get("root_device") if label.get("root_status") == "confirmed" else None
    success = prediction.get("status") == "ok"
    ranks = [row["device_id"] for row in prediction.get("root_ranking", [])]
    candidates = {d["id"] for d in incident["devices"]}
    if len(set(ranks)) != len(ranks) or not set(ranks) <= candidates:
        raise ValueError("Invalid root ranking: duplicate or out-of-domain device")
    result = {"case_id": case_id, "group_id": incident.get("group_id", case_id),
              "group_verified": incident.get("group_verified") is True,
              "status": prediction.get("status"), "metrics": {"failure": float(not success)}}
    metrics = result["metrics"]
    root_correct = bool(success and root and ranks and ranks[0] == root)
    if root and task in {"root", "full"}:
        position = ranks.index(root) + 1 if success and root in ranks else None
        metrics.update({f"top_{k}": float(position is not None and position <= k) for k in (1, 3, 5)})
        metrics.update(mrr=1 / position if position else 0.0, candidate_recall=float(root in candidates), returned_candidate_recall=float(success and root in ranks))
    if task == "root":
        return result
    graph = prediction.get("device_graph") or {}
    if graph.get("graph_condition") != {"oracle": "oracle", "shared": "shared_prediction", "full": "own_prediction"}[task]:
        if success:
            raise ValueError("Graph root condition does not match evaluation task")
    if task == "oracle" and (not root or graph.get("root") != root) and success:
        raise ValueError("Oracle graph must be conditioned on the confirmed root")
    if task == "full" and success and (not ranks or graph.get("root") != ranks[0]):
        raise ValueError("Full graph root differs from the method's Top-1")
    graph_success = success and graph.get("status") == "ok"
    validity = graph_validity(graph, incident, graph.get("root")) if graph_success else {}
    metrics.update({f"graph_{key}": float(validity.get(key, 0)) for key in
                    ("dag", "physical_edge_rate", "known_nodes", "root_reachable", "root_has_no_parent")})
    if graph_success and "raw_validity" in graph:
        metrics.update({f"raw_graph_{key}": float(value) for key, value in graph["raw_validity"].items()})
        metrics["projected_edge_retention"] = graph.get("projected_edge_retention", 1.0)
    if "positive_edges" not in label:
        result["graph_label_status"] = "unavailable"
        return result
    edges = {(e["source"], e["target"]) for e in graph.get("edges", [])}
    nodes = {n if isinstance(n, str) else n["id"] for n in graph.get("nodes", [])}
    gold_edges, gold_nodes = _pairs(label["positive_edges"]), set(label.get("positive_nodes", []))
    complete = label.get("graph_complete", False)
    allowed = _pairs(label.get("allowed_edges", [])) - gold_edges
    known_edges = _pairs(label.get("known_edge_mask", []))
    known_nodes = set(label.get("known_node_mask", []))
    edge_scope = complete or bool(known_edges - allowed)
    node_scope = complete or bool(known_nodes)
    result["graph_label_status"] = "complete" if complete else "partial" if edge_scope or node_scope else "unavailable"
    scored_edges = edges if complete else (edges & known_edges) - allowed
    scored_nodes = nodes if complete else nodes & known_nodes
    result["unknown_predictions"] = {"edges": len(edges - known_edges - allowed) if not complete else 0, "nodes": len(nodes - known_nodes) if not complete else 0}
    for prefix, predicted, gold in (("edge", scored_edges, gold_edges), ("node", scored_nodes, gold_nodes),
                                   ("node_without_root", scored_nodes - {root}, gold_nodes - {root})):
        if not (edge_scope if prefix == "edge" else node_scope):
            continue
        values = _scores(predicted, gold) if graph_success else dict(precision=0.0, recall=0.0, f1=0.0)
        metrics.update({f"{prefix}_{key}": value for key, value in values.items()})
    metrics.update(edge_count=len(edges), node_count=len(nodes), zero_edge_reference=float(not gold_edges))
    if complete:
        metrics["exact_graph"] = float(graph_success and edges == gold_edges and nodes == gold_nodes)
    if task == "full" and root and edge_scope:
        metrics["joint_edge_f1"] = float(root_correct) * metrics["edge_f1"]
        if complete:
            metrics["joint_exact_graph"] = float(root_correct) * metrics["exact_graph"]
    return result


def summarize(rows, *, bootstrap_samples=1000, seed=20260909):
    metrics = sorted({k for row in rows for k in row["metrics"]})
    output = {"cases": len(rows), "statuses": dict(Counter(row["status"] for row in rows)), "metrics": {}}
    for metric in metrics:
        usable = [row for row in rows if metric in row["metrics"]]
        values = [row["metrics"][metric] for row in usable]
        entry = {"mean": sum(values) / len(values), "n_cases": len(values), "ci95": None}
        successful_values = [row["metrics"][metric] for row in usable if row["status"] == "ok"]
        entry["successful_cases_mean"] = sum(successful_values) / len(successful_values) if successful_values else None
        entry["n_successful_cases"] = len(successful_values)
        groups = defaultdict(list)
        for row in usable:
            groups[row["group_id"]].append(row["metrics"][metric])
        verified = all(row.get("group_verified") is True for row in usable)
        entry["n_groups"] = len(groups)
        entry["ci_status"] = "available" if verified and len(groups) >= 2 and bootstrap_samples > 0 else "unavailable_unverified_or_too_few_groups"
        if verified and len(groups) >= 2 and bootstrap_samples > 0:
            names = sorted(groups)
            rng, samples = random.Random(seed), []
            for _ in range(bootstrap_samples):
                sample = [v for group in rng.choices(names, k=len(names)) for v in groups[group]]
                samples.append(sum(sample) / len(sample))
            samples.sort()
            entry["ci95"] = [samples[int(0.025 * (len(samples) - 1))], samples[int(0.975 * (len(samples) - 1))]]
        output["metrics"][metric] = entry
    return output
