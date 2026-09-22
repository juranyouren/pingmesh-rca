"""One-command RQ1 execution and reproducible offline re-evaluation."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import csv
import hashlib
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import importlib.metadata
import os
from pathlib import Path
import platform
import subprocess
import time

from Baseline.common.io import dump_json, load_incidents, read_json
from Baseline.common.schema import input_fingerprint, stable_hash, STATUSES
from .graph import device_graph
from .metrics import METRICS, aggregate, evaluate, label_sets
from .models import InputIneligible, Ours, PCMCI, THP, TimeOrder
from .prepare import (DEFAULT_LABEL_COMPLETENESS, DEFAULT_LABEL_POLICY, LABEL_COMPLETENESS, LABEL_POLICIES,
                      labels_from_path, prepare_manifest)

METHODS = ("timeorder", "nec", "pcmci", "thp", "ours")
NAMES = dict(zip(METHODS, ("TimeOrder", "NetEventCause", "PCMCI", "THP", "Ours")))


def versions():
    out = {"python": platform.python_version()}
    for name in ("numpy", "scipy", "pandas", "torch", "tigramite", "gcastle", "networkx"):
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = None
    return out


def git_state():
    root = Path(__file__).resolve().parents[2]
    def query(*args):
        try:
            return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL).decode().strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    status = query("status", "--porcelain", "--untracked-files=normal")
    return {"commit": query("rev-parse", "HEAD"), "dirty": bool(status) if status is not None else None}


def short_sha():
    root = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                                         stderr=subprocess.DEVNULL).decode().strip()
    except (OSError, subprocess.CalledProcessError):
        commit = ""
    return commit or "nogit"


def default_output_dir(results_root, condition):
    """Run directory naming contract, shared with scripts/common.sh:
    <experiment>_<variant>_<YYYYMMDD_HHMMSS>_<git-short-sha>[_NN].
    """
    stem = f"rq1_{condition}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{short_sha()}"
    candidate = Path(results_root) / stem
    suffix = 1
    while candidate.exists():
        candidate = Path(results_root) / f"{stem}_{suffix:02d}"
        suffix += 1
    return str(candidate)


def source_hashes():
    root = Path(__file__).resolve().parents[2]
    paths = set()
    for folder in ("Baseline/RQ1", "Baseline/common", "Baseline/NetEventCauseDevice",
                   "Sys/RootCauseAnalyze/propagation", "Sys/utils"):
        paths.update((root / folder).rglob("*.py"))
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def make_model(method, config, device):
    if method == "nec":
        from Baseline.NetEventCauseDevice import NetEventCauseDevice
        return NetEventCauseDevice(config, device=device)
    return {"timeorder": TimeOrder, "pcmci": PCMCI, "thp": THP, "ours": Ours}[method](config)


def frozen_config(model):
    c = model.config
    return asdict(c) if is_dataclass(c) else c


def failure(case, method, fold, condition, root, reason, status="runtime_failure"):
    return {"schema_version": "rq1-prediction-v1", "case_id": case["case_id"], "method": method,
            "fold": fold, "input_hash": input_fingerprint(case), "root": root,
            "condition": condition, "status": status, "reason": reason,
            "native_graph": None, "graphs": {}, "timing_seconds": 0.0}


def predict(model, method, case, fold, condition, root):
    started = time.perf_counter()
    record = failure(case, method, fold, condition, root, "")
    try:
        record.update(config=frozen_config(model), model_name=getattr(model, "method", method))
        native = model.predict_raw_graph(deepcopy(case), root) if method == "ours" else model.predict_raw_graph(deepcopy(case))
        record.update(status=native["status"], native_graph=native,
                      reason=native.get("reason", native.get("diagnostics", {}).get("reason", "")),
                      model_name=getattr(model, "method", method), config=frozen_config(model))
        if record["status"] not in STATUSES:
            raise ValueError("Unknown method status")
        if native["status"] == "ok":
            record["graphs"] = {v: device_graph(native, case, root, condition, v) for v in ("topology", "rooted")}
            if any(g["status"] != "ok" for g in record["graphs"].values()):
                raise ValueError("Device graph adapter rejected the root/graph")
        stable_hash(record)  # Fail visibly on NaN, tensors, or non-JSON artifacts.
    except Exception as exc:
        record.update(status="input_ineligible" if isinstance(exc, InputIneligible) else "runtime_failure",
                      reason=f"{type(exc).__name__}: {exc}", native_graph=None, graphs={})
    record["timing_seconds"] = time.perf_counter() - started
    return record


def check_inputs(args):
    cases = load_incidents(args.inputs, before_seconds=args.before_seconds, after_seconds=args.after_seconds)
    manifest = prepare_manifest(cases, manifest_path=args.manifest, groups_path=args.groups,
                                folds=args.folds, seed=args.seed)
    cases = [{**c, "group_id": manifest["groups"][c["case_id"]],
              "group_verified": manifest.get("groups_verified", False)} for c in cases]
    labels = labels_from_path(args.labels, cases, policy=args.label_policy,
                              completeness=args.label_completeness)
    if set(labels) != {c["case_id"] for c in cases}:
        raise ValueError("Canonical labels must cover the frozen inventory exactly; include unlabeled cases explicitly")
    for case in cases:
        label_sets(labels[case["case_id"]], case)
    return cases, manifest, labels


def roots_for(args, cases, manifest, labels):
    if args.condition == "oracle":
        if args.roots:
            raise ValueError("Oracle uses only explicitly confirmed roots, not --roots")
        if any(l.get("root_status") != "confirmed" for l in labels.values()):
            raise ValueError("Oracle requires one confirmed root for every case; no label-based case dropping")
        roots = {cid: l["root_device"] for cid, l in labels.items()}
    else:
        if not args.roots:
            raise ValueError("Shared condition requires frozen OOF --roots; see README")
        payload = read_json(args.roots)
        if payload.get("manifest_hash") != manifest["manifest_hash"] or not payload.get("source"):
            raise ValueError("Shared roots need matching manifest_hash and a nonempty source/provenance")
        roots = payload["roots"]
    if set(roots) != {c["case_id"] for c in cases}:
        raise ValueError("Roots must cover each case exactly once")
    for case in cases:
        if roots[case["case_id"]] not in {d["id"] for d in case["devices"]}:
            raise ValueError(f"Root is outside fixed candidate domain: {case['case_id']}")
    return roots


def summarize_predictions(cases, labels, predictions, methods, manifest, bootstrap_samples):
    expected = {(m, c["case_id"]) for m in methods for c in cases}
    keys = [(p["method"], p["case_id"]) for p in predictions]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("Predictions must contain every method/case exactly once, including failures")
    by_id = {c["case_id"]: c for c in cases}
    folds = {cid: split["fold"] for split in manifest["folds"] for cid in split["test"]}
    rows = {view: {m: [] for m in methods} for view in ("rooted", "topology")}
    for pred in predictions:
        case = by_id[pred["case_id"]]
        if pred.get("input_hash") != input_fingerprint(case) or pred.get("fold") != folds[case["case_id"]]:
            raise ValueError("Prediction input/fold differs from frozen inventory")
        if pred.get("status") not in STATUSES:
            raise ValueError("Unknown prediction status")
        for view in rows:
            graph = pred.get("graphs", {}).get(view)
            if pred["status"] == "ok":
                if not graph or graph.get("status") != "ok":
                    raise ValueError("Successful prediction is missing a device graph")
                ids = {d["id"] for d in case["devices"]}
                physical = {frozenset((e["u"], e["v"])) for e in case["physical_links"]}
                for edge in graph.get("edges", []):
                    u, v = edge["source"], edge["target"]
                    if u not in ids or v not in ids or u == v or frozenset((u, v)) not in physical:
                        raise ValueError("Device graph violates fixed domain/raw topology")
                    if not isinstance(edge.get("directed", True), bool):
                        raise ValueError("Graph edge directed marker must be boolean")
            row = evaluate({**pred, "device_graph": graph}, labels[case["case_id"]], case)
            rows[view][pred["method"]].append(row)
    # Keep entire groups in the paired successful subset, not a method-specific denominator.
    bad_groups = {by_id[p["case_id"]]["group_id"] for p in predictions if p["status"] != "ok"}
    tables = {}
    for view in rows:
        tables[view] = {}
        for scope in ("complete", "partial"):
            for cohort in ("all", "common_success"):
                tables[view][f"{scope}_{cohort}"] = {
                    method: aggregate([r for r in rows[view][method] if r["label_scope"] == scope and
                                       (cohort == "all" or r["group_id"] not in bad_groups)],
                                      bootstrap_samples=bootstrap_samples)
                    for method in methods}
    return {"schema_version": "rq1-summary-v1", "aggregation": "window mean within declared group, then group macro",
            "pcmci_coverage_policies": sorted({"strict" if p["config"]["require_coverage"] else "record-count"
                for p in predictions if p["method"] == "pcmci" and "require_coverage" in p.get("config", {})}),
            "label_policies": sorted({l.get("conversion", {}).get("policy", "canonical") for l in labels.values()}),
            "label_completeness": sorted({l.get("conversion", {}).get("graph_complete_source", "canonical")
                                          for l in labels.values()}),
            "groups_verified": manifest.get("groups_verified", True),
            "evaluation_status": manifest.get("evaluation_status", "reviewed_grouping"),
            "failure_policy": "PRF=0 for failed cases; SHD withheld if any included prediction failed",
            "shd_rule": "add/delete/reorient relation each costs 1; undecided/two-arrow relation replacement costs 1",
            "tables": tables, "rows": rows,
            "statuses": {m: dict(Counter(p["status"] for p in predictions if p["method"] == m)) for m in methods}}


def write_report(path, summary, view):
    dump_json(path / "summary.json", summary)
    markdown = ["# RQ1", "", f"Primary graph view: **{view}**. Scores are incident macro averages in [0,1].", "",
                f"Grouping: **{summary.get('evaluation_status', 'reviewed_grouping')}**. Unverified automatic groups are exploratory; CIs are disabled.", "",
                "PCMCI input policy: " + ", ".join(summary.get("pcmci_coverage_policies", [])),
                "In record-count mode, zero means no exported event record, not verified healthy or complete collection.", "",
                "Propagation label policy: " + ", ".join(summary.get("label_policies", [])),
                "Under possible-positive, 'possible' edges are scored as confirmed directed GT, matching the historical "
                "scorer; 'possible' is an annotation strength, not a verified physical relation.", "",
                "Reference completeness: " + ", ".join(summary.get("label_completeness", [])),
                "Under all_complete every propagation label is a complete ground-truth reference, so SHD-1 is reported "
                "and every unannotated device pair counts as a confirmed negative. The annotation tool does not emit a "
                "graph_complete key, so completeness comes from the label format itself rather than from a per-file "
                "declaration; the provenance field is named assumed_all_complete. Use 'as-declared' to read the key "
                "strictly instead, which withholds SHD on a reference that does not declare itself complete.", "",
                "NetEventCause is a mechanism reproduction + device adapter. THP uses gCastle TTPM + device adapter.",
                "Ours is current deterministic P0 on common observations and a fixed root.", "",
                "Failed cases score zero for P/R/F1. SHD is N/A when failures are present or labels are partial.",
                "See summary.json for metric-specific denominators, group bootstrap CIs and case-level diagnostics.", ""]
    csv_rows = []
    for graph_view in (view, "topology" if view == "rooted" else "rooted"):
        for cohort, table in summary["tables"][graph_view].items():
            markdown += [f"## {graph_view} / {cohort}", "",
                         "| Method | Adj-P ↑ | Adj-R ↑ | Adj-F1 ↑ | AH-P ↑ | AH-R ↑ | AH-F1 ↑ | SHD ↓ | Cases | Failed |",
                         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
            for method, data in table.items():
                numbers = {k: data["metrics"][k]["mean"] for k in METRICS}
                failed = data["n_cases"] - data["statuses"].get("ok", 0)
                values = ["N/A" if numbers[k] is None else f"{numbers[k]:.4f}" for k in METRICS]
                markdown.append("| " + " | ".join([NAMES[method], *values, str(data["n_cases"]), str(failed)]) + " |")
                csv_rows.append({"graph_view": graph_view, "cohort": cohort, "method": NAMES[method],
                                 **numbers, "n_cases": data["n_cases"], "n_groups": data["n_groups"], "failed": failed})
            markdown.append("")
    (path / "table.md").write_text("\n".join(markdown), encoding="utf-8")
    with (path / "table.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["graph_view", "cohort", "method", *METRICS, "n_cases", "n_groups", "failed"])
        writer.writeheader()
        writer.writerows(csv_rows)


def main(argv=None):
    project = Path(os.environ.get("PINGMESH_PROJECT_ROOT", Path(__file__).resolve().parents[2]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "evaluate"), nargs="?", default="run")
    parser.add_argument("--inputs", default=os.environ.get("PINGMESH_DATA", str(project / "data/node/nodes_max_labeled")),
                        help="Defaults to PINGMESH_DATA from common.sh")
    parser.add_argument("--labels", default=os.environ.get("PINGMESH_PROPAGATION_LABELS_ROOT", str(project / "data/propagation_labels")),
                        help="GT directory or canonical JSON; defaults to PINGMESH_PROPAGATION_LABELS_ROOT")
    parser.add_argument("--manifest", default=os.environ.get("PINGMESH_RQ1_MANIFEST") or None, help="Optional frozen manifest")
    parser.add_argument("--groups", default=os.environ.get("PINGMESH_RQ1_GROUPS") or None, help="Optional reviewed case->incident mapping")
    parser.add_argument("--folds", type=int, default=int(os.environ.get("PINGMESH_RQ1_FOLDS", "5")))
    parser.add_argument("--seed", type=int, default=int(os.environ.get("PINGMESH_RQ1_SEED", "20260920")))
    parser.add_argument("--output", help="New output directory; auto-named under PINGMESH_RESULTS when omitted")
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    parser.add_argument("--condition", choices=("shared", "oracle"), help="Default common.sh condition; --roots implies shared")
    parser.add_argument("--roots", default=os.environ.get("PINGMESH_RQ1_ROOTS") or None,
                        help="Frozen common OOF roots with manifest_hash and source")
    parser.add_argument("--config", default=os.environ.get("PINGMESH_RQ1_CONFIG", str(project / "configs/baselines/rq1.json")),
                        help="JSON keyed by methods; defaults to common.sh RQ1 config")
    parser.add_argument("--device", default="cpu", help="NEC torch device; PCMCI/THP use CPU")
    parser.add_argument("--pcmci-coverage", choices=("config", "strict", "record-count"),
                        default=os.environ.get("PINGMESH_RQ1_PCMCI_COVERAGE", "config"),
                        help="strict: require coverage; record-count: no exported records = zero counts; config: retain JSON setting")
    parser.add_argument("--label-policy", choices=LABEL_POLICIES,
                        default=os.environ.get("PINGMESH_RQ1_LABEL_POLICY", DEFAULT_LABEL_POLICY),
                        help="possible-positive: count propagation 'possible' edges as confirmed directed GT, "
                             "matching the historical scorer; strict: leave them undetermined")
    parser.add_argument("--label-completeness", choices=LABEL_COMPLETENESS,
                        default=os.environ.get("PINGMESH_RQ1_LABEL_COMPLETENESS", DEFAULT_LABEL_COMPLETENESS),
                        help="as-declared: honour graph_complete from the label file, so SHD stays N/A on partial "
                             "references; all-complete: assume every reference is complete, enabling SHD-1 but "
                             "declaring every unannotated device pair a confirmed negative")
    parser.add_argument("--before-seconds", type=float, default=300)
    parser.add_argument("--after-seconds", type=float, default=300)
    parser.add_argument("--graph-view", choices=("rooted", "topology"), default="rooted")
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--predictions", help="RQ1 predictions.json for evaluate")
    parser.add_argument("--dry-run", action="store_true", help="Check inventory/labels/folds/roots; do not fit or write")
    parser.add_argument("--check-inputs", action="store_true", help="Read-only observation checks; no GT, model, or training required")
    args = parser.parse_args(argv)
    args.condition = args.condition or ("shared" if args.roots else os.environ.get("PINGMESH_RQ1_CONDITION", "oracle"))
    if args.condition not in {"shared", "oracle"}:
        parser.error("PINGMESH_RQ1_CONDITION must be shared or oracle")
    if not args.output:
        args.output = default_output_dir(os.environ.get("PINGMESH_RESULTS", str(project / "res")), args.condition)
    if len(set(args.methods)) != len(args.methods) or args.bootstrap_samples < 0:
        parser.error("Methods must be unique and bootstrap-samples nonnegative")
    # argparse does not check an env-provided default against choices, and labels are
    # converted before the --pcmci-coverage check, so validate the policy up front.
    if args.label_policy not in LABEL_POLICIES:
        parser.error("PINGMESH_RQ1_LABEL_POLICY must be one of " + ", ".join(LABEL_POLICIES))
    if args.label_completeness not in LABEL_COMPLETENESS:
        parser.error("PINGMESH_RQ1_LABEL_COMPLETENESS must be one of " + ", ".join(LABEL_COMPLETENESS))
    if args.check_inputs:
        import json
        cases = load_incidents(args.inputs, before_seconds=args.before_seconds, after_seconds=args.after_seconds)
        print(json.dumps({"inputs": str(Path(args.inputs).resolve()), "gt_path": str(Path(args.labels).resolve()),
                          "gt_path_exists": Path(args.labels).exists(), "gt_read": False, "n_cases": len(cases),
                          "cases": [{"case_id": c["case_id"], "devices": len(c["devices"]),
                                     "physical_links": len(c["physical_links"]), "events": len(c["events"])} for c in cases],
                          "output": args.output, "models_executed": False}, ensure_ascii=False, indent=2))
        return
    cases, manifest, labels = check_inputs(args)
    roots = roots_for(args, cases, manifest, labels)
    config = read_json(args.config) if args.config else {}
    if not isinstance(config, dict) or set(config) - set(METHODS):
        raise ValueError("Config must be an object keyed by known method names")
    if args.pcmci_coverage not in {"config", "strict", "record-count"}:
        parser.error("PINGMESH_RQ1_PCMCI_COVERAGE must be config, strict or record-count")
    if args.pcmci_coverage != "config":
        config.setdefault("pcmci", {})["require_coverage"] = args.pcmci_coverage == "strict"
    output = Path(args.output)
    if output.exists():
        raise ValueError("Output already exists; choose a fresh directory")
    if args.dry_run:
        import json
        print(json.dumps({"cases": len(cases), "groups": len(set(manifest["groups"].values())),
                          "methods": args.methods, "condition": args.condition, "runtime": versions(),
                          "inputs": args.inputs, "gt": args.labels, "output": args.output,
                          "groups_verified": manifest.get("groups_verified", False),
                          "labels": dict(Counter("complete" if l.get("graph_complete") else "partial_or_unavailable" for l in labels.values())),
                          "dry_run": "inventory only; numerical backends are not executed"}, ensure_ascii=False, indent=2))
        return
    condition = "oracle" if args.condition == "oracle" else "shared_prediction"
    if args.command == "evaluate":
        if not args.predictions:
            parser.error("evaluate requires --predictions")
        payload = read_json(args.predictions)
        if payload.get("manifest_hash") != manifest["manifest_hash"] or payload.get("roots_hash") != stable_hash(roots):
            raise ValueError("Prediction manifest/roots differ from evaluation")
        predictions = payload["predictions"]
        if any(p.get("condition") != condition or p.get("root") != roots.get(p["case_id"]) for p in predictions):
            raise ValueError("Prediction root condition differs from evaluation")
    else:
        if args.predictions:
            parser.error("run does not accept --predictions")
        output.mkdir(parents=True)
        run = {"created_utc": datetime.now(timezone.utc).isoformat(), "git": git_state(), "runtime": versions(),
               "source_hashes": source_hashes(),
               "arguments": vars(args), "config": config, "config_hash": stable_hash(config),
               "manifest_hash": manifest["manifest_hash"], "input_hashes": manifest["input_hashes"],
               "labels_hash": stable_hash(labels), "roots_hash": stable_hash(roots), "status": "running"}
        dump_json(output / "run.json", run)
        dump_json(output / "folds.json", manifest)
        dump_json(output / "labels.canonical.json", {"labels": list(labels.values())})
        dump_json(output / "roots.json", {"manifest_hash": manifest["manifest_hash"], "roots": roots,
                  "source": str(args.roots) if args.roots else "explicit Oracle roots from propagation GT"})
        if not manifest.get("groups_verified", False):
            print("[RQ1] Automatic groups are unverified. NEC training and group CIs require --groups or --manifest.", flush=True)
        predictions, training = [], []
        by_id = {c["case_id"]: c for c in cases}
        for method in args.methods:
            for split in manifest["folds"]:
                fold = split["fold"]
                print(f"[{method}] fold={fold} test_cases={len(split['test'])}", flush=True)
                try:
                    if method == "nec" and (not manifest.get("groups_verified", False) or not split["train"]):
                        raise InputIneligible("NEC requires verified independent training groups; configure PINGMESH_RQ1_GROUPS or PINGMESH_RQ1_MANIFEST")
                    model = make_model(method, config.get(method), args.device)
                    if method == "nec":
                        model.fit([deepcopy(by_id[c]) for c in split["train"]],
                                  validation_cases=[deepcopy(by_id[c]) for c in split["validation"]])
                        checkpoint = output / "checkpoints" / f"nec-fold-{fold}.pt"
                        checkpoint.parent.mkdir(parents=True, exist_ok=True)
                        model.save(checkpoint)
                        training.append({"method": method, "fold": fold, "status": "ok",
                                         "checkpoint": str(checkpoint), "report": model.training_report})
                except Exception as exc:
                    reason = f"initialization_or_fit: {type(exc).__name__}: {exc}"
                    status = "input_ineligible" if isinstance(exc, InputIneligible) else "runtime_failure"
                    training.append({"method": method, "fold": fold, "status": status, "reason": reason})
                    fold_predictions = [failure(by_id[c], method, fold, condition, roots[c], reason, status=status) for c in split["test"]]
                else:
                    fold_predictions = []
                    for cid in split["test"]:
                        pred = predict(model, method, by_id[cid], fold, condition, roots[cid])
                        fold_predictions.append(pred)
                        # Save each case immediately, so a server interruption leaves useful evidence.
                        dump_json(output / "cases" / method / (stable_hash(cid)[:20] + ".json"), pred)
                        print(f"  {cid}: {pred['status']} {pred.get('reason', '')}", flush=True)
                predictions.extend(fold_predictions)
                dump_json(output / "predictions.json", {"manifest_hash": manifest["manifest_hash"],
                          "roots_hash": stable_hash(roots), "predictions": predictions, "training": training})
    summary = summarize_predictions(cases, labels, predictions, args.methods, manifest,
                                    args.bootstrap_samples if manifest.get("groups_verified", False) else 0)
    output.mkdir(parents=True, exist_ok=True)
    write_report(output, summary, args.graph_view)
    if args.command == "run":
        run.update(status="finished" if all(p["status"] == "ok" for p in predictions) else "finished_with_failures",
                   runtime=versions(), completed_utc=datetime.now(timezone.utc).isoformat())
        dump_json(output / "run.json", run)
    else:
        dump_json(output / "evaluation.json", {"arguments": vars(args), "git": git_state(),
                  "source_hashes": source_hashes(), "runtime": versions(),
                  "labels_hash": stable_hash(labels), "predictions_hash": stable_hash(payload),
                  "manifest_hash": manifest["manifest_hash"], "roots_hash": stable_hash(roots)})
    print(f"RQ1 tables: {output / 'table.md'}", flush=True)
    if any(p["status"] != "ok" for p in predictions):
        raise SystemExit(2)  # Artifacts are preserved; do not misreport a partial run as success.


if __name__ == "__main__":
    main()
