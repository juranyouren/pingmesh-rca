import math

import pytest

from Sys.Score.diagnose_graph_reranking import (
    evaluate_score_method,
    graph_diversity,
    score_candidate_graph,
)
from Sys.RootCauseAnalyze.stage1 import neural_graph
from Sys.RootCauseAnalyze.stage1.neural_graph import (
    EDGE_FEATURE_DIM,
    PROPAGATION_EDGE_FEATURE_DIM,
    REL_PHYSICAL_FORWARD,
    REL_PHYSICAL_REVERSE,
    EventVocabulary,
    GraphBuildConfig,
    PathConditionedGraphBuilder,
    RawCase,
    condition_graph_on_propagation_dag,
)
from Sys.RootCauseAnalyze.stage1.neural_pipeline import build_parser as stage1_parser
from Sys.RootCauseAnalyze.propagation_pipeline import _rankings_from_record


def _case():
    return RawCase(
        dirpath="propagation-feature-case",
        nodes=[
            {
                "mgmt_ip": "D1",
                "role": "LEAF",
                "linked_from": ["host-a"],
                "linked_to": ["D2"],
                "alarms": [],
                "logs": [],
            },
            {
                "mgmt_ip": "D2",
                "role": "SPINE",
                "linked_from": ["D1"],
                "linked_to": ["host-b"],
                "alarms": [],
                "logs": [],
            },
        ],
        info={
            "alarm_time": 2_000,
            "alarm_name": "pingmesh",
            "source_ip": ["host-a"],
            "sink_ip": ["host-b"],
        },
        gt_ip="D1",
    )


def _physical_features(graph, relation):
    return [
        features
        for edge_relation, features in zip(graph.edge_types, graph.edge_features)
        if edge_relation == relation
    ]


def test_stage1_root_independent_probabilities_are_orientation_aware(monkeypatch):
    monkeypatch.setattr(
        neural_graph,
        "_root_independent_edge_probabilities",
        lambda _case, _config: (
            {
                ("D1", "D2"): [0.75, 0.15, 0.10],
                ("D2", "D1"): [0.15, 0.75, 0.10],
            },
            {"propagation_probability_pair_count": 1},
        ),
    )
    case = _case()
    vocabulary = EventVocabulary.fit([case], max_size=8)
    graph = PathConditionedGraphBuilder(
        vocabulary,
        config=GraphBuildConfig(include_propagation_edge_probabilities=True),
    ).build(case, include_labels=True)

    assert graph.edge_feature_dim == PROPAGATION_EDGE_FEATURE_DIM
    assert _physical_features(graph, REL_PHYSICAL_FORWARD) == [
        [0.0, 0.0, 0.75, 0.15, 0.10]
    ]
    assert _physical_features(graph, REL_PHYSICAL_REVERSE) == [
        [0.0, 0.0, 0.15, 0.75, 0.10]
    ]
    assert graph.diagnostics["propagation_edge_probabilities_enabled"] is True
    assert graph.diagnostics["propagation_probability_pair_count"] == 1


def test_stage1_missing_propagation_pair_is_masked_not_no_direct(monkeypatch):
    monkeypatch.setattr(
        neural_graph,
        "_root_independent_edge_probabilities",
        lambda _case, _config: ({}, {"propagation_probability_pair_count": 0}),
    )
    case = _case()
    vocabulary = EventVocabulary.fit([case], max_size=8)
    graph = PathConditionedGraphBuilder(
        vocabulary,
        config=GraphBuildConfig(include_propagation_edge_probabilities=True),
    ).build(case, include_labels=False)

    assert _physical_features(graph, REL_PHYSICAL_FORWARD) == [
        [0.0, 0.0, 0.0, 0.0, 0.0]
    ]


def test_stage1_probability_feature_flag_preserves_original_contract():
    case = _case()
    vocabulary = EventVocabulary.fit([case], max_size=8)
    graph = PathConditionedGraphBuilder(vocabulary).build(case, include_labels=False)
    args = stage1_parser().parse_args(
        ["crossval", "--include-propagation-edge-probabilities"]
    )

    assert graph.edge_feature_dim == EDGE_FEATURE_DIM
    assert all(len(row) == EDGE_FEATURE_DIM for row in graph.edge_features)
    assert args.include_propagation_edge_probabilities is True


def test_candidate_conditioned_graph_uses_hard_direction_mask():
    case = _case()
    vocabulary = EventVocabulary.fit([case], max_size=8)
    base_graph = PathConditionedGraphBuilder(vocabulary).build(
        case, include_labels=False
    )

    graph = condition_graph_on_propagation_dag(
        base_graph,
        [("D1", "D2")],
        candidate_root="D1",
    )

    assert graph.edge_feature_dim == PROPAGATION_EDGE_FEATURE_DIM
    assert _physical_features(graph, REL_PHYSICAL_FORWARD) == [
        [0.0, 0.0, 1.0, 0.0, 0.0]
    ]
    assert _physical_features(graph, REL_PHYSICAL_REVERSE) == [
        [0.0, 0.0, 0.0, 1.0, 0.0]
    ]
    assert all(
        features[2:] == [0.0, 0.0, 0.0]
        for relation, features in zip(graph.edge_types, graph.edge_features)
        if relation not in {REL_PHYSICAL_FORWARD, REL_PHYSICAL_REVERSE}
    )
    assert graph.diagnostics["candidate_root"] == "D1"
    assert graph.diagnostics["hard_selected_edge_count"] == 1
    assert graph.diagnostics["hard_matched_edge_count"] == 1


