"""Encode -> existing root prior -> M1/M2 propagation -> root/path metrics."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import time

from Sys.Preprocess.evidence.encoder import EvidenceEncoder
from Sys.Preprocess.llm_encoder import run_case, write_json
from Sys.RootCauseAnalyze.propagation.artifacts import load_prediction_records
from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig
from Sys.RootCauseAnalyze.propagation.topology_context import load_topology_context
from Sys.RootCauseAnalyze.propagation_pipeline import _discover_case_dirs, run_propagation_pipeline
from Sys.Score.Score_N import Scorer
from Sys.Score.evaluate_propagation import aggregate_label_metrics, aggregate_validity, label_components
from Sys.utils.case_utils import load_case_info, load_case_nodes


def evaluate(predictions, labels_root=None):
    root = Scorer(str(predictions)).calculate_metrics()
    records = load_prediction_records(str(predictions))
    successful = [r for r in records if not r.get("error")]
    rows = []
    # Labels are read only here, after all inference is complete.
    for record in records:
        case = Path(record["dir"])
        label_path = (Path(labels_root) / case.name if labels_root else case) / "propagation_label.json"
        if not label_path.is_file():
            continue
        label = json.loads(label_path.read_text(encoding="utf-8"))
        if not isinstance(label, dict) or not any(isinstance(label.get(k), list) for k in ("edges", "dd_edges")):
            raise ValueError(f"Invalid propagation label: {label_path}")
        components = label_components(record, label, structural_equivalence=False)
        if record.get("error"):
            # Failed predictions count as misses, including labels with an empty edge set.
            components.update(root=0.0, strict_exact=False, evidence=0.0)
            for kind in ("node", "directed_edge"):
                components[kind] = {"precision": 0.0, "recall": 0.0, "f1": 0.0}
        rows.append({"case_id": case.name, "components": components})
    result = {"case_count": len(records), "failed_cases": len(records) - len(successful),
              "root": root.get("ranking_evaluation", {}).get("ranking_metrics") or None,
              "validity": aggregate_validity(successful),
              "propagation_labeled_cases": len(rows),
              "path_metrics": aggregate_label_metrics([r["components"] for r in rows]) if rows else None,
              "path_metric_scope": "raw_device_edges_without_structural_aggregation",
              "path_cases": rows}
    write_json(Path(predictions).parent / "evaluation.json", result)
    return result


def encoding_metrics(incidents):
    raw = sum(len(i["raw_records"]) for i in incidents)
    evidence = [e for i in incidents for d in i["devices"] for e in d["evidence"]]
    mapped = sum(e["source_count"] for e in evidence)
    unresolved = sum(len(d["unknown_events"]) for i in incidents for d in i["devices"])
    return {"raw_observations": raw, "mapped_observations": mapped, "canonical_evidence": len(evidence),
            "unresolved_observations": unresolved, "coverage": mapped / raw if raw else None,
            "dedup_reduction": 1 - len(evidence) / mapped if mapped else None,
            "partial_incidents": sum(i["status"] != "completed" for i in incidents),
            "candidate_concepts": sum(len(i["candidate_vocabulary"]) for i in incidents)}


def save_summary(output, summary):
    write_json(output / "summary.json", summary)
    rows = []
    for variant, metrics in summary["variants"].items():
        root = metrics["root"] or {}
        path = metrics["path_metrics"] or {}
        validity = metrics["validity"]
        rows.append({"variant": variant, "cases": metrics["case_count"], "failed": metrics["failed_cases"],
                     "root_labeled": root.get("Total Evaluated Cases", 0),
                     "top1_pct": root.get("Top-1 Acc (%)"), "top3_pct": root.get("Top-3 Acc (%)"),
                     "top5_pct": root.get("Top-5 Acc (%)"), "mrr": root.get("MRR"),
                     "path_labeled": metrics["propagation_labeled_cases"],
                     **{name: path.get("macro_" + name) for name in ("node_precision", "node_recall", "node_f1", "directed_edge_precision", "directed_edge_recall", "directed_edge_f1")},
                     "dag_valid_rate": validity.get("dag_valid_rate"),
                     "topology_validity": validity.get("mean_topology_validity"),
                     "mean_edge_count": validity.get("mean_edge_count")})
    with (output / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# LLM encoder experiment", "", f"Mode: {summary['mode']}", "",
             "| Variant | Cases | Failed | Root labels | Top-1 % | Top-3 % | Top-5 % | MRR | Path labels | Edge F1 | Node F1 |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in rows:
        values = [row[k] for k in ("variant", "cases", "failed", "root_labeled", "top1_pct", "top3_pct", "top5_pct", "mrr", "path_labeled", "directed_edge_f1", "node_f1")]
        lines.append("| " + " | ".join("N/A" if v is None else str(v) for v in values) + " |")
    lines.extend(["", "Encoding: " + json.dumps(summary["encoding"], ensure_ascii=False), "",
                  "N/A: no labels/denominator. Coverage is not semantic accuracy. Root/path failures remain in labeled denominators.",
                  "Graph validity covers successful predictions only; inspect edge counts to detect empty graphs."])
    if summary["mode"] == "synthetic_smoke":
        lines.append("Synthetic data and mock engine: these numbers are integration checks, not model performance.")
    text = "\n".join(lines) + "\n"
    (output / "summary.md").write_text(text, encoding="utf-8")
    print(text, flush=True)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("PINGMESH_DATA", "data/node/nodes_max_labeled")))
    parser.add_argument("--output", type=Path, required=True, help="New or empty run directory")
    parser.add_argument("--raw-root", type=Path, help="Backfill missing raw topology from this directory before inference")
    parser.add_argument("--labels-root", type=Path, help="Optional root of case/propagation_label.json")
    parser.add_argument("--root-results", type=Path, help="Optional existing neural/OOF root res.json for the same cases")
    parser.add_argument("--vocabulary", type=Path)
    parser.add_argument("--weight-file", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--stage1-weight", type=float, default=0.5)
    parser.add_argument("--compare-rules", action="store_true", help="Evaluate original rule evidence on the same cases and root priors")
    parser.add_argument("--smoke", action="store_true", help="Synthetic fixture + mock engine; no NPU/model needed")
    parser.add_argument("--allow-partial", action="store_true", help="Return zero with unresolved UNKNOWN; counts still reported")
    return parser


def run(args, engine=None):
    started = time.perf_counter()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Output must be new or empty to avoid mixing runs: {output}")
    if args.top_k < 5 or (args.limit is not None and args.limit < 1) or not 0 <= args.stage1_weight <= 1:
        raise ValueError("Require top-k >= 5, limit >= 1, and 0 <= stage1-weight <= 1")
    if args.labels_root and not args.labels_root.is_dir():
        raise ValueError(f"Labels directory does not exist: {args.labels_root}")
    if args.root_results and not args.root_results.is_file():
        raise ValueError(f"Root results do not exist: {args.root_results}")
    if not args.smoke:
        # Existing Stage 1 can silently degrade when these are missing; fail before model allocation.
        import networkx
        import scipy
        networkx.pagerank(networkx.path_graph(2))
    output.mkdir(parents=True, exist_ok=True)
    if args.smoke:
        from Sys.Preprocess.evidence.smoke import SmokeEngine, create_cases
        args.data = output / "smoke_data"
        create_cases(args.data)
        engine = SmokeEngine()
    cases = _discover_case_dirs(str(args.data.resolve()))
    if not cases:
        raise ValueError("No incident directories containing info.json and node data")
    if len({Path(c).name for c in cases}) != len(cases):
        raise ValueError("Duplicate incident directory names")
    cases = cases[:args.limit] if args.limit else cases
    if args.raw_root:
        from Sys.Preprocess.backfill_topology_context import backfill_topology_contexts
        report = backfill_topology_contexts(str(args.data), str(args.raw_root), write=True)
        write_json(output / "topology_backfill.json", report)
    for case in cases:
        context = load_topology_context(case, node_list=load_case_nodes(case), info=load_case_info(case))
        if context.get("diagnostics", {}).get("source") != "raw_task_topo":
            raise ValueError(f"Raw topology missing for {case}; provide --raw-root or run topology backfill")
    vocabulary = json.loads(args.vocabulary.read_text(encoding="utf-8")) if args.vocabulary else None
    if engine is None:
        from Sys.LLM.engine import get_shared_engine
        print("Initializing shared NPU engine once...", flush=True)
        engine = get_shared_engine()
    encoder = EvidenceEncoder(engine, vocabulary)
    write_json(output / "run.json", {"mode": "synthetic_smoke" if args.smoke else "npu", "cases": cases,
               "model_path": getattr(engine, "model_path", "injected"), "vocabulary": encoder.vocabulary,
               "top_k": args.top_k, "stage1_weight": args.stage1_weight,
               "npu_cards": os.environ.get("PINGMESH_NPU_CARDS", "0"),
               "max_model_len": os.environ.get("PINGMESH_MAX_MODEL_LEN", "16384"),
               "max_tokens": os.environ.get("PINGMESH_MAX_TOKENS", "4096"),
               "labels_root": str(args.labels_root) if args.labels_root else None,
               "compare_rules": args.compare_rules,
               "root_results": str(args.root_results) if args.root_results else None})
    incidents = []
    for index, case in enumerate(cases, 1):
        status = run_case(encoder, Path(case), output / "evidence")
        print(f"[encode {index}/{len(cases)}] {Path(case).name}: {status}", flush=True)
        incidents.append(json.loads((output / "evidence" / Path(case).name / "incident.json").read_text(encoding="utf-8")))
    cfg = PropagationConfig(root_top_k=args.top_k, stage1_weight=args.stage1_weight)
    variants = {}
    for name in (["llm_encoder", "rules"] if args.compare_rules else ["llm_encoder"]):
        result = run_propagation_pipeline(str(args.data), str(output / name),
                    root_results_path=str(args.root_results) if args.root_results else None,
                    top_k=args.top_k, config=cfg,
                    weight_path=str(args.weight_file) if args.weight_file else None,
                    evidence_dir=str(output / "evidence") if name == "llm_encoder" else None,
                    selected_case_dirs=cases)
        variants[name] = evaluate(Path(result), args.labels_root)
    summary = {"schema_version": "llm-encoder-experiment-v1", "mode": "synthetic_smoke" if args.smoke else "npu",
               "elapsed_seconds": round(time.perf_counter() - started, 3),
               "encoding": encoding_metrics(incidents), "variants": variants}
    save_summary(output, summary)
    failed = any(v["failed_cases"] for v in variants.values())
    return 2 if failed or (summary["encoding"]["partial_incidents"] and not args.allow_partial) else 0


def main():
    args = build_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
