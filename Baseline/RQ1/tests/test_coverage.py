"""Coverage policy tests without numerical backends or real incident data."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Baseline.common.io import dump_json, read_json
from Baseline.common.splits import build_manifest
from Baseline.common.synthetic import make_cases
from Baseline.common.timeseries import build_timeseries
from Baseline.RQ1.models import InputIneligible, PCMCI, TimeOrder
from Baseline.RQ1.runner import main, predict


class CoverageTests(unittest.TestCase):
    def case(self):
        case = make_cases(2)[0][0]
        case["observation_coverage"] = None
        return case

    def test_strict_keeps_unknown_bins_unknown(self):
        series = build_timeseries(self.case())
        self.assertEqual(series["reason"], "collection_coverage_unknown")
        self.assertTrue(all(value is None for row in series["values"] for value in row))

    def test_record_counts_are_not_claimed_collection_coverage(self):
        case = self.case()
        series = build_timeseries(case, require_coverage=False)
        self.assertEqual(series["status"], "ok")
        self.assertEqual(sum(sum(row) for row in series["values"]), len(case["events"]))
        self.assertEqual(series["diagnostics"]["coverage_assumption"], "record_count_only_zero_is_not_health")
        self.assertIsNone(case["observation_coverage"])

    def test_known_collection_gaps_still_masked(self):
        case = self.case()
        case["observation_coverage"] = {"complete": False, "intervals": [
            {"start": case["window"]["start"], "end": case["window"]["end"], "device_ids": ["A"]}]}
        series = build_timeseries(case, require_coverage=False)
        self.assertTrue(all(row[0] is not None and row[1] is None for row in series["values"]))

    def test_policy_name_and_boolean_validation(self):
        self.assertTrue(PCMCI().config["require_coverage"])
        self.assertIn("record-count", PCMCI({"require_coverage": False}).method)
        with self.assertRaises(ValueError):
            PCMCI({"require_coverage": "false"})

    def test_failed_prediction_keeps_policy(self):
        class Fails:
            config = {"require_coverage": False}
            method = "fixture"
            def predict_raw_graph(self, case):
                raise InputIneligible("too few events")
        row = predict(Fails(), "pcmci", self.case(), 0, "oracle", "A")
        self.assertEqual(row["status"], "input_ineligible")
        self.assertFalse(row["config"]["require_coverage"])

    def test_cli_override_saved_in_prediction_and_report(self):
        class FakePCMCI:
            method = "fixture-not-a-real-PCMCI-result"
            def __init__(self, config):
                self.config = config
            def predict_raw_graph(self, case):
                return TimeOrder().predict_raw_graph(case)

        cases, labels, groups = make_cases(2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dump_json(root / "inputs.json", {"incidents": cases})
            dump_json(root / "labels.json", {"labels": labels})
            dump_json(root / "folds.json", build_manifest(cases, groups, folds=2))
            args = ["run", "--inputs", str(root / "inputs.json"), "--labels", str(root / "labels.json"),
                    "--manifest", str(root / "folds.json"), "--output", str(root / "run"),
                    "--condition", "oracle", "--methods", "pcmci", "--pcmci-coverage", "record-count"]
            with patch("Baseline.RQ1.runner.make_model", side_effect=lambda method, config, device: FakePCMCI(config)), redirect_stdout(StringIO()):
                main(args)
            self.assertFalse(read_json(root / "run/run.json")["config"]["pcmci"]["require_coverage"])
            self.assertEqual(read_json(root / "run/summary.json")["pcmci_coverage_policies"], ["record-count"])
            self.assertIn("zero means no exported event record", (root / "run/table.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
