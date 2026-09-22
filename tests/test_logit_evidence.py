"""Behaviour tests for the ``logit_evidence_v1`` directional evidence model.

The model scores the two directions of a device pair independently. These tests
pin the behaviour that matters: attribution gates semantic evidence, temporal
evidence stays interval-based and quality-gated, the prior is edge-type
conditioned, and every contribution is explainable.

They are behaviour tests, not accuracy tests. The LR table is an uncalibrated
placeholder; nothing here asserts a statistically optimal number.
"""
import math
import unittest

DEVICE_A = "10.0.0.1"
DEVICE_B = "10.0.0.2"


def ep(
    eid,
    device_id,
    predicate,
    *,
    event_type=None,
    state="down",
    peer_raw="",
    peer_resolution=None,
    possible_effects=(),
    cause_hint=None,
    interval=None,
    timestamp_quality=0.0,
    mapping_confidence=0.95,
    lifecycle="raised",
):
    """Build an episode shaped like Sys.Preprocess.evidence.adapter.to_episodes."""

    episode = {
        "evidence_id": eid,
        "device_id": device_id,
        "predicate": predicate,
        "event_type": event_type or "generic_event",
        "object_type": "interface",
        "object": "GE1/0/0",
        "peer_raw": peer_raw,
        "lifecycle": lifecycle,
        "onset_interval_ms": interval,
        "quality": {
            "timestamp": timestamp_quality,
            "description": mapping_confidence,
            "core": mapping_confidence,
        },
        "possible_effects": list(possible_effects),
    }
    if peer_resolution is not None:
        episode["peer_resolution"] = peer_resolution
    elif peer_raw:
        episode["peer_resolution"] = {
            "status": "unresolved",
            "candidates": [],
            "reason": "no_declared_identity_or_topology_relation",
        }
    if cause_hint is not None:
        episode["cause_hint"] = cause_hint
    return episode


def resolved(device_id, confidence=1.0):
    return {
        "status": "resolved",
        "candidates": [{"device_id": device_id, "confidence": confidence, "source": "inventory:mgmt_ip"}],
        "reason": "declared_device_identity",
    }


def ambiguous(first, second, confidence=0.5):
    return {
        "status": "ambiguous",
        "candidates": [
            {"device_id": first, "confidence": confidence, "source": "inventory:name"},
            {"device_id": second, "confidence": confidence, "source": "inventory:name"},
        ],
        "reason": "multiple_devices_declare_this_identity",
    }


def evidence_for(a_episodes, b_episodes, *, edge_type="physical", model=None, uncertainty_ms=5000):
    from Sys.RootCauseAnalyze.propagation.evidence_logit import (
        build_pair_evidence,
        load_evidence_model,
    )

    return build_pair_evidence(
        DEVICE_A,
        DEVICE_B,
        a_episodes,
        b_episodes,
        edge_type=edge_type,
        model=model or load_evidence_model(),
        timestamp_uncertainty_ms=uncertainty_ms,
    )


def scores(pair_evidence, *, edge_type="physical", model=None):
    """Assemble the two directional scores the way m1.probability does."""

    from Sys.RootCauseAnalyze.propagation.evidence_logit import (
        directional_scores,
        load_evidence_model,
    )

    return directional_scores(
        pair_evidence, model=model or load_evidence_model(), edge_type=edge_type
    )


class NoEvidenceTests(unittest.TestCase):
    def test_case1_no_evidence_keeps_both_directions_low(self):
        pair = evidence_for([], [])

        result = scores(pair)

        self.assertLess(result["a_to_b_score"], 0.15)
        self.assertLess(result["b_to_a_score"], 0.15)

    def test_case1_no_direct_mass_dominates_when_nothing_is_observed(self):
        pair = evidence_for([], [])

        result = scores(pair)

        self.assertGreater(result["no_direct_score"], 0.8)

    def test_case9_both_directions_may_be_low_without_a_forced_choice(self):
        """A pair with no evidence must not be forced to pick a direction."""
        pair = evidence_for([], [])

        result = scores(pair)

        self.assertLess(result["a_to_b_score"], result["no_direct_score"])
        self.assertLess(result["b_to_a_score"], result["no_direct_score"])
        self.assertAlmostEqual(
            result["a_to_b_score"], result["b_to_a_score"], places=9
        )


