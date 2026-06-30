import json
import os
import tempfile
import unittest

from Sys.RootCauseAnalyze.confidence_gate import assess_gate, make_bypass_response
from Sys.RootCauseAnalyze.trust_trees.router import route_with_trust_trees
from Sys.RootCauseAnalyze.trust_trees.temporal_tree import assess_temporal_tree
from Sys.RootCauseAnalyze.trust_trees.topo_tree import assess_topo_tree


def _rankings(items, score_key):
    return [
        {"rank": i + 1, "ip": ip, score_key: score, **extra}
        for i, (ip, score, extra) in enumerate(items)
    ]


def _skill_ret(
    *,
    combined,
    topo,
    temporal,
    topo_meta=None,
    temporal_meta=None,
):
    payload = {
        "combined_score_rankings": _rankings(combined, "combined_score"),
        "topo": {"rankings": _rankings(topo, "pr_score"), **(topo_meta or {})},
        "temporal": {"rankings": _rankings(temporal, "score"), **(temporal_meta or {})},
    }
    return json.dumps(payload, ensure_ascii=False)


class TrustTreeUnitTest(unittest.TestCase):
    def test_topo_tree_strong_when_shape_and_algorithm_evidence_hold(self):
        tree = assess_topo_tree(
            {
                "rankings": _rankings(
                    [
                        ("10.0.0.1", 98.0, {"cross": 3, "high_weight_alarm_hit": True}),
                        ("10.0.0.2", 70.0, {"cross": 0}),
                        ("10.0.0.3", 66.0, {"cross": 0}),
                    ],
                    "pr_score",
                ),
                "diagnostics": {
                    "directed_top3": ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
                    "undirected_top3": ["10.0.0.1", "10.0.0.4", "10.0.0.5"],
                },
            }
        )

        self.assertEqual(tree["state"], "strong")
        self.assertIn("directed_undirected_top1_match", tree["passed"])
        self.assertIn("top1_high_weight_alarm", tree["passed"])

    def test_topo_tree_weak_when_ranking_is_flat_and_no_algorithm_evidence(self):
        tree = assess_topo_tree(
            {
                "rankings": _rankings(
                    [
                        ("10.0.0.1", 10.0, {"cross": 0, "seed_type": "baseline"}),
                        ("10.0.0.2", 9.9, {"cross": 0, "seed_type": "baseline"}),
                        ("10.0.0.3", 9.8, {"cross": 0, "seed_type": "baseline"}),
                    ],
                    "pr_score",
                ),
                "diagnostics": {
                    "directed_top3": ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
                    "undirected_top3": ["10.0.0.4", "10.0.0.5", "10.0.0.6"],
                },
            }
        )

        self.assertEqual(tree["state"], "weak")
        self.assertIn("topo_ranking_shape_ok", tree["failed"])
        self.assertIn("topo_algorithm_evidence_ok", tree["failed"])

    def test_temporal_tree_strong_when_two_subsignals_support_top1(self):
        tree = assess_temporal_tree(
            {
                "rankings": _rankings(
                    [
                        (
                            "10.0.0.1",
                            0.95,
                            {
                                "total_alarms": 4,
                                "total_logs": 1,
                                "burst_score": 1.0,
                                "early_bird_score": 1.0,
                                "density_score": 0.8,
                            },
                        ),
                        ("10.0.0.2", 0.5, {"total_alarms": 2}),
                        ("10.0.0.3", 0.4, {"total_alarms": 1}),
                    ],
                    "score",
                ),
                "diagnostics": {
                    "ref_time_ms": 123,
                    "devices_with_timestamps": 3,
                    "burst_top3": ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
                    "early_top3": ["10.0.0.1", "10.0.0.4", "10.0.0.5"],
                    "density_top3": ["10.0.0.6", "10.0.0.1", "10.0.0.7"],
                },
            }
        )

        self.assertEqual(tree["state"], "strong")
        self.assertIn("top1_supported_by_two_temporal_subsignals", tree["passed"])

    def test_temporal_tree_weak_when_time_data_is_missing(self):
        tree = assess_temporal_tree(
            {
                "rankings": _rankings(
                    [
                        ("10.0.0.1", 0.9, {"total_alarms": 0, "total_logs": 0}),
                        ("10.0.0.2", 0.8, {"total_alarms": 0, "total_logs": 0}),
                    ],
                    "score",
                ),
                "diagnostics": {"ref_time_ms": None, "devices_with_timestamps": 0},
            }
        )

        self.assertEqual(tree["state"], "weak")
        self.assertIn("temporal_data_available", tree["failed"])