def test_propagation_pipeline_consumes_learned_reranking_first():
    record = {
        "initial_root_rankings": [
            {"rank": 1, "ip": "D1", "combined_score": 0.7},
            {"rank": 2, "ip": "D2", "combined_score": 0.3},
        ],
        "reranked_root_rankings": [
            {"rank": 1, "ip": "D2", "combined_score": 0.8},
            {"rank": 2, "ip": "D1", "combined_score": 0.2},
        ],
    }

    assert [row["ip"] for row in _rankings_from_record(record)] == ["D2", "D1"]


def test_statistical_reranker_extracts_candidate_graph_quality():
    torch = pytest.importorskip("torch")
    from Sys.RootCauseAnalyze.stage1.propagation_reranker import (
        FEATURE_NAMES,
        RerankerExample,
        RerankerModelConfig,
        StatisticalListwiseReranker,
        extract_candidate_rows,
        predict_example,
    )

    hypothesis_graph = {
        "edge_hypotheses": [
            {
                "edge_hypothesis_id": "H1",
                "state_probabilities": {"no_direct_propagation": 0.20},
            }
        ]
    }
    root_conditioned = [
        {
            "root_hypothesis": {
                "root_devices": ["D1"],
                "rank": 1,
                "support_score": 0.7,
            },
            "explanation_score": 0.6,
            "propagation_graph": {
                "graph_score": 0.8,
                "target_coverage": 1.0,
                "nodes": [
                    {
                        "device_id": "D1",
                        "role": "root",
                        "evidence_ids": ["E1"],
                        "onset_interval_ms": [1, 2],
                    },
                    {"device_id": "D2", "role": "affected"},
                ],
                "edges": [
                    {
                        "edge_hypothesis_id": "H1",
                        "state_probability": 0.75,
                    }
                ],
                "ranked_chains": [
                    {"devices": ["D1", "D2"], "score": 0.8}
                ],
                "covered_targets": ["D2"],
                "diagnostics": {
                    "target_count": 1,
                    "reachable_target_count": 1,
                    "path_candidate_count": 2,
                    "supported_edge_ratio": 1.0,
                    "grounded_edge_ratio": 1.0,
                },
            },
        },
        {
            "root_hypothesis": {
                "root_devices": ["D2"],
                "rank": 2,
                "support_score": 0.3,
            },
            "explanation_score": 0.0,
            "propagation_graph": {
                "graph_score": 0.0,
                "target_coverage": 0.0,
                "nodes": [{"device_id": "D2", "role": "root"}],
                "edges": [],
                "ranked_chains": [],
                "diagnostics": {"target_count": 1},
            },
        },
    ]
    rankings = [
        {"rank": 1, "ip": "D1", "combined_score": 0.7, "logit": 1.0},
        {"rank": 2, "ip": "D2", "combined_score": 0.3, "logit": 0.0},
    ]
    rows = extract_candidate_rows(
        hypothesis_graph=hypothesis_graph,
        root_conditioned_graphs=root_conditioned,
        initial_root_rankings=rankings,
    )
    values = rows[0]["feature_values"]

    assert len(rows[0]["features"]) == len(FEATURE_NAMES)
    assert values["target_coverage"] == 1.0
    assert values["mean_direction_no_direct_margin"] == pytest.approx(0.55)
    assert values["mean_path_length"] == 1.0
    assert rows[1]["feature_values"]["empty_graph"] == 1.0

    model = StatisticalListwiseReranker(
        RerankerModelConfig(hidden_dim=4, dropout=0.0)
    )
    example = RerankerExample("case", rows, gt_ip="D1")
    output = predict_example(
        model,
        example,
        [0.0] * len(FEATURE_NAMES),
        [1.0] * len(FEATURE_NAMES),
        torch.device("cpu"),
    )
    assert [row["ip"] for row in output] == ["D1", "D2"]
    assert all(math.isclose(row["reranker_delta"], 0.0, abs_tol=1e-7) for row in output)