class SemanticCausalityTests(unittest.TestCase):
    def cause_hint(self, predicate="interface_flap"):
        return {"predicate": predicate, "quote": "interface flap", "source": "explicit_log_semantics"}

    def test_case3_resolved_peer_plus_explicit_cause_raises_forward_only(self):
        a_episodes = [
            ep("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down")
        ]
        b_episodes = [
            ep(
                "EB1",
                DEVICE_B,
                "bgp_adjacency_down",
                event_type="bgp_session_down",
                peer_raw="10.0.0.1",
                peer_resolution=resolved(DEVICE_A),
                possible_effects=["adjacency_loss", "path_degradation"],
                cause_hint=self.cause_hint(),
            )
        ]

        result = scores(evidence_for(a_episodes, b_episodes))

        self.assertGreater(result["a_to_b_score"], 0.2)
        self.assertLess(result["b_to_a_score"], result["a_to_b_score"])

    def test_case2_unresolvable_peer_neutralises_a_strong_cause_hint(self):
        a_episodes = [
            ep("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down")
        ]
        b_episodes = [
            ep(
                "EB1",
                DEVICE_B,
                "bgp_adjacency_down",
                event_type="bgp_session_down",
                peer_raw="28.219.131.16",
                peer_resolution={
                    "status": "unresolved",
                    "candidates": [],
                    "reason": "no_declared_identity_or_topology_relation",
                },
                possible_effects=["adjacency_loss", "path_degradation"],
                cause_hint=self.cause_hint(),
            )
        ]

        result = scores(evidence_for(a_episodes, b_episodes))

        self.assertLess(result["a_to_b_score"], 0.1)
        self.assertFalse(result["features"]["attribution_available"])

    def test_case4_ambiguous_peer_damps_the_contribution(self):
        a_episodes = [
            ep("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down")
        ]
        resolved_variant = scores(
            evidence_for(
                a_episodes,
                [
                    ep(
                        "EB1", DEVICE_B, "bgp_adjacency_down", event_type="bgp_session_down",
                        peer_raw="10.0.0.1", peer_resolution=resolved(DEVICE_A),
                        possible_effects=["adjacency_loss"], cause_hint=self.cause_hint(),
                    )
                ],
            )
        )
        ambiguous_variant = scores(
            evidence_for(
                a_episodes,
                [
                    ep(
                        "EB1", DEVICE_B, "bgp_adjacency_down", event_type="bgp_session_down",
                        peer_raw="SPINE", peer_resolution=ambiguous(DEVICE_A, "10.0.0.3"),
                        possible_effects=["adjacency_loss"], cause_hint=self.cause_hint(),
                    )
                ],
            )
        )

        self.assertLess(ambiguous_variant["a_to_b_score"], resolved_variant["a_to_b_score"])
        self.assertGreater(ambiguous_variant["a_to_b_score"], 0.02)

    def test_possible_effect_yields_weaker_evidence_than_an_explicit_cause(self):
        a_episodes = [
            ep("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down")
        ]
        explicit = scores(
            evidence_for(
                a_episodes,
                [
                    ep("EB1", DEVICE_B, "bgp_adjacency_down", event_type="bgp_session_down",
                       possible_effects=["adjacency_loss"], cause_hint=self.cause_hint())
                ],
            )
        )
        inferred = scores(
            evidence_for(
                a_episodes,
                [
                    ep("EB1", DEVICE_B, "bgp_adjacency_down", event_type="bgp_session_down",
                       possible_effects=["adjacency_loss"])
                ],
            )
        )

        self.assertGreater(explicit["a_to_b_score"], inferred["a_to_b_score"])
        self.assertGreater(inferred["a_to_b_score"], 0.02)

    def test_rule_path_episodes_are_semantically_scored_by_event_type(self):
        """The rule path names an ``event_type`` and no ``predicate`` at all."""
        a_episodes = [ep("EA1", DEVICE_A, "", event_type="physical_link_down")]
        b_episodes = [ep("EB1", DEVICE_B, "", event_type="bgp_session_down")]

        pair = evidence_for(a_episodes, b_episodes)

        self.assertTrue(
            any(term["pattern"] == "possible_effect" for term in pair["terms"])
        )
        self.assertGreater(scores(pair)["a_to_b_score"], 0.05)

    def test_case10_peer_resolution_alone_creates_no_semantic_contribution(self):
        """Attribution links evidence to the pair; it is never itself a symptom."""
        a_episodes = [ep("EA1", DEVICE_A, "device_restart", event_type="device_health")]
        b_episodes = [
            ep(
                "EB1", DEVICE_B, "lldp_neighbor_rebuild", event_type="lldp_neighbor_recovery",
                peer_raw="10.0.0.1", peer_resolution=resolved(DEVICE_A),
                interval=[0, 10_000],
            )
        ]

        pair = evidence_for(a_episodes, b_episodes)
        semantic_patterns = [
            term for term in pair["terms"] if term["kind"] == "semantic"
        ]
        result = scores(pair)

        self.assertEqual(semantic_patterns, [])
        self.assertLess(result["a_to_b_score"], 0.15)

    def test_derivative_to_physical_is_negative_evidence(self):
        a_episodes = [
            ep("EA1", DEVICE_A, "bgp_adjacency_down", event_type="bgp_session_down")
        ]
        b_episodes = [
            ep("EB1", DEVICE_B, "interface_flap", event_type="interface_state_down")
        ]

        result = scores(evidence_for(a_episodes, b_episodes))

        self.assertLess(result["a_to_b_score"], result["b_to_a_score"])

    def test_physical_to_derivative_is_weak_positive_evidence(self):
        a_episodes = [
            ep("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down")
        ]
        b_episodes = [
            ep("EB1", DEVICE_B, "bgp_adjacency_down", event_type="bgp_session_down")
        ]

        result = scores(evidence_for(a_episodes, b_episodes))

        self.assertGreater(result["a_to_b_score"], result["b_to_a_score"])
        self.assertGreater(result["a_to_b_score"], 0.02)


