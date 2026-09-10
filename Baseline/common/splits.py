from __future__ import annotations

import random
from collections import defaultdict

from .schema import input_fingerprint, stable_hash


def build_manifest(incidents, groups, *, folds=5, seed=20260909):
    """groups is an explicit, independently reviewed case_id -> incident_group mapping."""
    ids = {c["case_id"] for c in incidents}
    if set(groups) != ids or any(not isinstance(g, str) or not g.strip() for g in groups.values()):
        raise ValueError("Group manifest must cover every case exactly once with nonempty group IDs")
    by_group = defaultdict(list)
    hashes = {}
    for case in incidents:
        key = input_fingerprint(case)
        if key in hashes and groups[hashes[key]] != groups[case["case_id"]]:
            raise ValueError("Identical input exports occur in different groups")
        hashes[key] = case["case_id"]
        by_group[groups[case["case_id"]]].append(case["case_id"])
    if not 2 <= folds <= len(by_group):
        raise ValueError("Need at least two independent groups and folds <= group count")
    rng = random.Random(seed)
    names = sorted(by_group)
    rng.shuffle(names)
    names.sort(key=lambda g: -len(by_group[g]))
    bins = [[] for _ in range(folds)]
    loads = [0] * folds
    for group in names:
        index = min(range(folds), key=lambda i: (loads[i], i))
        bins[index].append(group)
        loads[index] += len(by_group[group])
    rows = []
    for index in range(folds):
        test_groups = bins[index]
        remaining = sorted(set(by_group) - set(test_groups))
        # A two-group smoke experiment has no validation group. It is explicitly
        # unsuitable for hyperparameter selection, rather than reusing test labels.
        val_groups = [remaining[-1]] if len(remaining) >= 2 else []
        train_groups = sorted(set(remaining) - set(val_groups))
        rows.append({"fold": index,
                     **{key: sorted(c for g in gs for c in by_group[g]) for key, gs in
                        (("train", train_groups), ("validation", val_groups), ("test", test_groups))}})
    return {"schema_version": "baseline-folds-v1", "seed": seed, "groups": groups,
            "input_hashes": {c["case_id"]: input_fingerprint(c) for c in incidents}, "folds": rows,
            "manifest_hash": stable_hash([groups, rows, seed])}


def validate_manifest(manifest, incidents):
    current = {c["case_id"]: input_fingerprint(c) for c in incidents}
    if manifest.get("input_hashes") != current:
        raise ValueError("Incident inventory or input hash differs from frozen manifest")
    groups = manifest["groups"]
    if set(groups) != set(current) or any(not isinstance(g, str) or not g.strip() for g in groups.values()):
        raise ValueError("Manifest groups must cover all inputs")
    if manifest.get("manifest_hash") != stable_hash([groups, manifest["folds"], manifest["seed"]]):
        raise ValueError("Manifest contents differ from its frozen hash")
    if len({row["fold"] for row in manifest["folds"]}) != len(manifest["folds"]):
        raise ValueError("Duplicate fold IDs")
    test_seen = []
    for row in manifest["folds"]:
        partitions = [set(row[k]) for k in ("train", "validation", "test")]
        if any(len(row[k]) != len(set(row[k])) for k in ("train", "validation", "test")):
            raise ValueError("Duplicate case within a partition")
        if set.union(*partitions) != set(current) or sum(map(len, partitions)) != len(current):
            raise ValueError("Fold must partition all case IDs exactly once")
        group_sets = [{groups[c] for c in part} for part in partitions]
        if any(group_sets[i] & group_sets[j] for i in range(3) for j in range(i)):
            raise ValueError("Incident group crosses a split boundary")
        if not row["train"] or not row["test"]:
            raise ValueError("Every fold requires train and test incidents")
        test_seen.extend(row["test"])
    if sorted(test_seen) != sorted(current):
        raise ValueError("Every case must be held out exactly once")
    return manifest
