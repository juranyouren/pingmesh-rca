from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


SUMMARY_SCHEMA = "pingmesh-full-experiment-summary-v2"
METHOD_ROLES = {
    "p0": "primary_paper_method",
    "p4": "supervised_optimization",
}
METHOD_DESCRIPTIONS = {
    "p0": "Deterministic evidence normalization with root-conditioned DAG decoding.",
    "p4": "OOF supervised three-state edge classifier with validation-selected conservative admission.",
}


def _load_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _ranking_metrics(summary: Mapping[str, Any]) -> Dict[str, Any]:
    metrics = summary.get("ranking_evaluation", {}).get("ranking_metrics", {})
    if not isinstance(metrics, Mapping):
        metrics = {}
    return {
        "case_count": metrics.get("Total Evaluated Cases", 0),
        "top1_accuracy_percent": metrics.get("Top-1 Acc (%)", 0),
        "top3_accuracy_percent": metrics.get("Top-3 Acc (%)", 0),
        "top5_accuracy_percent": metrics.get("Top-5 Acc (%)", 0),
        "mrr": metrics.get("MRR", metrics.get("Mean Reciprocal Rank", 0)),
    }


def _stage1_row(root_summary: Mapping[str, Any], oof_name: str) -> Dict[str, Any]:
    results = root_summary.get("results", [])
    for row in results if isinstance(results, list) else []:
        if isinstance(row, Mapping) and row.get("experiment") == oof_name:
            return {
                "method": oof_name,
                "evaluation": row.get("evaluation", "out_of_fold"),
                "case_count": row.get("cases", 0),
                "top1_accuracy_percent": row.get("top1", 0),
                "top3_accuracy_percent": row.get("top3", 0),
                "top5_accuracy_percent": row.get("top5", 0),
                "mrr": row.get("mrr", 0),
            }
    raise ValueError(f"root summary does not contain experiment {oof_name!r}")


def _method_metrics(workdir: Path, name: str) -> Dict[str, Any]:
    score_path = workdir / "propagation" / name / "sum.json"
    evaluation_path = workdir / "evaluation" / f"{name}.json"
    score = _load_json(score_path)
    evaluation = _load_json(evaluation_path)
    labels = evaluation.get("label_metrics", {})
    validity = evaluation.get("validity", {})
    if not isinstance(labels, Mapping):
        labels = {}
    if not isinstance(validity, Mapping):
        validity = {}
    return {
        "role": METHOD_ROLES.get(name, "comparison"),
        "description": METHOD_DESCRIPTIONS.get(name, name),
        "root_location": {
            **_ranking_metrics(score),
            "selected_root_accuracy": labels.get("root_accuracy", 0),
        },
        "graph_rebuild": {
            "case_count": labels.get("case_count", 0),
            "directed_edge_precision": labels.get(
                "macro_directed_edge_precision", 0
            ),
            "directed_edge_recall": labels.get("macro_directed_edge_recall", 0),
            "directed_edge_f1": labels.get("macro_directed_edge_f1", 0),
            "node_precision": labels.get("macro_node_precision", 0),
            "node_recall": labels.get("macro_node_recall", 0),
            "node_f1": labels.get("macro_node_f1", 0),
            "strict_exact_rate": labels.get("strict_exact_rate", 0),
            "tolerant_accuracy": evaluation.get("tolerant_accuracy"),
            "structural_equivalence": labels.get("structural_equivalence"),
            "cases_with_aggregation": labels.get("cases_with_aggregation", 0),
            "validity": dict(validity),
        },
        "artifacts": {
            "root_and_graph_predictions": str(
                workdir / "propagation" / name / "res.json"
            ),
            "propagation_graphs": str(
                workdir
                / "propagation"
                / name
                / "selected_propagation_paths.json"
            ),
            "evaluation": str(evaluation_path),
        },
    }


