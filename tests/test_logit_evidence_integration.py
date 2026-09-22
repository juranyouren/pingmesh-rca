"""Wiring tests for ``logit_evidence_v1`` inside the M1 pipeline.

These pin the contract the new method has to honour *and* the contracts it must
not disturb: adding a fourth scoring method may not change what the three
existing ones emit.
"""
import unittest

DEVICE_A = "10.0.0.1"
DEVICE_B = "10.0.0.2"


def episode(
    eid,
    device_id,
    predicate,
    *,
    event_type,
    peer_raw="",
    peer_resolution=None,
    possible_effects=(),
    cause_hint=None,
    interval=None,
    timestamp_quality=0.0,
    mapping_confidence=0.95,
):
    item = {
        "evidence_id": eid,
        "device_id": device_id,
        "predicate": predicate,
        "event_type": event_type,
        "object_type": "interface",
        "object": "GE1/0/0",
        "peer_raw": peer_raw,
        "lifecycle": "raised",
        "onset_interval_ms": interval,
        "quality": {"timestamp": timestamp_quality, "core": mapping_confidence,
                    "description": mapping_confidence},
        "possible_effects": list(possible_effects),
        "incident_relevance": 0.6,
    }
    if peer_resolution is not None:
        item["peer_resolution"] = peer_resolution
    if cause_hint is not None:
        item["cause_hint"] = cause_hint
    return item


def resolved(device_id, confidence=1.0):
    return {
        "status": "resolved",
        "candidates": [{"device_id": device_id, "confidence": confidence,
                        "source": "inventory:mgmt_ip"}],
        "reason": "declared_device_identity",
    }


CANDIDATE_GRAPH = {
    "nodes": [{"device_id": DEVICE_A}, {"device_id": DEVICE_B}],
    "edges": [
        {
            "endpoint_a": DEVICE_A,
            "endpoint_b": DEVICE_B,
            "edge_type": "physical",
            "topology_edge_ids": ["L-aaa"],
            "group_ids": [],
        }
    ],
}

STRONG_EPISODES = [
    episode("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down"),
    episode(
        "EB1",
        DEVICE_B,
        "bgp_adjacency_down",
        event_type="bgp_session_down",
        peer_raw="10.0.0.1",
        peer_resolution=resolved(DEVICE_A),
        possible_effects=["adjacency_loss", "path_degradation"],
        cause_hint={"predicate": "interface_flap", "quote": "flap",
                    "source": "explicit_log_semantics"},
    ),
]

WEAK_EPISODES = [
    episode("EA1", DEVICE_A, "device_restart", event_type="device_health"),
    episode("EB1", DEVICE_B, "incident_local_event", event_type="generic_event"),
]


def config_for(method, **overrides):
    from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig

    return PropagationConfig(edge_probability_method=method, **overrides)


def scored_hypothesis(episodes, method="logit_evidence_v1", **overrides):
    from Sys.RootCauseAnalyze.propagation.m1.probability import (
        assign_edge_state_probabilities,
    )
    from Sys.RootCauseAnalyze.propagation.scorer import build_edge_relation_graph

    config = config_for(method, **overrides)
    raw = build_edge_relation_graph(CANDIDATE_GRAPH, episodes, config=config)
    hypothesis = raw["edge_hypotheses"][0]
    return hypothesis, assign_edge_state_probabilities(hypothesis, config=config)


class SchemaTests(unittest.TestCase):
    def test_logit_evidence_v1_is_an_accepted_method(self):
        from Sys.RootCauseAnalyze.propagation.schema import normalize_config

        config = normalize_config(config_for("logit_evidence_v1"))

        self.assertEqual(config.edge_probability_method, "logit_evidence_v1")

    def test_existing_methods_remain_accepted(self):
        from Sys.RootCauseAnalyze.propagation.schema import normalize_config

        for method in ("deterministic_evidence_v1", "logit_softmax_v1"):
            self.assertEqual(
                normalize_config(config_for(method)).edge_probability_method, method
            )

    def test_unknown_method_is_still_rejected(self):
        from Sys.RootCauseAnalyze.propagation.schema import normalize_config

        with self.assertRaises(ValueError):
            normalize_config(config_for("not_a_method_v1"))

    def test_model_path_is_configurable(self):
        from Sys.RootCauseAnalyze.propagation.schema import normalize_config

        config = normalize_config(
            config_for("logit_evidence_v1", edge_evidence_model_path="somewhere.json")
        )

        self.assertEqual(config.edge_evidence_model_path, "somewhere.json")