def test_candidate_graph_verifier_scores_candidate_self_consistency():
    torch = pytest.importorskip("torch")
    from Sys.RootCauseAnalyze.stage1.candidate_graph_verifier import (
        CandidateConditionedGraphVerifier,
        CandidateGraphExample,
        CandidateGraphView,
        VerifierModelConfig,
        predict_example,
        score_example,
    )

    case = _case()
    vocabulary = EventVocabulary.fit([case], max_size=8)
    base_graph = PathConditionedGraphBuilder(vocabulary).build(
        case, include_labels=False
    )
    d1_graph = condition_graph_on_propagation_dag(
        base_graph, [("D1", "D2")], candidate_root="D1"
    )
    # Deliberately give D2 the D1-rooted graph: the verifier should reject it.
    d2_graph = condition_graph_on_propagation_dag(
        base_graph, [("D1", "D2")], candidate_root="D2"
    )

    class SelectedSourceBackbone(torch.nn.Module):
        def forward(self, batch):
            logits = torch.zeros(
                len(base_graph.device_ips),
                dtype=batch["edge_features"].dtype,
                device=batch["edge_features"].device,
            )
            selected = batch["edge_features"][:, 2]
            logits.index_add_(0, batch["edge_sources"], selected)
            return logits

    model = CandidateConditionedGraphVerifier(
        SelectedSourceBackbone(),
        VerifierModelConfig(max_correction_scale=2.0, gate_init=1.0),
    )
    example = CandidateGraphExample(
        dirpath=case.dirpath,
        gt_ip="D1",
        candidates=[
            CandidateGraphView("D1", 1, 0.5, 0.0, d1_graph, 0),
            CandidateGraphView("D2", 2, 0.5, 0.0, d2_graph, 1),
        ],
    )
    outputs = score_example(model, example, torch.device("cpu"))
    rankings = predict_example(model, example, torch.device("cpu"))

    assert outputs["verification_margins"].tolist() == pytest.approx([1.0, -1.0])
    assert rankings[0]["ip"] == "D1"
    assert rankings[0]["verification_top1"] is True
    assert rankings[1]["verification_top1"] is False


def test_graph_rerank_diagnostic_scores_path_evidence_without_labels():
    hypothesis_graph = {
        "edge_hypotheses": [
            {
                "edge_hypothesis_id": "H1",
                "endpoint_a": "D1",
                "endpoint_b": "D2",
                "state_probabilities": {
                    "endpoint_a_to_b": 0.8,
                    "endpoint_b_to_a": 0.0,
                    "no_direct_propagation": 0.2,
                },
            }
        ]
    }
    root_item = {
        "root_hypothesis": {"root_devices": ["D1"]},
        "explanation_score": 0.75,
        "propagation_graph": {
            "graph_score": 0.8,
            "target_coverage": 1.0,
            "covered_targets": ["D2"],
            "nodes": [
                {
                    "device_id": "D1",
                    "evidence_ids": ["E1"],
                    "onset_interval_ms": [0, 1],
                },
                {
                    "device_id": "D2",
                    "evidence_ids": ["E2"],
                    "onset_interval_ms": [2, 3],
                },
            ],
            "edges": [
                {
                    "edge_hypothesis_id": "H1",
                    "from": "D1",
                    "to": "D2",
                    "state_probability": 0.8,
                    "support_level": "strong",
                    "evidence_ids": ["E1", "E2"],
                    "features": {
                        "temporal_available": True,
                        "temporal_order_support": 1.0,
                        "contradiction": 0.0,
                    },
                }
            ],
            "diagnostics": {
                "target_count": 1,
                "reachable_target_count": 1,
                "uncovered_targets": [],
            },
        },
    }

    scored = score_candidate_graph(
        root_item=root_item,
        hypothesis_graph=hypothesis_graph,
        max_path_depth=8,
    )

    assert scored["components"]["edge_direction_preference"] == pytest.approx(0.8)
    assert scored["components"]["target_path_support"] == pytest.approx(0.8)
    assert scored["components"]["root_earliness"] == 1.0
    assert scored["scores"]["structured_reasonableness"] > 0.7


def test_graph_rerank_diagnostic_reports_correctable_and_corruption_risk():
    def candidate(ip, rank, score, edges):
        return {
            "ip": ip,
            "initial_rank": rank,
            "scores": {"structured_reasonableness": score},
            "selected_edges": [
                {"from": source, "to": target} for source, target in edges
            ],
        }

    cases = [
        {
            "gt_ip": "D1",
            "candidates": [
                candidate("D2", 1, 0.5, [("D2", "D3")]),
                candidate("D1", 2, 0.8, [("D1", "D3")]),
            ],
        },
        {
            "gt_ip": "D1",
            "candidates": [
                candidate("D1", 1, 0.8, [("D1", "D3")]),
                candidate("D2", 2, 0.7, [("D2", "D3")]),
            ],
        },
    ]

    metrics = evaluate_score_method(
        cases,
        "structured_reasonableness",
        tie_epsilon=1e-6,
        thresholds=[0.0, 0.2, 0.4],
    )
    diversity = graph_diversity(cases[0]["candidates"])

    assert metrics["pairwise_win_rate"] == 1.0
    assert metrics["gt_vs_strongest_false_win_rate"] == 1.0
    assert metrics["fractional_graph_best_lift"]["ci95_low"] == 0.5
    assert metrics["correctable_cases"] == 1
    assert metrics["strict_graph_top1_correctable_cases"] == 1
    assert metrics["wrong_preference_cases"] == 0
    assert metrics["threshold_sweep"][0]["corrections"] == 1
    assert metrics["threshold_sweep"][0]["corruptions"] == 0
    assert diversity["mean_pairwise_jaccard_distance"] == 1.0
