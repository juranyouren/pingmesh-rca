#!/usr/bin/env python
"""Backfill NetEventCause into an existing RQ1 run and re-score SHD under an explicit penalty.

Only NetEventCause is executed. Every other method's predictions are read back from the
source run and reused verbatim, which is only sound because ``manifest_hash`` does not
cover ``groups_verified`` (see ``Baseline/common/splits.py``: ``manifest_hash`` is
``stable_hash([groups, folds, seed])``). Forcing the flag therefore leaves the frozen
folds, the frozen roots and every previously computed prediction valid, and
``Baseline/RQ1/runner.py`` keeps accepting them.

Usage:
    # 1) Show the plan; runs nothing and writes nothing.
    python scripts/rq1_nec_backfill.py --from-run res/rq1_oracle_20260921_153738_930782 --dry-run

    # 2) Re-run NEC only, then re-score SHD with the domain-maximum penalty.
    python scripts/rq1_nec_backfill.py \\
        --from-run res/rq1_oracle_20260921_153738_930782 \\
        --allow-unverified-nec-training --shd-failure-penalty worst

    # 3) Score with the empty-graph floor instead, into a chosen directory.
    python scripts/rq1_nec_backfill.py --from-run res/rq1_oracle_20260921_153738_930782 \\
        --allow-unverified-nec-training --shd-failure-penalty empty \\
        --output res/rq1_nec_backfill_empty

Why --allow-unverified-nec-training is required:
    NetEventCause is supervised, so ``runner.py`` refuses to train it unless the manifest
    declares ``groups_verified``. The automatic endpoint/alarm-context grouping is not a
    reviewed incident-independence certificate, so this script will not assert it on your
    behalf: it asks for the flag and records the override in every artifact it writes.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
import subprocess
import sys

PROJECT = Path(os.environ.get("PINGMESH_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
NEC = "nec"
RESULTS = Path(os.environ.get("PINGMESH_RESULTS", str(PROJECT / "res")))

# Stored argparse attribute -> CLI flag, used to replay the source run's invocation so the
# labels, roots and folds are reproduced exactly rather than re-guessed.
REPLAY_FLAGS = (
    ("inputs", "--inputs"), ("labels", "--labels"), ("config", "--config"),
    ("condition", "--condition"), ("device", "--device"),
    ("pcmci_coverage", "--pcmci-coverage"), ("label_policy", "--label-policy"),
    ("label_completeness", "--label-completeness"),
    ("before_seconds", "--before-seconds"), ("after_seconds", "--after-seconds"),
    ("graph_view", "--graph-view"), ("bootstrap_samples", "--bootstrap-samples"),
    ("folds", "--folds"), ("seed", "--seed"),
)


def read_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT,
                              capture_output=True, text=True, check=True).stdout.strip() or "nogit"
    except Exception:
        return "nogit"


def replay(arguments, *, skip):
    """Rebuild the source run's CLI, dropping flags this script supplies itself."""
    flags = []
    for attribute, flag in REPLAY_FLAGS:
        if flag in skip or arguments.get(attribute) is None:
            continue
        flags += [flag, str(arguments[attribute])]
    if arguments.get("condition") != "oracle" and arguments.get("roots"):
        flags += ["--roots", str(arguments["roots"])]
    return flags


