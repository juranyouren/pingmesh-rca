"""Regression tests for repeated raw alarm IDs (no server data required)."""
from pathlib import Path
import tempfile
import unittest

from Baseline.common.io import dump_json, from_processed, from_raw, normalize_incident
from Baseline.common.schema import input_fingerprint


def raw_case(events):
    return {"full_link": {
        "task_info": {"task_id": "fixture", "alarm_time": 1700000100},
        "task_topo": {"value": [[{"nodes": [{"mgmt_ip": "A"}, {"mgmt_ip": "B"}],
                                  "links": [{"src_ip": "A", "dst_ip": "B"}]}]]},
        "alarm_list": events,
    }}


def alarm(**changes):
    return {"alarm_id": "reused", "alarm_ip_ad": "A", "alarm_name": "link down",
            "alarm_time": 1700000100, "message": "interface down", **changes}


class EventIdentityTests(unittest.TestCase):
    def test_same_alarm_id_different_times_survive(self):
        case = from_raw(raw_case([alarm(), alarm(alarm_time=1700000101)]))
        self.assertEqual(len(case["events"]), 2)
        self.assertEqual(len({e["event_id"] for e in case["events"]}), 2)
        self.assertEqual(case["input_diagnostics"]["reused_alarm_id_groups"], 1)

    def test_same_alarm_id_time_different_content_survives(self):
        case = from_raw(raw_case([alarm(), alarm(message="interface recovered")]))
        self.assertEqual(len(case["events"]), 2)

    def test_exact_observation_duplicates_are_merged(self):
        case = from_raw(raw_case([alarm(), alarm(), alarm(alarm_time=1700000101)]))
        self.assertEqual(len(case["events"]), 2)
        self.assertEqual(case["input_diagnostics"]["excluded_events"]["exact_duplicate"], 1)

    def test_order_independent_and_roundtrip_stable(self):
        rows = [alarm(), alarm(alarm_time=1700000101), alarm(message="other")]
        a, b = from_raw(raw_case(rows)), from_raw(raw_case(list(reversed(rows))))
        self.assertEqual(a["events"], b["events"])
        self.assertEqual(input_fingerprint(a), input_fingerprint(normalize_incident(a)))

    def test_canonical_conflict_still_fails(self):
        with self.assertRaisesRegex(ValueError, "explicit event_id"):
            from_raw(raw_case([alarm(event_id="event-1"), alarm(event_id="event-1", message="other")]))

    def test_explicit_id_preserved_and_deduplicated(self):
        case = from_raw(raw_case([alarm(event_id="event-1"), alarm(event_id="event-1")]))
        self.assertEqual([e["event_id"] for e in case["events"]], ["event-1"])

    def test_label_fields_do_not_change_identity(self):
        clean = from_raw(raw_case([alarm()]))
        polluted = from_raw(raw_case([alarm(root_device="A", propagation_label={"edges": [["A", "B"]]})]))
        self.assertEqual(clean["events"], polluted["events"])

    def test_different_devices_are_distinct(self):
        case = from_raw(raw_case([alarm(), alarm(alarm_ip_ad="B")]))
        self.assertEqual(len(case["events"]), 2)
        self.assertEqual(case["input_diagnostics"]["reused_alarm_id_groups"], 0)

    def test_processed_directory_uses_same_identity_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            dump_json(path / "info.json", {"alarm_time": 1700000100})
            dump_json(path / "nodes.json", [{"mgmt_ip": "A", "alarms": [alarm(), alarm(alarm_time=1700000101)]}])
            dump_json(path / "topology_context.json", {"diagnostics": {"source": "raw_task_topo"},
                      "nodes": [{"device_id": "A"}], "edges": []})
            case = from_processed(path)
            self.assertEqual(len(case["events"]), 2)
            self.assertEqual(case["input_diagnostics"]["reused_alarm_id_groups"], 1)


if __name__ == "__main__":
    unittest.main()
