from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from Sys.RootCauseAnalyze.propagation.heterogeneous.builder import (
    build_candidate_heterogeneous_graph,
)
from Sys.RootCauseAnalyze.propagation.heterogeneous.decoder import (
    decode_joint_root_and_graph,
)
from Sys.RootCauseAnalyze.propagation.heterogeneous.relations import (
    build_probabilistic_heterogeneous_relations,
)
from Sys.RootCauseAnalyze.propagation.heterogeneous.schema import (
    HETEROGENEOUS_SCHEMA_VERSION,
    HeterogeneousConfig,
    normalize_heterogeneous_config,
)
from Sys.RootCauseAnalyze.propagation.m1 import reconstruct_hypothesis_graph
from Sys.RootCauseAnalyze.propagation.schema import (
    PropagationConfig,
    normalize_config,
)


def reconstruct_heterogeneous_propagation(
    *,
    nodes: Sequence[Mapping[str, Any]],
    info: Mapping[str, Any],
    topology_context: Mapping[str, Any] | None = None,
    evidence_episodes: Sequence[Mapping[str, Any]] | None = None,
    propagation_config: PropagationConfig | Mapping[str, Any] | None = None,
    heterogeneous_config: HeterogeneousConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Run the first label-free heterogeneous root/propagation baseline."""

    pcfg = normalize_config(propagation_config)
    hcfg = normalize_heterogeneous_config(heterogeneous_config)
    device_hypothesis_graph = reconstruct_hypothesis_graph(
        nodes=nodes,
        info=info,
        topology_context=topology_context,
        evidence_episodes=evidence_episodes,
        config=pcfg,
    )
    candidate_graph = build_candidate_heterogeneous_graph(
        device_hypothesis_graph,
        info,
        config=hcfg,
    )
    probabilistic_graph = build_probabilistic_heterogeneous_relations(
        candidate_graph,
        device_hypothesis_graph.get("edge_hypotheses", []),
        config=hcfg,
    )
    reconstruction = decode_joint_root_and_graph(
        device_hypothesis_graph,
        candidate_graph,
        probabilistic_graph,
        propagation_config=pcfg,
        heterogeneous_config=hcfg,
    )
    device_graph = reconstruction.get("device_propagation_graph", {})
    event_graph = reconstruction.get("event_explanation_graph", {})
    return {
        "schema_version": HETEROGENEOUS_SCHEMA_VERSION,
        "method": "heterogeneous_interpretable_baseline_v0",
        "direction": "root_to_pingmesh_symptom",
        "root_input_required": False,
        "selected_root": reconstruction.get("selected_root"),
        "m1_candidate_graph": candidate_graph,
        "m2_probabilistic_graph": probabilistic_graph,
        "m3_reconstruction": reconstruction,
        "summary": {
            "candidate_device_count": candidate_graph.get("diagnostics", {}).get(
                "device_node_count", 0
            ),
            "candidate_event_count": candidate_graph.get("diagnostics", {}).get(
                "event_node_count", 0
            ),
            "candidate_device_relation_count": len(
                probabilistic_graph.get("device_relations", [])
            ),
            "candidate_event_relation_count": len(
                probabilistic_graph.get("event_relations", [])
            ),
            "selected_device_edge_count": (
                len(device_graph.get("edges", []))
                if isinstance(device_graph, Mapping)
                else 0
            ),
            "selected_event_relation_count": (
                len(event_graph.get("relations", []))
                if isinstance(event_graph, Mapping)
                else 0
            ),
            "target_coverage": (
                float(device_graph.get("target_coverage", 0.0) or 0.0)
                if isinstance(device_graph, Mapping)
                else 0.0
            ),
            "identifiability": reconstruction.get("identifiability", {}).get(
                "state", "unknown"
            ),
            "raw_topology_available": bool(
                device_hypothesis_graph.get("summary", {}).get(
                    "raw_topology_available", False
                )
            ),
        },
        "limitations": [
            "single_device_root_only",
            "heuristic_root_and_event_relation_potentials",
            "bounded_enumeration_not_exact_cp_sat",
            "event_relations_are_explanatory_not_proven_causal",
            "probabilities_are_not_calibrated",
        ],
        "propagation_config_version": pcfg.config_version,
        "heterogeneous_config_version": hcfg.config_version,
    }
