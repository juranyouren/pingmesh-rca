"""Tests for the shared timestamp-quality assessment.

A raw timestamp existing is not evidence that it can order events. This module
decides whether an incident's timestamps are *usable as event times*, and both
the LLM evidence path and the rule path consume that single decision.

The detector is deliberately one-sided: it may downgrade a timestamp to
unusable, but the absence of a degradation signature never promotes an
unverified timestamp to verified. That asymmetry is what makes a heuristic
acceptable here - a false positive costs nothing (the axis is already off),
while a false negative just keeps today's conservative behaviour.
"""
import json
import unittest


def obs(time_ms, device_id="", key=""):
    from Sys.utils.time_quality import TimeObservation

    return TimeObservation(time_ms=time_ms, device_id=device_id, key=key)


# Real shapes, taken from the two labelled cases in data/node/nodes_max_labeled.
# 8294294: three devices each stamped twice at ~+15.2s and twice at ~+23.2s, with
# the three devices' stamps landing within 43 ms of each other, twice.
BATCH_SNAPSHOT_OBSERVATIONS = [
    obs(1786068495277, "28.219.131.16"), obs(1786068495278, "28.219.131.16"),
    obs(1786068503251, "28.219.131.16"), obs(1786068503251, "28.219.131.16"),
    obs(1786068495235, "28.219.67.16"), obs(1786068495235, "28.219.67.16"),
    obs(1786068503171, "28.219.67.16"), obs(1786068503171, "28.219.67.16"),
    obs(1786068495242, "28.219.67.17"), obs(1786068495243, "28.219.67.17"),
    obs(1786068503151, "28.219.67.17"), obs(1786068503151, "28.219.67.17"),
]

# 23041865: one alarm on each of three devices, ~545 s apart, no repetition.
SPREAD_OBSERVATIONS = [
    obs(1786470060103, "mykualalumpur1d-nc01"),
    obs(1786470560000, "mykualalumpur1c-mgs01"),
    obs(1786470605015, "mykualalumpur1c-mgs01-usg"),
]


class MissingTimeTests(unittest.TestCase):
    def test_no_observations_is_missing_and_unusable(self):
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality([])

        self.assertEqual(result.quality, "missing")
        self.assertEqual(result.score, 0.0)
        self.assertFalse(result.usable)

    def test_observations_without_timestamps_are_missing(self):
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality([obs(None, "a"), obs(None, "b")])

        self.assertEqual(result.quality, "missing")
        self.assertFalse(result.usable)


class DowngradeOnlyTests(unittest.TestCase):
    def test_spread_out_timestamps_are_unverified_not_verified(self):
        """Not detecting a batch signature must never promote a timestamp."""
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality(SPREAD_OBSERVATIONS)

        self.assertEqual(result.quality, "unverified_source_timestamp")
        self.assertEqual(result.score, 0.0)
        self.assertFalse(result.usable)

    def test_a_single_device_with_one_timestamp_is_still_unverified(self):
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality([obs(1786068495277, "a")])

        self.assertEqual(result.quality, "unverified_source_timestamp")
        self.assertFalse(result.usable)