class TemporalDirectionTests(unittest.TestCase):
    def pair_with_intervals(self, a_interval, b_interval, a_quality=1.0, b_quality=1.0):
        """Two symptoms with no semantic relation, so only time speaks.

        The second predicate is deliberately outside every semantic table and
        every event-type class; otherwise the semantic axis would leak into a
        test that is meant to isolate the temporal one.
        """
        a_episodes = [
            ep("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down",
               interval=a_interval, timestamp_quality=a_quality)
        ]
        b_episodes = [
            ep("EB1", DEVICE_B, "incident_local_event", event_type="generic_event",
               interval=b_interval, timestamp_quality=b_quality)
        ]
        return evidence_for(a_episodes, b_episodes)

    def test_case5_reliable_forward_order_adds_positive_temporal_evidence(self):
        result = scores(self.pair_with_intervals([0, 1_000], [3_000, 4_000]))

        self.assertTrue(result["features"]["temporal_available"])
        self.assertGreater(result["a_to_b_score"], result["b_to_a_score"])
        self.assertGreater(result["a_to_b_score"], 0.2)

    def test_case6_overlapping_intervals_add_no_temporal_evidence(self):
        result = scores(self.pair_with_intervals([0, 10_000], [5_000, 15_000]))

        temporal = [c for c in result["a_to_b_contributions"] if c["kind"] == "temporal"]
        self.assertTrue(temporal)
        self.assertEqual(temporal[0]["log_contribution"], 0.0)
        self.assertEqual(temporal[0]["reason"], "interval_overlap_no_direction")

    def test_case7_reversed_order_adds_negative_temporal_evidence(self):
        result = scores(self.pair_with_intervals([5_000, 9_000], [0, 1_000]))

        self.assertGreater(result["b_to_a_score"], result["a_to_b_score"])
        temporal = [c for c in result["a_to_b_contributions"] if c["kind"] == "temporal"]
        self.assertLess(temporal[0]["log_contribution"], 0.0)

    def test_case8_unreliable_timestamps_switch_the_temporal_axis_off(self):
        result = scores(self.pair_with_intervals([0, 1_000], [3_000, 4_000], a_quality=0.0))

        self.assertEqual(result["a_to_b_score"], result["b_to_a_score"])
        temporal = [c for c in result["a_to_b_contributions"] if c["kind"] == "temporal"]
        self.assertTrue(temporal)
        self.assertEqual(temporal[0]["temporal_quality"], 0.0)
        self.assertEqual(temporal[0]["log_contribution"], 0.0)

    def test_absent_intervals_report_no_temporal_evidence_at_all(self):
        pair = self.pair_with_intervals(None, None)

        self.assertFalse(scores(pair)["features"]["temporal_available"])


