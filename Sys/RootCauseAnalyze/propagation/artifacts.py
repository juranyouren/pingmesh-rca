from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Sequence

from Sys.utils.io_utils import load_json


SELECTED_PATHS_FILENAME = "selected_propagation_paths.json"
SELECTED_PATH_SCHEMA_VERSION = "selected-propagation-path-v1"
SELECTED_PATH_REF_SCHEMA_VERSION = "selected-propagation-path-ref-v1"


def case_id_from_record(record: Mapping[str, Any]) -> str:
    explicit = str(record.get("case_id", "") or "").strip()
    if explicit:
        return explicit
    return os.path.basename(os.path.normpath(str(record.get("dir", "") or "")))


def compact_propagation(propagation: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep scalar/summary Stage 2 output in res.json; graphs live in a sidecar."""

    keys = (
        "schema_version",
        "selected_root",
        "ranking_feedback",
        "direction",
        "granularity",
        "target_coverage",
        "graph_score",
        "hypothesis_score",
        "diagnostics",
        "diagnosability",
        "unresolved_ambiguity",
        "trust",
        "config_version",
    )
    summary = {key: propagation[key] for key in keys if key in propagation}
    hypothesis_graph = propagation.get("hypothesis_graph", {})
    if isinstance(hypothesis_graph, Mapping) and isinstance(
        hypothesis_graph.get("summary"), Mapping
    ):
        summary["hypothesis_summary"] = dict(hypothesis_graph["summary"])
    return summary


def build_selected_path_record(
    dirpath: str, propagation: Mapping[str, Any]
) -> Dict[str, Any]:
    """Build the JSON-array record consumed directly by propagation-labeler."""

    selected = propagation.get("selected_propagation_graph", {})
    selected_graph = dict(selected) if isinstance(selected, Mapping) else {}
    selected_graph.setdefault("root_hypothesis", {})
    selected_graph.setdefault("nodes", [])
    selected_graph.setdefault("edges", [])
    return {
        "schema_version": SELECTED_PATH_SCHEMA_VERSION,
        "case_id": os.path.basename(os.path.normpath(dirpath)),
        "dir": dirpath,
        "selected_root": propagation.get("selected_root"),
        "selected_propagation_graph": selected_graph,
        "diagnosability": propagation.get("diagnosability", "unknown"),
        "unresolved_ambiguity": propagation.get("unresolved_ambiguity", []),
        "trust": propagation.get("trust", {}),
        "ranking_feedback": propagation.get("ranking_feedback", {}),
        "hypothesis_summary": compact_propagation(propagation).get(
            "hypothesis_summary", {}
        ),
        "config_version": propagation.get("config_version"),
    }


def build_selected_path_ref(dirpath: str) -> Dict[str, str]:
    return {
        "schema_version": SELECTED_PATH_REF_SCHEMA_VERSION,
        "artifact": SELECTED_PATHS_FILENAME,
        "case_id": os.path.basename(os.path.normpath(dirpath)),
    }


def _load_json_list(path: str, *, description: str) -> List[Dict[str, Any]]:
    raw = load_json(path, default=None)
    if not isinstance(raw, list):
        raise ValueError(f"{description} must contain a JSON list: {path}")
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _referenced_sidecar_path(
    predictions_path: str,
    records: Sequence[Mapping[str, Any]],
    explicit_path: str | None,
) -> str | None:
    if explicit_path:
        return explicit_path
    artifacts = {
        str(ref.get("artifact"))
        for record in records
        for ref in [record.get("selected_path_ref")]
        if isinstance(ref, Mapping) and ref.get("artifact")
    }
    if not artifacts:
        return None
    if len(artifacts) != 1:
        raise ValueError("predictions reference more than one selected-path artifact")
    artifact = next(iter(artifacts))
    if os.path.isabs(artifact):
        return artifact
    return os.path.join(os.path.dirname(os.path.abspath(predictions_path)), artifact)


def load_prediction_records(
    predictions_path: str, *, selected_paths_path: str | None = None
) -> List[Dict[str, Any]]:
    """Load legacy inline predictions or merge a referenced selected-path sidecar."""

    records = _load_json_list(predictions_path, description="predictions")
    sidecar_path = _referenced_sidecar_path(
        predictions_path, records, selected_paths_path
    )
    if not sidecar_path:
        return records

    sidecar_records = _load_json_list(
        sidecar_path, description="selected propagation paths"
    )
    sidecar_by_case: Dict[str, Dict[str, Any]] = {}
    for item in sidecar_records:
        case_id = case_id_from_record(item)
        if not case_id:
            raise ValueError("selected propagation path record has no case_id or dir")
        if case_id in sidecar_by_case:
            raise ValueError(f"duplicate selected propagation path case_id: {case_id}")
        sidecar_by_case[case_id] = item

    merge_fields = (
        "selected_root",
        "selected_propagation_graph",
        "diagnosability",
        "unresolved_ambiguity",
        "trust",
        "ranking_feedback",
        "hypothesis_summary",
        "config_version",
    )
    merged_records: List[Dict[str, Any]] = []
    for record in records:
        merged = dict(record)
        ref = record.get("selected_path_ref")
        case_id = (
            str(ref.get("case_id", "") or case_id_from_record(record))
            if isinstance(ref, Mapping)
            else case_id_from_record(record)
        )
        selected = sidecar_by_case.get(case_id)
        if selected is None and isinstance(ref, Mapping):
            raise ValueError(
                f"selected propagation path is missing for referenced case: {case_id}"
            )
        if selected is not None:
            for key in merge_fields:
                if key in selected:
                    merged[key] = selected[key]
        merged_records.append(merged)
    return merged_records
