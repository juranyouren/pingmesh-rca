"""Server directory adapters and reproducible, observation-only run preparation."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from Baseline.common.evaluation import load_labels
from Baseline.common.io import read_json
from Baseline.common.schema import input_fingerprint, stable_hash
from Baseline.common.splits import build_manifest, validate_manifest


def auto_groups(cases):
    """Conservative endpoint/alarm-context grouping; NOT reviewed incident IDs.

    All windows with the same endpoint/alarm context share a group irrespective
    of date. Identical exports also share a group. This heuristic is disclosed,
    and cannot establish incident independence for a publication claim.
    """
    parent = {c["case_id"]: c["case_id"] for c in cases}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    seen = {}
    for case in cases:
        context = case.get("endpoint_context", {})
        # Retain directional endpoints like the existing training split rule.
        keys = [("context", stable_hash({k: context.get(k) for k in
                 ("source_ip", "sink_ip", "source_az", "sink_az", "alarm_name")})),
                ("input", input_fingerprint(case))]
        for key in keys:
            if key in seen:
                a, b = find(case["case_id"]), find(seen[key])
                parent[max(a, b)] = min(a, b)
            else:
                seen[key] = case["case_id"]
    return {cid: "auto-context:" + stable_hash(find(cid))[:16] for cid in parent}


def prepare_manifest(cases, *, manifest_path=None, groups_path=None, folds=5, seed=20260920):
    if manifest_path:
        result = read_json(manifest_path)
        if result.get("schema_version") == "rq1-inference-only-v1":
            groups, splits = result["groups"], result["folds"]
            expected = {c["case_id"]: input_fingerprint(c) for c in cases}
            if (result.get("input_hashes") != expected or set(groups) != set(expected) or
                    len(set(groups.values())) != 1 or
                    splits != [{"fold": 0, "train": [], "validation": [], "test": sorted(expected)}] or
                    result.get("manifest_hash") != stable_hash([groups, splits, result["seed"]])):
                raise ValueError("Invalid frozen inference-only inventory")
        else:
            result = validate_manifest(result, cases)
        # Older explicitly supplied manifests use the existing reviewed-groups contract.
        result.setdefault("groups_verified", True)
        return result
    if folds < 2:
        raise ValueError("RQ1 folds must be >=2")
    verified = bool(groups_path)
    groups = read_json(groups_path) if groups_path else auto_groups(cases)
    if set(groups) != {c["case_id"] for c in cases} or any(not isinstance(g, str) or not g for g in groups.values()):
        raise ValueError("Groups must map every case to a nonempty group ID")
    n_groups = len(set(groups.values()))
    if n_groups >= 2:
        result = build_manifest(cases, groups, folds=min(folds, n_groups), seed=seed)
    else:
        # Inference still runs; NEC cannot train on the held-out group.
        splits = [{"fold": 0, "train": [], "validation": [], "test": sorted(groups)}]
        result = {"schema_version": "rq1-inference-only-v1", "groups": groups, "folds": splits,
                  "seed": seed, "manifest_hash": stable_hash([groups, splits, seed]),
                  "input_hashes": {c["case_id"]: input_fingerprint(c) for c in cases}}
    result.update(groups_verified=verified,
                  grouping_source="reviewed_groups_file" if verified else "automatic_endpoint_alarm_context",
                  evaluation_status="reviewed_grouping" if verified else "exploratory_unverified_groups")
    return result


def convert_label(raw, case_id):
    """Translate the repository propagation_label format without guessing possible."""
    if not isinstance(raw, dict):
        raise ValueError(f"{case_id}: propagation label must be an object")
    if raw.get("case_id") not in (None, case_id):
        raise ValueError(f"{case_id}: propagation label case_id disagrees with directory")
    if "graph_complete" in raw and not isinstance(raw["graph_complete"], bool):
        raise ValueError(f"{case_id}: graph_complete must be boolean")
    if "positive_edges" in raw or "root_status" in raw:
        if raw.get("graph_complete") and ("positive_nodes" not in raw or "positive_edges" not in raw):
            raise ValueError(f"{case_id}: complete canonical labels need explicit positive_nodes/positive_edges")
        return {**raw, "case_id": case_id}
    roots = raw.get("root_devices", [])
    confirmed = raw.get("root_scope") == "device" and isinstance(roots, list) and len(roots) == 1 and isinstance(roots[0], str) and bool(roots[0])
    label = {"case_id": case_id, "root_status": "confirmed" if confirmed else "unknown",
             "graph_complete": raw.get("graph_complete") is True,
             "positive_nodes": [], "known_node_mask": [], "positive_edges": [], "known_edge_mask": [],
             "conversion": {"source": "propagation_label", "ignored_states": {}}}
    if confirmed:
        label["root_device"] = roots[0]
    if raw.get("acceptable_hypotheses"):
        raise ValueError(f"{case_id}: acceptable_hypotheses need explicit canonical set-valued labels")
    rows = raw.get("edges", raw.get("dd_edges"))
    if rows is None:
        label.pop("positive_edges")
        label["graph_complete"] = False
        return label
    if not isinstance(rows, list):
        raise ValueError(f"{case_id}: edges/dd_edges must be a list")
    positives, known, ignored = set(), set(), Counter()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{case_id}: malformed propagation edge")
        u, v = row.get("from", row.get("source")), row.get("to", row.get("target"))
        state = row.get("membership", row.get("state"))
        if not isinstance(u, str) or not isinstance(v, str) or not u or not v or u == v:
            raise ValueError(f"{case_id}: malformed propagation endpoints")
        if state == "definite":
            positives.add((u, v))
            known.update(((u, v), (v, u)))
        elif state == "explicit_no_direct":
            known.update(((u, v), (v, u)))
        else:
            ignored[str(state)] += 1
    negative_pairs = {frozenset((r.get("from", r.get("source")), r.get("to", r.get("target"))))
                      for r in rows if r.get("membership", r.get("state")) == "explicit_no_direct"}
    if any(frozenset(e) in negative_pairs for e in positives):
        raise ValueError(f"{case_id}: definite edge contradicts explicit_no_direct")
    if label["graph_complete"] and ignored:
        raise ValueError(f"{case_id}: complete graph contains unresolved states {dict(ignored)}")
    nodes = {n for e in positives for n in e} | ({roots[0]} if confirmed else set())
    label.update(positive_nodes=sorted(nodes), known_node_mask=sorted(nodes),
                 positive_edges=[list(e) for e in sorted(positives)],
                 known_edge_mask=[list(e) for e in sorted(known)])
    label["conversion"]["ignored_states"] = dict(ignored)
    return label


def labels_from_path(path, cases):
    path = Path(path)
    if path.is_file():
        return load_labels(path)
    if not path.is_dir():
        raise FileNotFoundError(f"Propagation GT directory is unavailable: {path}. "
                                "Run on the server with GT, or use --check-inputs for local examples.")
    # The repository stores <case_id>/propagation_label.json; allow nested groups.
    index = {}
    for file in sorted(path.rglob("propagation_label.json")):
        cid = file.parent.name
        if cid in index:
            raise ValueError(f"Duplicate propagation label for case {cid}")
        index[cid] = file
    if not index and (path / "labels.json").is_file():
        return load_labels(path / "labels.json")
    required = {c["case_id"] for c in cases}
    missing = required - set(index)
    if missing:
        raise FileNotFoundError(f"Missing propagation_label.json for {len(missing)} input cases: {sorted(missing)[:10]}")
    return {cid: convert_label(read_json(index[cid]), cid) for cid in sorted(required)}