class ModelConfigurationTests(unittest.TestCase):
    def test_prior_is_conditioned_on_edge_type(self):
        from Sys.RootCauseAnalyze.propagation.evidence_logit import load_evidence_model

        model = load_evidence_model()

        self.assertNotEqual(model.prior_for("physical"), model.prior_for("protocol_context"))
        self.assertGreater(model.prior_for("physical"), model.prior_for("protocol_context"))

    def test_unknown_edge_type_falls_back_to_the_default_prior(self):
        from Sys.RootCauseAnalyze.propagation.evidence_logit import load_evidence_model

        model = load_evidence_model()

        self.assertEqual(model.prior_for("something_new"), model.prior_for("_default"))

    def test_shipped_model_matches_its_declared_schema(self):
        from Sys.RootCauseAnalyze.propagation.evidence_logit import (
            EVIDENCE_SCHEMA_VERSION,
            load_evidence_model,
        )

        model = load_evidence_model()

        self.assertEqual(model.schema_version, EVIDENCE_SCHEMA_VERSION)
        self.assertTrue(model.patterns)

    def test_pattern_lrs_are_read_from_the_model_not_hard_coded(self):
        from dataclasses import replace

        from Sys.RootCauseAnalyze.propagation.evidence_logit import load_evidence_model

        model = load_evidence_model()
        a_episodes = [ep("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down")]
        # An event type no token table covers, so the weak layer taxonomy is the
        # only pattern that can relate these two observations.
        b_episodes = [ep("EB1", DEVICE_B, "", event_type="lldp_neighbor_recovery")]

        baseline_pair = evidence_for(a_episodes, b_episodes, model=model)
        self.assertEqual(
            [term["pattern"] for term in baseline_pair["terms"]], ["physical_to_derivative"]
        )
        baseline = scores(baseline_pair)
        tweaked = scores(
            evidence_for(
                a_episodes,
                b_episodes,
                model=replace(
                    model,
                    patterns={
                        **model.patterns,
                        "physical_to_derivative": {"forward_lr": 60.0, "reverse_lr": 0.01},
                    },
                ),
            )
        )

        self.assertGreater(tweaked["a_to_b_score"], baseline["a_to_b_score"])

    def test_score_is_the_sigmoid_of_the_accumulated_logit(self):
        a_episodes = [ep("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down")]
        b_episodes = [ep("EB1", DEVICE_B, "bgp_adjacency_down", event_type="bgp_session_down")]

        result = scores(evidence_for(a_episodes, b_episodes))

        self.assertAlmostEqual(
            result["a_to_b_score"], 1.0 / (1.0 + math.exp(-result["a_to_b_logit"])), places=9
        )

    def test_directions_are_not_normalised_against_each_other(self):
        a_episodes = [ep("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down")]
        b_episodes = [ep("EB1", DEVICE_B, "bgp_adjacency_down", event_type="bgp_session_down")]

        result = scores(evidence_for(a_episodes, b_episodes))

        self.assertLess(
            result["a_to_b_score"] + result["b_to_a_score"], 1.0
        )


class ExplainabilityTests(unittest.TestCase):
    def test_every_contribution_carries_its_own_reasoning(self):
        a_episodes = [
            ep("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down",
               interval=[0, 1_000], timestamp_quality=1.0)
        ]
        b_episodes = [
            ep("EB1", DEVICE_B, "bgp_adjacency_down", event_type="bgp_session_down",
               peer_raw="10.0.0.1", peer_resolution=resolved(DEVICE_A),
               possible_effects=["adjacency_loss"],
               cause_hint={"predicate": "interface_flap", "quote": "flap",
                           "source": "explicit_log_semantics"},
               interval=[3_000, 4_000], timestamp_quality=1.0)
        ]

        result = scores(evidence_for(a_episodes, b_episodes))
        contributions = result["a_to_b_contributions"]

        self.assertTrue(contributions)
        for item in contributions:
            for key in (
                "pattern",
                "kind",
                "attribution",
                "semantic_lr_a_to_b",
                "semantic_quality",
                "temporal_lr_a_to_b",
                "temporal_quality",
                "log_contribution",
                "evidence_ids",
                "reason",
            ):
                self.assertIn(key, item, key)
        self.assertIn("EA1", result["evidence_ids"])
        self.assertIn("EB1", result["evidence_ids"])

    def test_log_contribution_matches_the_declared_formula(self):
        a_episodes = [
            ep("EA1", DEVICE_A, "interface_flap", event_type="interface_state_down")
        ]
        b_episodes = [
            ep("EB1", DEVICE_B, "bgp_adjacency_down", event_type="bgp_session_down",
               possible_effects=["adjacency_loss"],
               cause_hint={"predicate": "interface_flap", "quote": "flap",
                           "source": "explicit_log_semantics"})
        ]

        contribution = scores(evidence_for(a_episodes, b_episodes))["a_to_b_contributions"][0]
        expected = contribution["attribution"] * (
            contribution["semantic_quality"] * math.log(contribution["semantic_lr_a_to_b"])
            + contribution["temporal_quality"] * math.log(contribution["temporal_lr_a_to_b"])
        )

        self.assertAlmostEqual(contribution["log_contribution"], expected, places=9)

    def test_feature_flags_report_what_was_actually_available(self):
        result = scores(evidence_for([], []))

        self.assertEqual(
            result["features"],
            {
                "semantic_available": False,
                "temporal_available": False,
                "attribution_available": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
