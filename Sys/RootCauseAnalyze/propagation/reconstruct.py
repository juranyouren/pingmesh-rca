from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from Sys.RootCauseAnalyze.propagation.m1 import reconstruct_hypothesis_graph
from Sys.RootCauseAnalyze.propagation.m2 import infer_root_paths
from Sys.RootCauseAnalyze.propagation.schema import (
    SCHEMA_VERSION,
    PropagationConfig,
    normalize_config,
    root_devices,
)
from Sys.RootCauseAnalyze.propagation.trust import assess_path_trust


def _rankings_from_hypotheses(
    hypotheses: Sequence[Mapping[str, Any] | str],
) -> list[Dict[str, Any] | str]:
    rankings: list[Dict[str, Any] | str] = []
    for index, item in enumerate(hypotheses, 1):
        if isinstance(item, str):
            rankings.append(item)
            continue
        if not isinstance(item, Mapping):
            continue
        devices = root_devices(item)
        if not devices:
            continue
        rankings.append(
            {
                "rank": int(item.get("rank", index) or index),
                "ip": devices[0],
                "combined_score": float(item.get("support_score", 1.0 / index) or 0.0),
                "decision_state": item.get("decision_state", "ranked_candidate"),
                "evidence_ids": list(item.get("evidence_ids", [])),
            }
        )
    return rankings


def _selected_evidence(
    hypothesis_graph: Mapping[str, Any], selected_graph: Mapping[str, Any]
) -> list[Dict[str, Any]]:
    evidence_ids = {
        str(evidence_id)
        for item in [
            *selected_graph.get("nodes", []),
            *selected_graph.get("edges", []),
        ]
        if isinstance(item, Mapping)
        for evidence_id in item.get("evidence_ids", [])
    }
    evidence_map = hypothesis_graph.get("evidence_map", {})
    if not isinstance(evidence_map, Mapping):
        return []
    return [
        dict(evidence_map[evidence_id])
        for evidence_id in sorted(evidence_ids)
        if evidence_id in evidence_map and isinstance(evidence_map[evidence_id], Mapping)
    ]


def reconstruct_propagation(
    *,
    nodes: Sequence[Mapping[str, Any]],
    info: Mapping[str, Any],
    topology_context: Mapping[str, Any] | None = None,
    root_hypotheses: Sequence[Mapping[str, Any] | str] | None = None,
    root_rankings: Sequence[Mapping[str, Any] | str] | None = None,
    evidence_episodes: Sequence[Mapping[str, Any]] | None = None,
    config: PropagationConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Run Stage 2 as two explicit modules: M1 graph then M2 inference."""

    cfg = normalize_config(config)
    rankings: Sequence[Mapping[str, Any] | str] = root_rankings or []
    if root_hypotheses is not None:
        rankings = _rankings_from_hypotheses(root_hypotheses)

    hypothesis_graph = reconstruct_hypothesis_graph(
        nodes=nodes,
        info=info,
        topology_context=topology_context,
        evidence_episodes=evidence_episodes,
        config=cfg,
    )
    inference = infer_root_paths(
        hypothesis_graph=hypothesis_graph,
        initial_root_rankings=rankings,
        config=cfg,
    )
    selected_graph = dict(inference.get("selected_propagation_graph", {}))
    selected_graph.setdefault("root_hypothesis", {})
    selected_graph.setdefault("nodes", [])
    selected_graph.setdefault("edges", [])
    selected_graph.setdefault("ranked_chains", [])
    selected_graph.setdefault("alternative_hypotheses", [])
    selected_graph.setdefault("covered_targets", [])
    selected_graph.setdefault("target_coverage", 0.0)
    selected_graph.setdefault("graph_score", 0.0)
    selected_graph.setdefault("hypothesis_score", 0.0)
    selected_graph.setdefault(
        "diagnostics",
        {"target_count": len(hypothesis_graph.get("affected_targets", []))},
    )
    selected_graph["diagnostics"] = {
        **dict(selected_graph.get("diagnostics", {})),
        "m1_node_count": len(hypothesis_graph.get("nodes", [])),
        "m1_edge_hypothesis_count": len(hypothesis_graph.get("edge_hypotheses", [])),
    }
    trust = assess_path_trust(selected_graph, config=cfg)

    # Stage-oriented fields are canonical. The selected-graph aliases below
    # keep existing evaluation and visualization consumers operational.
    return {
        "schema_version": SCHEMA_VERSION,
        "stage1": {
            "root_rankings": inference.get("initial_root_rankings", []),
        },
        "stage2": {
            "m1": hypothesis_graph,
            "m2": inference,
        },
        "hypothesis_graph": hypothesis_graph,
        "initial_root_rankings": inference.get("initial_root_rankings", []),
        "final_root_rankings": inference.get("final_root_rankings", []),
        "root_conditioned_propagation_graphs": inference.get(
            "root_conditioned_propagation_graphs", []
        ),
        "selected_root": inference.get("selected_root"),
        "selected_propagation_graph": selected_graph,
        "ranking_feedback": inference.get("ranking_feedback", {}),
        "direction": "root_to_symptom",
        "granularity": "device_with_alarm_evidence",
        "root_hypothesis": selected_graph["root_hypothesis"],
        "nodes": selected_graph["nodes"],
        "edges": selected_graph["edges"],
        "ranked_chains": selected_graph["ranked_chains"],
        "alternative_hypotheses": selected_graph["alternative_hypotheses"],
        "covered_targets": selected_graph["covered_targets"],
        "target_coverage": selected_graph["target_coverage"],
        "graph_score": selected_graph["graph_score"],
        "hypothesis_score": selected_graph["hypothesis_score"],
        "evidence": _selected_evidence(hypothesis_graph, selected_graph),
        "diagnostics": selected_graph["diagnostics"],
        "diagnosability": trust["diagnosability"],
        "unresolved_ambiguity": trust["unresolved_ambiguity"],
        "trust": trust["trust"],
        "config_version": cfg.config_version,
    }