class TrustTreeRouterTest(unittest.TestCase):
    def test_rank_near_accepts_combined(self):
        gate = route_with_trust_trees(
            combined_ips=["10.0.0.9", "10.0.0.1", "10.0.0.2"],
            topo_ips=["10.0.0.1", "10.0.0.2", "10.0.0.3"],
            temporal_ips=["10.0.0.4", "10.0.0.2", "10.0.0.1"],
            topo_tree={"state": "uncertain", "passed": [], "failed": [], "evidence": {}},
            temporal_tree={"state": "uncertain", "passed": [], "failed": [], "evidence": {}},
        )

        self.assertEqual(gate["decision"], "bypass_llm")
        self.assertEqual(gate["route"], "combined")
        self.assertEqual(gate["reason"], "rankers_near_accept_combined")

    def test_confident_single_ranker_routes_to_that_ranker(self):
        gate = route_with_trust_trees(
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1", "10.0.0.2", "10.0.0.3"],
            temporal_ips=["10.0.0.4", "10.0.0.5", "10.0.0.6"],
            topo_tree={"state": "strong", "passed": [], "failed": [], "evidence": {}},
            temporal_tree={"state": "weak", "passed": [], "failed": [], "evidence": {}},
        )

        self.assertEqual(gate["decision"], "bypass_llm")
        self.assertEqual(gate["route"], "topo")
        self.assertEqual(gate["recommended_ips"][:3], ["10.0.0.1", "10.0.0.2", "10.0.0.3"])

    def test_confident_disagreement_invokes_llm(self):
        gate = route_with_trust_trees(
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1", "10.0.0.2", "10.0.0.3"],
            temporal_ips=["10.0.0.4", "10.0.0.5", "10.0.0.6"],
            topo_tree={"state": "strong", "passed": [], "failed": [], "evidence": {}},
            temporal_tree={"state": "strong", "passed": [], "failed": [], "evidence": {}},
        )

        self.assertEqual(gate["decision"], "invoke_llm")
        self.assertEqual(gate["route"], "llm")

    def test_two_weak_rankers_routes_to_operator_review(self):
        gate = route_with_trust_trees(
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1"],
            temporal_ips=["10.0.0.4"],
            topo_tree={"state": "weak", "passed": [], "failed": [], "evidence": {}},
            temporal_tree={"state": "weak", "passed": [], "failed": [], "evidence": {}},
        )

        self.assertEqual(gate["decision"], "operator_review")
        self.assertEqual(gate["route"], "operator")


class ConfidenceGateTrustTreeIntegrationTest(unittest.TestCase):
    def test_assess_gate_returns_trust_tree_v1_schema(self):
        gate = assess_gate(
            _skill_ret(
                combined=[
                    ("10.0.0.1", 95.0, {}),
                    ("10.0.0.2", 80.0, {}),
                    ("10.0.0.3", 70.0, {}),
                ],
                topo=[
                    ("10.0.0.1", 98.0, {"cross": 3, "high_weight_alarm_hit": True}),
                    ("10.0.0.2", 70.0, {"cross": 0}),
                    ("10.0.0.3", 60.0, {"cross": 0}),
                ],
                temporal=[
                    ("10.0.0.1", 0.9, {"total_alarms": 2, "burst_score": 1.0, "density_score": 0.8}),
                    ("10.0.0.4", 0.4, {"total_alarms": 1}),
                    ("10.0.0.5", 0.3, {"total_alarms": 1}),
                ],
                topo_meta={
                    "diagnostics": {
                        "directed_top3": ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
                        "undirected_top3": ["10.0.0.1", "10.0.0.6", "10.0.0.7"],
                    }
                },
                temporal_meta={
                    "diagnostics": {
                        "ref_time_ms": 123,
                        "devices_with_timestamps": 3,
                        "burst_top3": ["10.0.0.1", "10.0.0.4"],
                        "early_top3": ["10.0.0.1"],
                        "density_top3": ["10.0.0.1"],
                    }
                },
            )
        )

        self.assertEqual(gate["policy_version"], "trust_tree_v1")
        self.assertEqual(gate["decision"], "bypass_llm")
        self.assertEqual(gate["route"], "combined")
        self.assertIn("trust_trees", gate)
        self.assertEqual(gate["trust_trees"]["topo"]["state"], "strong")

    def test_operator_review_response_has_empty_ip_list(self):
        response = make_bypass_response(
            {
                "decision": "operator_review",
                "route": "operator",
                "reason": "both_rankers_weak_operator_review",
                "recommended_ips": ["10.0.0.1", "10.0.0.2"],
            }
        )
        payload = json.loads(response.split("```json\n", 1)[1].rsplit("\n```", 1)[0])

        self.assertEqual(payload["ip"], [])
        self.assertIn("operator_review", payload["reasoning"])


class TrustGateEvaluationTest(unittest.TestCase):
    def test_evaluates_routes_from_skillpipe_records(self):
        from Sys.Score.evaluate_trust_gate import evaluate_trust_gate

        records = [
            {
                "dir": "/cases/case-combined",
                "skill_ips": ["10.0.0.1", "10.0.0.2"],
                "gt_ips": ["10.0.0.1"],
                "response": "unused",
                "skill_details": {
                    "combined": {"topk": [["10.0.0.1", 0.9], ["10.0.0.2", 0.6]]},
                    "1": {"topk": [["10.0.0.1", 0.9], ["10.0.0.2", 0.6]], "trust_tree": {"state": "strong"}},
                    "2": {"topk": [["10.0.0.1", 0.8], ["10.0.0.3", 0.5]], "trust_tree": {"state": "strong"}},
                },
            },
            {
                "dir": "/cases/case-operator",
                "skill_ips": ["10.0.0.9", "10.0.0.8"],
                "gt_ips": ["10.0.0.7"],
                "response": "unused",
                "skill_details": {
                    "combined": {"topk": [["10.0.0.9", 0.3], ["10.0.0.8", 0.29]]},
                    "1": {"topk": [["10.0.0.9", 0.3]], "trust_tree": {"state": "weak"}},
                    "2": {"topk": [["10.0.0.8", 0.3]], "trust_tree": {"state": "weak"}},
                },
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            summary = evaluate_trust_gate(records, out_dir=tmp)

            self.assertEqual(summary["total_cases"], 2)
            self.assertEqual(summary["route_counts"]["combined"], 1)
            self.assertEqual(summary["route_counts"]["operator"], 1)
            self.assertTrue(os.path.exists(os.path.join(tmp, "trust_gate_cases.jsonl")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "trust_gate_summary.json")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "trust_gate_by_route.csv")))


if __name__ == "__main__":
    unittest.main()
