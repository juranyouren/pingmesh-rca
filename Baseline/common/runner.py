from __future__ import annotations

import argparse
import copy
from dataclasses import asdict, is_dataclass
import importlib.metadata
import platform
from pathlib import Path
import time

from .evaluation import evaluate_case, load_labels, summarize
from .graph import adapt_graph
from .io import dump_json, load_incidents, read_json
from .schema import PREDICTION_VERSION, input_fingerprint, stable_hash
from .splits import build_manifest, validate_manifest
from .timeseries import audit_incident

METHODS = ("skynet", "bian", "nec", "pcmci", "dynotears")
GRAPH_METHODS = {"nec", "pcmci", "dynotears"}


def failure_record(name, case, task, reason, *, status="runtime_failure", fold=None):
    return {"schema_version": PREDICTION_VERSION, "case_id": case["case_id"], "method": name,
            "version": "0.1.0", "task": task, "fold": fold, "input_hash": input_fingerprint(case),
            "status": status, "seed": None, "root_ranking": [], "native_graph": None, "device_graph": None,
            "graph_condition": None, "adapter_version": None, "diagnostics": {"reason": reason}, "timing": {}}


def runtime_versions():
    versions = {"python": platform.python_version()}
    for package in ("numpy", "scipy", "torch", "tigramite", "joblib", "cloudpickle"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def make_model(name, config=None, checkpoint=None, device="cpu"):
    if name == "skynet":
        from Baseline.SkyNetVoting import SkyNetVoting
        return SkyNetVoting(config)
    if name == "bian":
        from Baseline.BiAnAdapt import BiAnAdapt, BiAnConfig
        return BiAnAdapt(BiAnConfig(**config)) if config else BiAnAdapt()
    if name == "nec":
        from Baseline.NetEventCauseDevice import NetEventCauseDevice
        if checkpoint and config:
            raise ValueError("Checkpoint owns its frozen config; prediction overrides are not allowed")
        return NetEventCauseDevice.load(checkpoint, device=device) if checkpoint else NetEventCauseDevice(config, device=device)
    if name == "pcmci":
        from Baseline.PCMCIPlus import PCMCIPlus
        return PCMCIPlus(config)
    if name == "dynotears":
        from Baseline.DYNOTEARS import DYNOTEARS
        return DYNOTEARS(config)
    raise ValueError("Unknown method")


def predict_one(model, name, case, task, root_condition=None, fold=None):
    if task != "root" and name not in GRAPH_METHODS:
        return failure_record(name, case, task, "method_has_no_graph_reconstruction", status="unsupported_task", fold=fold)
    if task in {"root", "full"} and name not in {"skynet", "bian", "nec"}:
        return failure_record(name, case, task, "method_has_no_native_root_ranking", status="unsupported_task", fold=fold)
    started = time.perf_counter()
    output = None
    try:
        output = model.predict_root(case) if task == "root" else model.predict_raw_graph(case)
        if task != "root":
            ranks = output.get("root_ranking", [])
            root = ranks[0]["device_id"] if task == "full" and ranks else root_condition
            native = copy.deepcopy(output)
            output = {k: v for k, v in output.items() if k not in {"nodes", "edges"}}
            output["native_graph"] = native
            output["device_graph"] = adapt_graph(native, case, root, condition={"oracle": "oracle", "shared": "shared_prediction", "full": "own_prediction"}[task])
            if output["status"] == "ok" and output["device_graph"]["status"] != "ok":
                output["status"] = output["device_graph"]["status"]
    except Exception as exc:
        partial = output
        output = failure_record(name, case, task, f"{type(exc).__name__}: {exc}", fold=fold)
        if partial is not None:
            output["partial_native_output"] = partial
    output.update(schema_version=PREDICTION_VERSION, fold=fold, input_hash=input_fingerprint(case), task=task)
    output.setdefault("root_ranking", [])
    output.setdefault("version", getattr(model, "version", "0.1.0"))
    cfg = getattr(model, "config", {})
    cfg = asdict(cfg) if is_dataclass(cfg) else cfg if isinstance(cfg, dict) else {}
    output.setdefault("seed", cfg.get("seed"))
    output.setdefault("diagnostics", {}).setdefault("frozen_config", cfg)
    output["config_hash"] = stable_hash(cfg)
    for field in ("native_graph", "device_graph", "graph_condition", "adapter_version"):
        output.setdefault(field, None)
    if output.get("device_graph") is not None:
        output["graph_condition"] = output["device_graph"]["graph_condition"]
        output["adapter_version"] = output["device_graph"]["adapter_version"]
    output.setdefault("timing", {})["including_adapter_seconds"] = time.perf_counter() - started
    return output


def main():
    parser = argparse.ArgumentParser(description="Unified, label-isolated baseline experiments")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "audit", "manifest", "predict", "crossvalidate", "evaluate"):
        p = sub.add_parser(command)
        p.add_argument("--inputs", required=True)
        p.add_argument("--output", required=True)
        p.add_argument("--before-seconds", type=float, default=300)
        p.add_argument("--after-seconds", type=float, default=300)
        if command == "manifest":
            p.add_argument("--groups", required=True, help="Reviewed case_id -> real incident group mapping")
            p.add_argument("--folds", type=int, default=5)
            p.add_argument("--seed", type=int, default=20260909)
        if command in {"predict", "crossvalidate"}:
            p.add_argument("--method", choices=METHODS, required=True)
            p.add_argument("--config")
            p.add_argument("--task", choices=("root", "oracle", "full", "shared"), default="root")
            p.add_argument("--device", default="cpu")
            p.add_argument("--labels", help="Explicit canonical labels; only oracle prediction/evaluation")
            p.add_argument("--roots", help="Frozen case_id -> shared predicted root mapping")
        if command == "predict":
            p.add_argument("--checkpoint")
        if command == "crossvalidate":
            p.add_argument("--manifest", required=True)
        if command == "evaluate":
            p.add_argument("--labels", required=True)
            p.add_argument("--predictions", required=True)
            p.add_argument("--task", choices=("root", "oracle", "full", "shared"), default="root")
    args = parser.parse_args()
    cases = load_incidents(args.inputs, before_seconds=args.before_seconds, after_seconds=args.after_seconds)
    if args.command == "prepare":
        dump_json(args.output, {"incidents": cases})
        return
    if args.command == "audit":
        dump_json(args.output, {"cases": [audit_incident(c) for c in cases], "performance_evaluation": "not_run"})
        return
    if args.command == "manifest":
        dump_json(args.output, build_manifest(cases, read_json(args.groups), folds=args.folds, seed=args.seed))
        return
    if args.command == "predict" and args.task != "oracle" and args.labels:
        raise ValueError("Only Oracle prediction accepts labels; evaluate root/full outputs in a separate step")
    labels = load_labels(args.labels) if args.labels else {}
    if labels and set(labels) != {c["case_id"] for c in cases}:
        raise ValueError("Labels must cover the frozen inventory exactly; missing labels cannot silently remove cases")
    if args.command == "evaluate":
        loaded = read_json(args.predictions)
        predictions = loaded.get("predictions", []) if isinstance(loaded, dict) else loaded
        mapped = {p["case_id"]: p for p in predictions}
        if len(mapped) != len(predictions) or set(mapped) != {c["case_id"] for c in cases}:
            raise ValueError("Predictions must contain each case exactly once, including failures")
        rows = [evaluate_case(mapped[c["case_id"]], labels[c["case_id"]], c, args.task) for c in cases]
        dump_json(args.output, {"rows": rows, "summary": summarize(rows)})
        return
    if args.task == "oracle" and (not labels or any(l.get("root_status") != "confirmed" for l in labels.values())):
        raise ValueError("Oracle requires a confirmed single root for every case")
    roots = read_json(args.roots) if args.roots else {}
    if args.task == "shared" and set(roots) != {c["case_id"] for c in cases}:
        raise ValueError("Shared-root experiment requires a frozen root for every case")
    config = read_json(args.config) if args.config else None
    predictions, training = [], []
    def condition(case):
        return labels[case["case_id"]].get("root_device") if args.task == "oracle" else roots.get(case["case_id"])
    if args.command == "predict":
        if args.method == "nec" and not args.checkpoint:
            raise ValueError("NEC prediction needs a trained checkpoint")
        try:
            model = make_model(args.method, config, args.checkpoint, args.device)
        except Exception as exc:
            predictions = [failure_record(args.method, c, args.task, f"initialization: {type(exc).__name__}: {exc}") for c in cases]
        else:
            predictions = [predict_one(model, args.method, c, args.task, condition(c)) for c in cases]
    else:
        manifest = validate_manifest(read_json(args.manifest), cases)
        by_id = {c["case_id"]: {**c, "group_id": manifest["groups"][c["case_id"]], "group_verified": True} for c in cases}
        for split in manifest["folds"]:
            try:
                model = make_model(args.method, config, device=args.device)
                if args.method == "nec":
                    model.fit([by_id[c] for c in split["train"]], validation_cases=[by_id[c] for c in split["validation"]])
                    checkpoint = Path(args.output).with_suffix("") / f"fold-{split['fold']}.pt"
                    model.save(checkpoint)
                    training.append({"fold": split["fold"], "status": "ok", "checkpoint": str(checkpoint), "report": model.training_report})
            except Exception as exc:
                reason = f"initialization_or_fit: {type(exc).__name__}: {exc}"
                training.append({"fold": split["fold"], "status": "runtime_failure", "reason": reason})
                predictions.extend(failure_record(args.method, by_id[c], args.task, reason, fold=split["fold"]) for c in split["test"])
                continue
            for case_id in split["test"]:
                case = by_id[case_id]
                predictions.append(predict_one(model, args.method, case, args.task, condition(case), split["fold"]))
        cases = list(by_id.values())
    result = {"method": args.method, "task": args.task, "runtime": runtime_versions(), "predictions": predictions, "training": training}
    if args.command == "crossvalidate" and labels:
        by_id = {c["case_id"]: c for c in cases}
        rows = [evaluate_case(p, labels[p["case_id"]], by_id[p["case_id"]], args.task) for p in predictions]
        result.update(evaluation=rows, summary=summarize(rows))
    dump_json(args.output, result)


if __name__ == "__main__":
    main()