class ScorerEvidenceTests(unittest.TestCase):
    def test_scorer_emits_pair_evidence_terms(self):
        from Sys.RootCauseAnalyze.propagation.scorer import build_edge_relation_graph

        raw = build_edge_relation_graph(
            CANDIDATE_GRAPH, STRONG_EPISODES, config=config_for("logit_evidence_v1")
        )

        pair = raw["edge_hypotheses"][0]["pair_evidence"]
        self.assertEqual(pair["edge_type"], "physical")
        self.assertTrue(
            any(term["pattern"] == "explicit_cause" for term in pair["terms"])
        )

    def test_pair_evidence_is_present_regardless_of_scoring_method(self):
        """Extraction is root-independent; only the scoring policy is method-specific."""
        from Sys.RootCauseAnalyze.propagation.scorer import build_edge_relation_graph

        raw = build_edge_relation_graph(
            CANDIDATE_GRAPH, STRONG_EPISODES, config=config_for("deterministic_evidence_v1")
        )

        self.assertIn("pair_evidence", raw["edge_hypotheses"][0])

    def test_resolution_gates_the_terms_attribution(self):
        """Attribution reaches the scorer through the resolver's annotation."""
        from Sys.RootCauseAnalyze.propagation.scorer import build_edge_relation_graph

        unresolved = [
            STRONG_EPISODES[0],
            {**STRONG_EPISODES[1],
             "peer_resolution": {"status": "unresolved", "candidates": [],
                                 "reason": "no_declared_identity_or_topology_relation"}},
        ]

        raw = build_edge_relation_graph(
            CANDIDATE_GRAPH, unresolved, config=config_for("logit_evidence_v1")
        )
        terms = raw["edge_hypotheses"][0]["pair_evidence"]["terms"]

        self.assertTrue(terms)
        self.assertTrue(all(term["attribution"] == 0.0 for term in terms))


class DirectionalContributionTests(unittest.TestCase):
    def test_edge_hypothesis_carries_the_directional_contract(self):
        _, hypothesis = scored_hypothesis(STRONG_EPISODES)

        self.assertEqual(hypothesis["probability_method"], "logit_evidence_v1")
        self.assertEqual(
            set(hypothesis["state_probabilities"]),
            {"endpoint_a_to_b", "endpoint_b_to_a", "no_direct_propagation"},
        )
        details = hypothesis["probability_details"]
        for key in ("a_to_b_score", "b_to_a_score", "no_direct_score"):
            self.assertIn(key, details)
        self.assertEqual(
            details["features"].keys(),
            {"semantic_available", "temporal_available", "attribution_available"},
        )
        self.assertTrue(details["contributions"])
        for item in details["contributions"]:
            self.assertIn(item["direction"], {"a_to_b", "b_to_a"})
            self.assertIn("reason", item)

    def test_directional_scores_are_not_renormalised_into_a_simplex(self):
        """The whole point of independent directions: they need not sum to one."""
        _, hypothesis = scored_hypothesis(STRONG_EPISODES)

        probabilities = hypothesis["state_probabilities"]
        total = sum(probabilities.values())

        self.assertGreater(total, 1.0)
        # ``state_probabilities`` are rounded to 6 places by contract; a
        # renormalised value would differ from the raw score by far more.
        self.assertAlmostEqual(
            probabilities["endpoint_a_to_b"],
            hypothesis["probability_details"]["a_to_b_score"],
            places=6,
        )

    def test_strong_evidence_raises_the_forward_direction_only(self):
        _, hypothesis = scored_hypothesis(STRONG_EPISODES)

        probabilities = hypothesis["state_probabilities"]
        self.assertGreater(
            probabilities["endpoint_a_to_b"], probabilities["endpoint_b_to_a"]
        )

    def test_weak_evidence_leaves_both_directions_low(self):
        _, hypothesis = scored_hypothesis(WEAK_EPISODES)

        probabilities = hypothesis["state_probabilities"]
        self.assertLess(probabilities["endpoint_a_to_b"], 0.15)
        self.assertLess(probabilities["endpoint_b_to_a"], 0.15)
        self.assertGreater(probabilities["no_direct_propagation"], 0.8)

    def test_direction_ordering_survives_endpoint_ordering(self):
        """Swapping the endpoints must swap the scores, not change them."""
        from Sys.RootCauseAnalyze.propagation.m1.probability import (
            assign_edge_state_probabilities,
        )
        from Sys.RootCauseAnalyze.propagation.scorer import build_edge_relation_graph

        reversed_graph = {
            "edges": [{**CANDIDATE_GRAPH["edges"][0],
                       "endpoint_a": DEVICE_B, "endpoint_b": DEVICE_A}]
        }
        config = config_for("logit_evidence_v1")
        raw = build_edge_relation_graph(reversed_graph, STRONG_EPISODES, config=config)
        hypothesis = assign_edge_state_probabilities(
            raw["edge_hypotheses"][0], config=config
        )
        forward, backward = scored_hypothesis(STRONG_EPISODES)

        self.assertAlmostEqual(
            hypothesis["state_probabilities"]["endpoint_a_to_b"],
            backward["state_probabilities"]["endpoint_b_to_a"],
            places=9,
        )


