from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

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
from Sys.Score.summarize_full_experiment import build_summary, write_summary
from Sys.Score.train_stage2_edge_classifier import (
    NO_DIRECT_INDEX,
    _predict_with_decision_policy,
    _select_decision_policy,
)
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


def test_p4_conservative_policy_rejects_weak_directional_edges():
    probabilities = np.asarray(
        [
            [0.45, 0.20, 0.35],
            [0.15, 0.20, 0.65],
            [0.70, 0.10, 0.20],
            [0.10, 0.65, 0.25],
        ],
        dtype=np.float64,
    )
    predicted = _predict_with_decision_policy(
        probabilities,
        direction_min_probability=0.50,
        direction_vs_no_direct_margin=0.10,
    )
    assert predicted.tolist() == [NO_DIRECT_INDEX, NO_DIRECT_INDEX, 0, 1]


def test_p4_policy_selection_returns_auditable_thresholds():
    probabilities = np.asarray(
        [
            [0.80, 0.05, 0.15],
            [0.05, 0.80, 0.15],
            [0.38, 0.20, 0.42],
            [0.20, 0.35, 0.45],
        ],
        dtype=np.float64,
    )
    labels = np.asarray([0, 1, NO_DIRECT_INDEX, NO_DIRECT_INDEX], dtype=np.int64)
    policy = _select_decision_policy(probabilities, labels)
    assert 0.30 <= policy["direction_min_probability"] <= 0.85
    assert 0.0 <= policy["direction_vs_no_direct_margin"] <= 0.35
    assert policy["selection_objective"] == "validation_directional_f0_5"
    assert policy["validation_metrics"]["precision"] == 1.0


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_unified_summary_contains_root_and_graph_metrics(tmp_path: Path):
    _write_json(
        tmp_path / "root" / "summary.json",
        {
            "stage1_variant": "supervised",
            "final_checkpoint": "root/final_model.pt",
            "results": [
                {
                    "experiment": "pc_stgr_oof",
                    "evaluation": "out_of_fold",
                    "cases": 207,
                    "top1": 75.0,
                    "top3": 91.0,
                    "top5": 96.0,
                    "mrr": 0.83,
                }
            ],
        },
    )
    ranking = {
        "ranking_evaluation": {
            "ranking_metrics": {
                "Total Evaluated Cases": 207,
                "Top-1 Acc (%)": 76.0,
                "Top-3 Acc (%)": 92.0,
                "Top-5 Acc (%)": 97.0,
                "MRR": 0.84,
            }
        }
    }
    for name, edge_f1 in (("p0", 0.60), ("p4", 0.40)):
        _write_json(tmp_path / "propagation" / name / "sum.json", ranking)
        _write_json(
            tmp_path / "evaluation" / f"{name}.json",
            {
                "validity": {
                    "mean_edge_count": 4.0,
                    "dag_valid_rate": 1.0,
                    "root_reachable_rate": 1.0,
                },
                "label_metrics": {
                    "case_count": 207,
                    "root_accuracy": 0.76,
                    "macro_directed_edge_precision": edge_f1,
                    "macro_directed_edge_recall": edge_f1,
                    "macro_directed_edge_f1": edge_f1,
                    "macro_node_precision": 0.7,
                    "macro_node_recall": 0.8,
                    "macro_node_f1": 0.74,
                    "strict_exact_rate": 0.47,
                    "cases_with_aggregation": 182,
                    "structural_equivalence": "test-equivalence",
                },
            },
        )

    payload = build_summary(tmp_path, oof_name="pc_stgr_oof")
    assert payload["primary_method"] == "p0"
    assert payload["root_location"]["stage1_oof"]["top1_accuracy_percent"] == 75.0
    assert payload["root_location"]["after_graph_rebuild"]["p0"][
        "selected_root_accuracy"
    ] == 0.76
    assert payload["graph_rebuild"]["p0"]["directed_edge_f1"] == 0.60
    assert payload["graph_rebuild"]["p4"]["directed_edge_f1"] == 0.40

    write_summary(payload, tmp_path)
    with (tmp_path / "summary.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["method"] for row in rows] == ["p0", "p4"]
    assert "root_final_accuracy" in rows[0]
    assert "graph_edge_f1" in rows[0]
    assert "P0" in (tmp_path / "summary.md").read_text(encoding="utf-8").upper()
