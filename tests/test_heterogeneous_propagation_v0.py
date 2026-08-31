from __future__ import annotations

from pathlib import Path

from Sys.RootCauseAnalyze.heterogeneous_propagation_pipeline import (
    run_heterogeneous_propagation_pipeline,
)
from Sys.RootCauseAnalyze.propagation import PropagationConfig
from Sys.RootCauseAnalyze.propagation.heterogeneous import (
    HETEROGENEOUS_SCHEMA_VERSION,
    HeterogeneousConfig,
    reconstruct_heterogeneous_propagation,
)
from Sys.RootCauseAnalyze.propagation.solver import is_dag
from Sys.RootCauseAnalyze.propagation.topology_context import TOPOLOGY_SCHEMA_VERSION
from Sys.utils.io_utils import load_json, save_json


BASE_TIME = 1_700_000_000_000


def _nodes(with_events: bool = True):
    events = {
        "D1": [
            {
                "alarm_name": "physical link down interface=GE1/0/1",
                "alarm_time": BASE_TIME,
            }
        ],
        "D2": [
            {
                "alarm_name": "BFD session down",
                "alarm_time": BASE_TIME + 10_000,
            }
        ],
        "D3": [
            {
                "alarm_name": "routing change",
                "alarm_time": BASE_TIME + 20_000,
            }
        ],
    }
    return [
        {
            "mgmt_ip": device_id,
            "role": role,
            "alarms": events[device_id] if with_events else [],
            "logs": [],
        }
        for device_id, role in (("D1", "LEAF"), ("D2", "SPINE"), ("D3", "LEAF"))
    ]


def _info():
    return {
        "alarm_time": BASE_TIME + 30_000,
        "alarm_name": "pingmesh packet loss",
        "source_ip": ["host-a"],
        "sink_ip": ["host-b"],
    }


def _topology_context():
    return {
        "schema_version": TOPOLOGY_SCHEMA_VERSION,
        "source_endpoints": ["host-a"],
        "sink_endpoints": ["host-b"],
        "source_anchors": ["D1"],
        "sink_anchors": ["D3"],
        "nodes": [
            {"device_id": "D1", "role": "LEAF"},
            {"device_id": "D2", "role": "SPINE"},
            {"device_id": "D3", "role": "LEAF"},
        ],
        "edges": [
            {
                "edge_id": "T1",
                "endpoint_a": "D1",
                "endpoint_b": "D2",
                "endpoint_a_port": "GE1/0/1",
                "endpoint_b_port": "GE1/0/1",
                "group_ids": ["G1"],
            },
            {
                "edge_id": "T2",
                "endpoint_a": "D2",
                "endpoint_b": "D3",
                "endpoint_a_port": "GE1/0/2",
                "endpoint_b_port": "GE1/0/1",
                "group_ids": ["G1"],
            },
        ],
        "diagnostics": {
            "source": "raw_task_topo",
            "device_count": 3,
            "edge_count": 2,
            "group_count": 1,
        },
    }


def _run(with_events: bool = True):
    return reconstruct_heterogeneous_propagation(
        nodes=_nodes(with_events=with_events),
        info=_info(),
        topology_context=_topology_context(),
        propagation_config=PropagationConfig(
            root_top_k=3,
            max_candidate_nodes=10,
            max_targets=4,
        ),
        heterogeneous_config=HeterogeneousConfig(
            max_root_candidates=3,
            max_events_per_device=4,
            max_event_pairs=20,
        ),
    )


def test_v0_runs_end_to_end_without_an_external_root():
    result = _run()

    assert result["schema_version"] == HETEROGENEOUS_SCHEMA_VERSION
    assert result["root_input_required"] is False
    assert result["selected_root"] in {"D1", "D2", "D3"}
    assert result["summary"]["candidate_device_count"] == 3
    assert result["summary"]["candidate_event_count"] == 3

    node_types = {
        item["node_type"] for item in result["m1_candidate_graph"]["nodes"]
    }
    assert node_types == {"device", "event", "symptom"}
    relation_types = {
        item["relation_type"]
        for item in result["m1_candidate_graph"]["relations"]
    }
    assert "device_physical_adjacency" in relation_types
    assert "event_observed_on_device" in relation_types
    assert "event_dependency_candidate" in relation_types


def test_v0_device_edges_are_raw_topology_valid_and_acyclic():
    result = _run()
    device_graph = result["m3_reconstruction"]["device_propagation_graph"]
    allowed = {frozenset(("D1", "D2")), frozenset(("D2", "D3"))}

    assert is_dag(device_graph["edges"])
    assert all(
        frozenset((edge["from"], edge["to"])) in allowed
        for edge in device_graph["edges"]
    )
    assert all(edge.get("topology_edge_ids") for edge in device_graph["edges"])


def test_v0_keeps_observation_and_event_relations_out_of_device_propagation():
    result = _run()
    reconstruction = result["m3_reconstruction"]

    assert all(
        relation["is_propagation_edge"] is False
        for relation in reconstruction["evidence_grounding_relations"]
    )
    assert all(
        relation["is_propagation_edge"] is False
        for relation in reconstruction["event_explanation_graph"]["relations"]
    )
    assert all(
        edge["from"] in {"D1", "D2", "D3"}
        and edge["to"] in {"D1", "D2", "D3"}
        for edge in reconstruction["device_propagation_graph"]["edges"]
    )


def test_v0_returns_an_unidentifiable_partial_result_when_events_are_missing():
    result = _run(with_events=False)

    assert result["selected_root"] in {"D1", "D2", "D3"}
    assert result["summary"]["candidate_event_count"] == 0
    assert result["m3_reconstruction"]["identifiability"]["state"] == "unidentifiable"


def test_v0_batch_pipeline_writes_compact_and_full_artifacts(tmp_path: Path):
    case_dir = tmp_path / "case-001"
    output_dir = tmp_path / "out"
    case_dir.mkdir()
    save_json(_nodes(), str(case_dir / "nodes.json"))
    save_json(_info(), str(case_dir / "info.json"))
    save_json(_topology_context(), str(case_dir / "topology_context.json"))
    # An intentionally unrelated label proves the V0 interface does not need
    # a root argument or label artifact to run.
    save_json([{"abnormal_node": [{"ip": "NOT_A_DEVICE"}]}], str(case_dir / "label.json"))

    result_path = run_heterogeneous_propagation_pipeline(
        [str(case_dir)],
        str(output_dir),
        propagation_config=PropagationConfig(root_top_k=3, max_candidate_nodes=10),
        heterogeneous_config=HeterogeneousConfig(max_root_candidates=3),
    )

    compact = load_json(result_path)
    full = load_json(str(output_dir / "heterogeneous_graphs.json"))
    assert compact[0]["case_id"] == "case-001"
    assert compact[0]["root_input_required"] is False
    assert "error" not in compact[0]
    assert full[0]["result"]["selected_root"] in {"D1", "D2", "D3"}