class BatchSnapshotDetectorTests(unittest.TestCase):
    def test_repeated_timestamp_on_one_device_is_a_batch_signature(self):
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality(
            [
                obs(1000, "a"), obs(1000, "a"),
                obs(9000, "a"), obs(9000, "a"),
            ]
        )

        self.assertEqual(result.quality, "batch_snapshot")
        self.assertEqual(result.score, 0.0)

    def test_a_device_writing_one_instant_for_all_its_records_is_a_batch(self):
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality([obs(1000, "a"), obs(1000, "a"), obs(1000, "a")])

        self.assertEqual(result.quality, "batch_snapshot")

    def test_a_single_record_on_one_device_is_not_a_batch(self):
        """One observation cannot repeat itself, so it carries no signature."""
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality([obs(1000, "a")])

        self.assertNotEqual(result.quality, "batch_snapshot")

    def test_near_simultaneity_across_devices_is_a_batch_signature(self):
        """Three devices do not fail within 43 ms of each other, twice."""
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality(
            [
                obs(0, "a"), obs(21, "b"), obs(42, "c"),
                obs(500_000, "a"), obs(500_100, "b"), obs(500_200, "c"),
            ]
        )

        self.assertEqual(result.quality, "batch_snapshot")

    def test_coincidence_is_judged_relative_to_the_incident_extent(self):
        """Three devices inside 43 ms of an 8 s incident is still a collector."""
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality(
            [
                obs(1_786_068_495_277, "a"), obs(1_786_068_503_251, "a"),
                obs(1_786_068_495_235, "b"), obs(1_786_068_503_171, "b"),
                obs(1_786_068_495_242, "c"), obs(1_786_068_503_151, "c"),
            ]
        )

        self.assertEqual(result.quality, "batch_snapshot")

    def test_an_incident_contained_in_one_instant_is_not_a_batch(self):
        """Too short to tell: no incident extent for the coincidence to stand out from."""
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality([obs(0, "a"), obs(600, "b"), obs(900, "c")])

        self.assertEqual(result.quality, "unverified_source_timestamp")

    def test_two_devices_close_together_is_not_enough_on_its_own(self):
        """Adjacent devices can genuinely fail together; three is a collector."""
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality([obs(0, "a"), obs(30, "b")])

        self.assertEqual(result.quality, "unverified_source_timestamp")

    def test_the_real_batch_case_is_detected(self):
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality(BATCH_SNAPSHOT_OBSERVATIONS)

        self.assertEqual(result.quality, "batch_snapshot")
        self.assertEqual(result.score, 0.0)
        self.assertIn("detector", result.evidence)

    def test_the_real_spread_case_is_not_a_batch(self):
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality(SPREAD_OBSERVATIONS)

        self.assertNotEqual(result.quality, "batch_snapshot")


class VerifiedSourceTests(unittest.TestCase):
    def test_a_declared_source_with_clean_timestamps_is_verified(self):
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality(
            SPREAD_OBSERVATIONS, source_declares_event_times=True
        )

        self.assertEqual(result.quality, "verified_event_timestamp")
        self.assertGreater(result.score, 0.0)
        self.assertTrue(result.usable)

    def test_a_batch_signature_overrides_a_declared_source(self):
        """A declaration may not outrank evidence that the stamps are collected."""
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality(
            BATCH_SNAPSHOT_OBSERVATIONS, source_declares_event_times=True
        )

        self.assertEqual(result.quality, "batch_snapshot")
        self.assertEqual(result.score, 0.0)

    def test_declaring_a_source_does_not_help_with_no_timestamps(self):
        from Sys.utils.time_quality import assess_time_quality

        result = assess_time_quality([obs(None, "a")], source_declares_event_times=True)

        self.assertEqual(result.quality, "missing")


class ContractTests(unittest.TestCase):
    def test_assessment_is_json_serializable(self):
        from Sys.utils.time_quality import assess_time_quality

        payload = assess_time_quality(BATCH_SNAPSHOT_OBSERVATIONS).to_dict()

        json.dumps(payload)
        # ``time_*`` keys so the dict drops straight into an episode's
        # ``quality`` block and the encoder's ``time`` block.
        self.assertEqual(payload["time_quality"], "batch_snapshot")
        self.assertEqual(payload["time_score"], 0.0)
        self.assertFalse(payload["usable"])

    def test_quality_names_are_exposed_as_constants(self):
        from Sys.utils import time_quality

        self.assertEqual(time_quality.TIME_QUALITY_VERIFIED, "verified_event_timestamp")
        self.assertEqual(time_quality.TIME_QUALITY_BATCH, "batch_snapshot")
        self.assertEqual(
            time_quality.TIME_QUALITY_UNVERIFIED, "unverified_source_timestamp"
        )
        self.assertEqual(time_quality.TIME_QUALITY_MISSING, "missing")


def rule_node(name, mgmt_ip, times):
    id_field = "IP=" + mgmt_ip
    return {
        "name": name,
        "mgmt_ip": mgmt_ip,
        "role": "PE",
        "alarms": [
            {"alarm_name": "Interface down", "alarm_time": t,
             "description": f"{id_field}; interface GE1/0/0 changed state to down"}
            for t in times
        ],
        "logs": [],
    }