def run_rq1(cli, *, python, tolerate_failures):
    command = [python, "-m", "Baseline.RQ1", *cli]
    print("$ " + " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=PROJECT)
    # The runner exits 2 when any prediction failed. Artifacts stay valid and the failure
    # is recorded per case, so exit 2 is not an error for this script.
    allowed = (0, 2) if tolerate_failures else (0,)
    if completed.returncode not in allowed:
        raise SystemExit(f"Baseline.RQ1 exited {completed.returncode}")
    return completed.returncode


def merge_predictions(source, nec):
    """Replace NEC entries in the source payload; every other method is carried over."""
    for key in ("manifest_hash", "roots_hash"):
        if source.get(key) != nec.get(key):
            raise SystemExit(
                f"{key} differs between the source run and the NEC run.\n"
                "The folds are no longer the frozen ones, so the previously computed "
                "predictions cannot be reused. Re-run all methods instead of backfilling.")
    kept = [p for p in source["predictions"] if p["method"] != NEC]
    fresh = [p for p in nec["predictions"] if p["method"] == NEC]
    if not fresh:
        raise SystemExit("The NEC run produced no predictions")
    training = [t for t in source.get("training", []) if t.get("method") != NEC]
    return {**source, "predictions": kept + fresh, "training": training + nec.get("training", [])}, kept, fresh


def shd_column(summary, view, cohort):
    """summary["tables"] is keyed [view][cohort][method]; cohorts may be empty."""
    return {method: data["metrics"]["SHD"]
            for method, data in summary["tables"].get(view, {}).get(cohort, {}).items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-run", required=True,
                        help="Existing RQ1 run directory containing predictions.json/folds.json/run.json")
    parser.add_argument("--output", help="New output directory; defaults to res/rq1_nec_backfill_<UTC timestamp>")
    parser.add_argument("--shd-failure-penalty", choices=("withhold", "empty", "worst"), default="worst",
                        help="How failed cases are scored for SHD (see Baseline/RQ1/metrics.py)")
    parser.add_argument("--allow-unverified-nec-training", action="store_true",
                        help="Acknowledge that groups_verified is forced so NEC can train, and that incident "
                             "independence is therefore NOT certified")
    parser.add_argument("--python", default=os.environ.get("PYTHON") or sys.executable,
                        help="Interpreter used for the Baseline.RQ1 subprocesses")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; run nothing and write nothing")
    args = parser.parse_args(argv)

    source_dir = Path(args.from_run)
    if not source_dir.is_dir():
        raise SystemExit(f"Not a directory: {source_dir}")
    for name in ("predictions.json", "folds.json", "run.json"):
        if not (source_dir / name).is_file():
            raise SystemExit(f"Missing {name} in {source_dir}")

    folds = read_json(source_dir / "folds.json")
    predictions = read_json(source_dir / "predictions.json")
    run = read_json(source_dir / "run.json")

    if folds.get("manifest_hash") != predictions.get("manifest_hash"):
        raise SystemExit("folds.json and predictions.json disagree on manifest_hash")
    if run.get("manifest_hash") != folds.get("manifest_hash"):
        raise SystemExit("run.json and folds.json disagree on manifest_hash")

    already_verified = bool(folds.get("groups_verified", False))
    if not already_verified and not args.allow_unverified_nec_training:
        raise SystemExit(
            "This manifest is not a reviewed grouping, so NEC cannot train on it.\n"
            "Pass --allow-unverified-nec-training to force groups_verified, or supply a "
            "reviewed manifest with PINGMESH_RQ1_MANIFEST / --manifest.")

    methods = sorted({p["method"] for p in predictions["predictions"]})
    cases = sorted({p["case_id"] for p in predictions["predictions"]})
    if NEC not in methods:
        raise SystemExit(f"Source run has no {NEC} predictions to replace: {methods}")

    output = Path(args.output) if args.output else RESULTS / (
        "rq1_nec_backfill_" + datetime.utcnow().strftime("%Y%m%d_%H%M%S"))
    # Baseline.RQ1 refuses an --output that already exists (runner.py: "Output already
    # exists; choose a fresh directory"), so the verified manifest copy, the NEC run and
    # the merged predictions live in a sibling work directory. The final evaluate pass
    # then creates --output itself.
    work = output.with_name(output.name + "_work")
    manifest_path = work / "folds_nec_verified.json"
    nec_dir = work / "nec_run"
    merged_path = work / "predictions.merged.json"

    print(f"source run      : {source_dir}")
    print(f"output          : {output}")
    print(f"work directory  : {work}")
    print(f"manifest_hash   : {folds['manifest_hash']}")
    print(f"grouping        : {folds.get('grouping_source')} "
          f"(verified={already_verified} -> True{'' if already_verified else ' FORCED'})")
    print(f"methods reused  : {[m for m in methods if m != NEC]}")
    print(f"cases           : {len(cases)}")
    print(f"shd penalty     : {args.shd_failure_penalty}")

    # --inputs/--labels are replayed because check_inputs must reproduce the source run's
    # inventory, canonical labels and Oracle roots exactly; --manifest is supplied here.
    replay_cli = replay(run.get("arguments", {}), skip=set())
    nec_cli = ["run", "--methods", NEC, "--manifest", str(manifest_path), "--output", str(nec_dir),
               "--shd-failure-penalty", args.shd_failure_penalty, *replay_cli]
    evaluate_cli = ["evaluate", "--manifest", str(manifest_path), "--predictions", str(merged_path),
                    "--output", str(output), "--shd-failure-penalty", args.shd_failure_penalty, *replay_cli]

    if args.dry_run:
        print("\n[dry-run] would create:", output)
        print("[dry-run] would write a manifest copy to:", manifest_path)
        print("[dry-run] would run:", " ".join([args.python, "-m", "Baseline.RQ1", *nec_cli]))
        print("[dry-run] would run:", " ".join([args.python, "-m", "Baseline.RQ1", *evaluate_cli]))
        return 0

    for path in (output, work):
        if path.exists():
            raise SystemExit(f"Already exists: {path}. Pick a new --output.")

    manifest = json.loads(json.dumps(folds))
    manifest["groups_verified"] = True
    manifest["groups_verified_source"] = (
        "declared by the frozen manifest" if already_verified else
        "forced by scripts/rq1_nec_backfill.py so NEC could train; incident independence is NOT certified")
    write_json(manifest_path, manifest)

    print("\n[1/3] re-running NetEventCause", flush=True)
    run_rq1(nec_cli, python=args.python, tolerate_failures=True)
    nec_payload = read_json(nec_dir / "predictions.json")

    print("\n[2/3] merging with the source predictions", flush=True)
    merged, kept, fresh = merge_predictions(predictions, nec_payload)
    write_json(merged_path, merged)
    print(f"  reused {len(kept)} predictions, replaced with {len(fresh)} NEC predictions")
    statuses = {}
    for prediction in fresh:
        statuses[prediction["status"]] = statuses.get(prediction["status"], 0) + 1
    print(f"  NEC statuses: {statuses}")

    print("\n[3/3] re-scoring with SHD penalty " + args.shd_failure_penalty, flush=True)
    run_rq1(evaluate_cli, python=args.python, tolerate_failures=True)

    summary = read_json(output / "summary.json")
    provenance = {
        "created_utc": datetime.utcnow().isoformat(), "git": git_commit(),
        "source_run": str(source_dir), "source_arguments": run.get("arguments", {}),
        "manifest_hash": folds["manifest_hash"],
        "groups_verified_before": already_verified, "groups_verified_forced": not already_verified,
        "groups_verified_source": manifest["groups_verified_source"],
        "shd_failure_penalty": args.shd_failure_penalty,
        "nec_statuses": statuses, "methods_reused": [m for m in methods if m != NEC],
        "note": ("Only NEC was re-run. Other methods' predictions were reused from the source run "
                 "under the unchanged manifest_hash; groups_verified was forced, so grouping "
                 "independence is exploratory and not certified."),
    }
    # Keep the verified manifest inside the self-contained result directory too.
    write_json(output / "folds_nec_verified.json", manifest)
    write_json(output / "backfill.json", provenance)
    print(f"\nwork directory left in place: {work}")

    for view in ("rooted", "topology"):
        for cohort in ("complete_all", "partial_all", "complete_common_success", "partial_common_success"):
            rows = shd_column(summary, view, cohort)
            if not rows or all(r["status"] == "unavailable" for r in rows.values()):
                continue
            print(f"\n{view} / {cohort}:")
            for method, shd in rows.items():
                value = f"{shd['mean']:.4f}" if shd["mean"] is not None else "N/A"
                print(f"  {method:<12} SHD={value} status={shd['status']} "
                      f"penalised={shd['n_penalised']} success_only={shd['successful_only_mean']}")
    print(f"\nArtifacts: {output / 'table.md'}  {output / 'summary.json'}  {output / 'backfill.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
