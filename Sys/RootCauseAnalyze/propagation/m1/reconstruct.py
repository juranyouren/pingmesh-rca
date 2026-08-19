from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from Sys.RootCauseAnalyze.propagation.candidates import build_candidate_graph
from Sys.RootCauseAnalyze.propagation.episodes import build_evidence_episodes
from Sys.RootCauseAnalyze.propagation.m1.probability import assign_edge_state_probabilities
from Sys.RootCauseAnalyze.propagation.schema import (
    M1_SCHEMA_VERSION,
    PropagationConfig,
    normalize_config,
)
from Sys.RootCauseAnalyze.propagation.scorer import build_edge_relation_graph
from Sys.RootCauseAnalyze.propagation.topology_context import topology_context_from_nodes


def reconstruct_hypothesis_graph(
    *,
    nodes: Sequence[Mapping[str, Any]],
    info: Mapping[str, Any],
    topology_context: Mapping[str, Any] | None = None,
    evidence_episodes: Sequence[Mapping[str, Any]] | None = None,
    config: PropagationConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build the single root-independent M1 graph without Stage 1 rankings."""

    cfg = normalize_config(config)
    episodes = (
        [dict(item) for item in evidence_episodes]
        if evidence_episodes is not None
        else build_evidence_episodes(nodes, info, config=cfg)
    )
    context = (
        dict(topology_context)
        if topology_context is not None
        else topology_context_from_nodes(nodes, info)
    )
    candidate_graph = build_candidate_graph(nodes, info, context, episodes, config=cfg)
    raw_relation_graph = build_edge_relation_graph(candidate_graph, episodes, config=cfg)
    edge_hypotheses = [
        assign_edge_state_probabilities(item, config=cfg)
        for item in raw_relation_graph.get("edge_hypotheses", [])
        if isinstance(item, Mapping)
    ]
    evidence_map = {
        str(item.get("evidence_id")): dict(item)
        for item in episodes
        if isinstance(item, Mapping) and item.get("evidence_id")
    }
    probability_config: Dict[str, Any] = {
        "method": cfg.edge_probability_method,
        "temperature": cfg.edge_probability_temperature,
    }
    if cfg.edge_probability_method == "logit_softmax_v1":
        probability_config.update(
            {
                "direction_bias": cfg.logit_direction_bias,
                "temporal_weight": cfg.logit_temporal_weight,
                "semantic_weight": cfg.logit_semantic_weight,
                "direct_weight": cfg.logit_direct_weight,
                "contradiction_weight": cfg.logit_contradiction_weight,
                "no_direct_bias": cfg.logit_no_direct_bias,
                "inactive_weight": cfg.logit_inactive_weight,
                "missing_relation_weight": cfg.logit_missing_relation_weight,
                "routing_convergence_bias": cfg.logit_routing_convergence_bias,
                "physical_link_bias": cfg.logit_physical_link_bias,
                "inferred_impact_bias": cfg.logit_inferred_impact_bias,
            }
        )
    elif cfg.edge_probability_method == "supervised_softmax_v1":
        probability_config["model_path"] = cfg.edge_probability_model_path
    candidate_diagnostics = dict(candidate_graph.get("diagnostics", {}))
    return {
        "schema_version": M1_SCHEMA_VERSION,
        "graph_type": "root_independent_hypothetical_propagation_graph",
        "nodes": [dict(item) for item in candidate_graph.get("nodes", [])],
        "candidate_topology_edges": [
            dict(item) for item in candidate_graph.get("edges", [])
        ],
        "edge_hypotheses": edge_hypotheses,
        "affected_targets": [dict(item) for item in candidate_graph.get("targets", [])],
        "source_anchors": list(candidate_graph.get("source_anchors", [])),
        "sink_anchors": list(candidate_graph.get("sink_anchors", [])),
        "evidence_map": evidence_map,
        "summary": {
            **dict(raw_relation_graph.get("summary", {})),
            "node_count": len(candidate_graph.get("nodes", [])),
            "active_relation_count": sum(
                item.get("preferred_state") != "no_direct_propagation"
                for item in edge_hypotheses
            ),
            "root_independent": True,
            "probability_method": cfg.edge_probability_method,
            "probability_config": probability_config,
            "probability_evidence_types": [
                "temporal_order",
                "alarm_semantics",
                "direct_device_relation",
            ],
            "topology_role": "raw_adjacent_pair_hard_constraint",
            "raw_topology_required": True,
            "raw_topology_available": bool(
                candidate_diagnostics.get("raw_topology_available", False)
            ),
        },
        "diagnostics": candidate_diagnostics,
        "config_version": cfg.config_version,
    }