def batch_snapshot_nodes():
    return [
        rule_node("PE-1", "28.219.131.16",
                  [1786068495277, 1786068503251]),
        rule_node("PE-2", "28.219.67.16",
                  [1786068495235, 1786068503171]),
        rule_node("PE-3", "28.219.67.17",
                  [1786068495242, 1786068503151]),
    ]


def spread_nodes():
    return [
        rule_node("PE-1", "11.64.255.250", [1786470293933]),
        rule_node("PE-2", "11.64.255.253", [1786470239985]),
    ]


class RulePathIntegrationTests(unittest.TestCase):
    def test_rule_path_episodes_carry_the_assessed_quality(self):
        from Sys.RootCauseAnalyze.propagation.episodes import build_evidence_episodes

        episodes = build_evidence_episodes(
            batch_snapshot_nodes(), {"alarm_time": 1786068480000}
        )

        self.assertTrue(episodes)
        for episode in episodes:
            self.assertEqual(episode["quality"]["timestamp"], 0.0)
            self.assertEqual(episode["quality"]["time_quality"], "batch_snapshot")

    def test_batch_snapshot_episodes_expose_no_onset_interval(self):
        """The batch gap must not become a propagation lag."""
        from Sys.RootCauseAnalyze.propagation.episodes import build_evidence_episodes

        episodes = build_evidence_episodes(
            batch_snapshot_nodes(), {"alarm_time": 1786068480000}
        )

        for episode in episodes:
            self.assertIsNone(episode["onset_interval_ms"])
            # The raw stamp is preserved; only the derived interval is gated.
            self.assertIsNotNone(episode["onset_time_ms"])

    def test_spread_timestamps_also_expose_no_onset_interval(self):
        """Unverified is gated exactly like batch: 23041865's 44 s gap is gone."""
        from Sys.RootCauseAnalyze.propagation.episodes import build_evidence_episodes

        episodes = build_evidence_episodes(
            spread_nodes(), {"alarm_time": 1786470420000}
        )

        self.assertTrue(episodes)
        for episode in episodes:
            self.assertEqual(episode["quality"]["timestamp"], 0.0)
            self.assertEqual(
                episode["quality"]["time_quality"], "unverified_source_timestamp"
            )
            self.assertIsNone(episode["onset_interval_ms"])

    def test_raw_timestamps_are_preserved_even_when_gated(self):
        from Sys.RootCauseAnalyze.propagation.episodes import build_evidence_episodes

        episodes = build_evidence_episodes(
            batch_snapshot_nodes(), {"alarm_time": 1786068480000}
        )

        self.assertEqual(episodes[0]["quality"]["time_reason"], "batch_snapshot_timestamps")


class FakeEngine:
    """Minimal stand-in for the NPU-side LLM."""

    def generate_json(self, prompt):
        data = json.loads(prompt.split("DATA_JSON=", 1)[1])
        return {
            "mappings": [
                {
                    "raw_event_id": record["raw_event_id"],
                    "predicate": "interface_state_change",
                    "entity": {"entity_type": "interface", "local_name": "AggregatePort 5"},
                    "value": {"state": "down"},
                    "mapping_confidence": 0.9,
                    "semantic_summary": "Interface went down",
                }
                for record in data["records"]
            ]
        }


def llm_node(ip, times):
    records = [
        {
            "alarm_name": "LINEPROTO_5_UPDOWN",
            "source": "Ruijie",
            "description": "Interface AggregatePort 5, changed state to down.",
            "alarm_time": time_ms,
        }
        for time_ms in times
    ]
    return {"mgmt_ip": ip, "alarms": records, "logs": []}


def encode(nodes, **kwargs):
    from Sys.Preprocess.evidence.encoder import EvidenceEncoder

    return EvidenceEncoder(FakeEngine(), **kwargs).encode_incident("case", nodes)