class DirectionSelectionScaleTests(unittest.TestCase):
    """Pins the scale change the independent-direction model introduces.

    ``m2.infer`` admits a direction when ``probability > no_direct``. Under the
    three-state methods ``no_direct`` is a normalised share, so clearing
    ``min_edge_support`` (0.25) is usually enough. Under independent directions
    ``no_direct = (1 - a)(1 - b)`` stays large, so a direction has to clear
    roughly 0.5 instead. This is a threshold-scale change, not a bug, and it is
    why the downstream thresholds still need re-tuning.
    """

    def test_a_direction_above_min_edge_support_can_still_be_dropped(self):
        _, hypothesis = scored_hypothesis(STRONG_EPISODES)

        probabilities = hypothesis["state_probabilities"]
        self.assertGreater(probabilities["endpoint_a_to_b"], 0.25)
        self.assertLess(
            probabilities["endpoint_a_to_b"], probabilities["no_direct_propagation"]
        )

    def test_a_strong_enough_pair_does_survive_the_no_direct_comparison(self):
        episodes = [
            episode("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down",
                    interval=[0, 1_000], timestamp_quality=1.0),
            episode("EB1", DEVICE_B, "bgp_adjacency_down", event_type="bgp_session_down",
                    peer_raw="10.0.0.1", peer_resolution=resolved(DEVICE_A),
                    possible_effects=["adjacency_loss"],
                    cause_hint={"predicate": "interface_flap", "quote": "flap",
                                "source": "explicit_log_semantics"},
                    interval=[3_000, 4_000], timestamp_quality=1.0),
        ]

        _, hypothesis = scored_hypothesis(episodes)
        probabilities = hypothesis["state_probabilities"]

        self.assertGreater(probabilities["endpoint_a_to_b"], 0.7)
        self.assertGreater(
            probabilities["endpoint_a_to_b"], probabilities["no_direct_propagation"]
        )


class ResolutionWiringTests(unittest.TestCase):
    NODES = [
        {"name": "PE-1", "mgmt_ip": "10.0.0.1", "role": "PE", "alarms": [], "logs": []},
        {"name": "PE-2", "mgmt_ip": "10.0.0.2", "role": "PE", "alarms": [], "logs": []},
    ]
    INFO = {"source_ip": '["10.0.0.1"]', "sink_ip": '["10.0.0.2"]',
            "alarm_time": 1_800_000_000_000}
    CONTEXT = {
        "schema_version": "topology-context-v1",
        "nodes": [{"device_id": "10.0.0.1", "name": "PE-1"},
                  {"device_id": "10.0.0.2", "name": "PE-2"}],
        "edges": [{"edge_id": "L-aaa", "endpoint_a": "10.0.0.1", "endpoint_a_port": "GE1/0/0",
                   "endpoint_b": "10.0.0.2", "endpoint_b_port": "GE1/0/1"}],
    }

    def reconstruct(self, episodes, method="logit_evidence_v1"):
        from Sys.RootCauseAnalyze.propagation.m1.reconstruct import (
            reconstruct_hypothesis_graph,
        )

        return reconstruct_hypothesis_graph(
            nodes=self.NODES,
            info=self.INFO,
            topology_context=self.CONTEXT,
            evidence_episodes=episodes,
            config=config_for(method),
        )

    def test_m1_resolves_peer_entities_before_scoring(self):
        graph = self.reconstruct(
            [episode("EB1", "10.0.0.2", "bgp_adjacency_down",
                     event_type="bgp_session_down", peer_raw="10.0.0.1")]
        )

        resolution = graph["evidence_map"]["EB1"]["peer_resolution"]
        self.assertEqual(resolution["status"], "resolved")
        self.assertEqual(resolution["candidates"][0]["device_id"], "10.0.0.1")

    def test_m1_leaves_an_unresolvable_peer_unresolved(self):
        graph = self.reconstruct(
            [episode("EB1", "10.0.0.2", "bgp_adjacency_down",
                     event_type="bgp_session_down", peer_raw="28.219.131.16")]
        )

        resolution = graph["evidence_map"]["EB1"]["peer_resolution"]
        self.assertEqual(resolution["status"], "unresolved")
        self.assertEqual(resolution["candidates"], [])

    def test_raw_peer_token_survives_resolution(self):
        graph = self.reconstruct(
            [episode("EB1", "10.0.0.2", "bgp_adjacency_down",
                     event_type="bgp_session_down", peer_raw="10.0.0.1")]
        )

        self.assertEqual(graph["evidence_map"]["EB1"]["peer_raw"], "10.0.0.1")


class ExistingMethodRegressionTests(unittest.TestCase):
    def test_deterministic_method_still_normalises(self):
        _, hypothesis = scored_hypothesis(STRONG_EPISODES, method="deterministic_evidence_v1")

        self.assertAlmostEqual(sum(hypothesis["state_probabilities"].values()), 1.0, places=6)

    def test_logit_softmax_method_still_normalises(self):
        _, hypothesis = scored_hypothesis(STRONG_EPISODES, method="logit_softmax_v1")

        self.assertAlmostEqual(sum(hypothesis["state_probabilities"].values()), 1.0, places=6)

    def test_deterministic_method_ignores_the_new_evidence_terms(self):
        _, hypothesis = scored_hypothesis(STRONG_EPISODES, method="deterministic_evidence_v1")

        self.assertEqual(hypothesis["probability_method"], "deterministic_evidence_v1")
        self.assertNotIn("a_to_b_score", hypothesis.get("probability_details", {}))


if __name__ == "__main__":
    unittest.main()