def build_summary(
    workdir: Path,
    *,
    oof_name: str,
    methods: Iterable[str] = ("p0", "p4"),
    primary_method: str = "p0",
) -> Dict[str, Any]:
    names = tuple(dict.fromkeys(methods))
    if primary_method not in names:
        raise ValueError("primary method must be included in methods")
    root_summary = _load_json(workdir / "root" / "summary.json")
    stage1 = _stage1_row(root_summary, oof_name)
    method_rows = {name: _method_metrics(workdir, name) for name in names}
    return {
        "schema_version": SUMMARY_SCHEMA,
        "run_id": workdir.name,
        "workdir": str(workdir),
        "root_variant": root_summary.get("stage1_variant"),
        "primary_method": primary_method,
        "optimization_method": "p4" if "p4" in names else None,
        "root_location": {
            "stage1_oof": stage1,
            "after_graph_rebuild": {
                name: row["root_location"] for name, row in method_rows.items()
            },
        },
        "graph_rebuild": {
            name: row["graph_rebuild"] for name, row in method_rows.items()
        },
        "methods": method_rows,
        "artifacts": {
            "root_predictions": str(workdir / "root" / oof_name / "res.json"),
            "root_final_checkpoint": root_summary.get("final_checkpoint"),
            "p4_oof_manifest": str(
                workdir / "dd_edge_model" / "oof_manifest.json"
            ),
        },
    }


def _csv_rows(payload: Mapping[str, Any]) -> list[Dict[str, Any]]:
    stage1 = payload["root_location"]["stage1_oof"]
    rows = []
    for name, method in payload["methods"].items():
        root = method["root_location"]
        graph = method["graph_rebuild"]
        validity = graph.get("validity", {})
        rows.append(
            {
                "method": name,
                "role": method["role"],
                "root_stage1_top1_percent": stage1["top1_accuracy_percent"],
                "root_stage1_top3_percent": stage1["top3_accuracy_percent"],
                "root_stage1_top5_percent": stage1["top5_accuracy_percent"],
                "root_stage1_mrr": stage1["mrr"],
                "root_final_accuracy": root["selected_root_accuracy"],
                "root_final_top1_percent": root["top1_accuracy_percent"],
                "root_final_top3_percent": root["top3_accuracy_percent"],
                "root_final_top5_percent": root["top5_accuracy_percent"],
                "root_final_mrr": root["mrr"],
                "graph_edge_precision": graph["directed_edge_precision"],
                "graph_edge_recall": graph["directed_edge_recall"],
                "graph_edge_f1": graph["directed_edge_f1"],
                "graph_node_precision": graph["node_precision"],
                "graph_node_recall": graph["node_recall"],
                "graph_node_f1": graph["node_f1"],
                "graph_strict_exact_rate": graph["strict_exact_rate"],
                "graph_tolerant_accuracy": graph["tolerant_accuracy"],
                "graph_mean_edge_count": validity.get("mean_edge_count", 0),
                "graph_dag_valid_rate": validity.get("dag_valid_rate", 0),
                "graph_root_reachable_rate": validity.get(
                    "root_reachable_rate", 0
                ),
            }
        )
    return rows


def write_summary(payload: Mapping[str, Any], workdir: Path) -> None:
    (workdir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = _csv_rows(payload)
    with (workdir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    headers = (
        "Method",
        "Role",
        "Stage-1 Top-1 (%)",
        "Stage-1 Top-3 (%)",
        "Stage-1 Top-5 (%)",
        "Stage-1 MRR",
        "Final Root Acc.",
        "Edge P",
        "Edge R",
        "Edge F1",
        "Node P",
        "Node R",
        "Node F1",
        "Strict Exact",
    )
    keys = (
        "method",
        "role",
        "root_stage1_top1_percent",
        "root_stage1_top3_percent",
        "root_stage1_top5_percent",
        "root_stage1_mrr",
        "root_final_accuracy",
        "graph_edge_precision",
        "graph_edge_recall",
        "graph_edge_f1",
        "graph_node_precision",
        "graph_node_recall",
        "graph_node_f1",
        "graph_strict_exact_rate",
    )
    markdown = [
        "# Unified Root Location and Graph Rebuild Metrics",
        "",
        f"Primary paper method: **{payload['primary_method']}**",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _header in headers) + " |",
    ]
    for row in rows:
        markdown.append(
            "| " + " | ".join(str(row[key]) for key in keys) + " |"
        )
    markdown.append("")
    (workdir / "summary.md").write_text("\n".join(markdown), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate root-location and graph-rebuild metrics for a full run."
    )
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--oof-name", required=True)
    parser.add_argument("--methods", default="p0,p4")
    parser.add_argument("--primary-method", default="p0")
    args = parser.parse_args()
    workdir = Path(args.workdir).resolve()
    methods = [item.strip() for item in args.methods.split(",") if item.strip()]
    payload = build_summary(
        workdir,
        oof_name=args.oof_name,
        methods=methods,
        primary_method=args.primary_method,
    )
    write_summary(payload, workdir)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