class LlmPathIntegrationTests(unittest.TestCase):
    def test_the_llm_path_consumes_the_same_assessment_as_the_rule_path(self):
        from Sys.Preprocess.evidence.adapter import to_episodes

        # Three devices, two records each, all sharing one collection instant.
        incident = encode(
            [
                llm_node("10.0.0.1", [1786068495277, 1786068495277]),
                llm_node("10.0.0.2", [1786068495235, 1786068495235]),
                llm_node("10.0.0.3", [1786068495242, 1786068495242]),
            ]
        )

        evidence = incident["devices"][0]["evidence"][0]
        self.assertEqual(evidence["time"]["time_quality"], "batch_snapshot")
        self.assertEqual(evidence["time"]["time_score"], 0.0)

        episode = to_episodes(incident)[0]
        self.assertEqual(episode["quality"]["timestamp"], 0.0)
        self.assertEqual(episode["quality"]["time_quality"], "batch_snapshot")
        self.assertIsNone(episode["onset_interval_ms"])

    def test_unverified_llm_timestamps_are_gated_too(self):
        from Sys.Preprocess.evidence.adapter import to_episodes

        incident = encode(
            [
                llm_node("10.0.0.1", [1786068495277]),
                llm_node("10.0.0.2", [1787000000000]),
            ]
        )

        evidence = incident["devices"][0]["evidence"][0]
        self.assertEqual(evidence["time"]["time_quality"], "unverified_source_timestamp")
        self.assertEqual(evidence["time"]["time_score"], 0.0)

        episode = to_episodes(incident)[0]
        self.assertEqual(episode["quality"]["timestamp"], 0.0)
        self.assertIsNone(episode["onset_interval_ms"])

    def test_a_declared_verified_source_opens_the_interval(self):
        from Sys.Preprocess.evidence.adapter import to_episodes

        incident = encode(
            [
                llm_node("10.0.0.1", [1786068495277]),
                llm_node("10.0.0.2", [1786068545277]),
            ],
            source_declares_event_times=True,
        )

        evidence = incident["devices"][0]["evidence"][0]
        self.assertEqual(evidence["time"]["time_quality"], "verified_event_timestamp")
        self.assertEqual(evidence["time"]["time_score"], 1.0)

        episode = to_episodes(incident)[0]
        self.assertEqual(episode["quality"]["timestamp"], 1.0)
        self.assertIsNotNone(episode["onset_interval_ms"])

    def test_a_declaration_loses_to_a_batch_signature_on_the_llm_path(self):
        from Sys.Preprocess.evidence.adapter import to_episodes

        incident = encode(
            [
                llm_node("10.0.0.1", [1786068495277, 1786068495277]),
                llm_node("10.0.0.2", [1786068495235, 1786068495235]),
                llm_node("10.0.0.3", [1786068495242, 1786068495242]),
            ],
            source_declares_event_times=True,
        )

        evidence = incident["devices"][0]["evidence"][0]
        self.assertEqual(evidence["time"]["time_quality"], "batch_snapshot")
        self.assertIsNone(to_episodes(incident)[0]["onset_interval_ms"])

    def test_the_raw_timestamp_stays_on_the_evidence(self):
        incident = encode([llm_node("10.0.0.1", [1786068495277])])

        self.assertEqual(
            incident["devices"][0]["evidence"][0]["time"]["raw_time"], 1786068495277
        )


class TemporalAxisIntegrationTests(unittest.TestCase):
    def test_gated_timestamps_produce_no_temporal_contribution(self):
        from Sys.RootCauseAnalyze.propagation.evidence_logit import build_pair_evidence
        from Sys.RootCauseAnalyze.propagation.evidence_logit import load_evidence_model

        a = {"evidence_id": "EA1", "device_id": "a", "predicate": "", "event_type": "physical_link_down",
             "peer_raw": "", "lifecycle": "raised", "onset_interval_ms": [0, 10_000],
             "quality": {"timestamp": 0.0, "time_quality": "batch_snapshot"}}
        b = {"evidence_id": "EB1", "device_id": "b", "predicate": "", "event_type": "bgp_session_down",
             "peer_raw": "", "lifecycle": "raised", "onset_interval_ms": [30_000, 40_000],
             "quality": {"timestamp": 0.0, "time_quality": "batch_snapshot"}}

        pair = build_pair_evidence("a", "b", [a], [b], model=load_evidence_model())
        temporal = [t for t in pair["terms"] if t["kind"] == "temporal"]

        self.assertTrue(temporal)
        self.assertEqual(temporal[0]["temporal_quality"], 0.0)


if __name__ == "__main__":
    unittest.main()
