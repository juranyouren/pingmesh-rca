"""Dependency-free directory/CLI tests; no real dataset or scientific backend."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Baseline.common.io import dump_json, read_json
from Baseline.common.synthetic import make_cases
from Baseline.RQ1.prepare import convert_label, labels_from_path, prepare_manifest
from Baseline.RQ1.runner import main


class PreparationTests(unittest.TestCase):
    def test_legacy_possible_remains_unknown(self):
        label = convert_label({"root_scope": "device", "root_devices": ["A"], "edges": [
            {"from": "A", "to": "B", "membership": "definite"},
            {"from": "B", "to": "C", "membership": "possible"},
            {"from": "A", "to": "C", "membership": "explicit_no_direct"}]}, "c")
        self.assertEqual(label["positive_edges"], [["A", "B"]])
        self.assertNotIn(["B", "C"], label["known_edge_mask"])
        self.assertIn(["C", "A"], label["known_edge_mask"])
        self.assertFalse(label["graph_complete"])

    def test_complete_with_possible_rejected(self):
        with self.assertRaisesRegex(ValueError, "unresolved"):
            convert_label({"graph_complete": True, "edges": [
                {"from": "A", "to": "B", "state": "possible"}]}, "c")

    def test_multi_root_never_picks_first(self):
        label = convert_label({"root_scope": "device", "root_devices": ["A", "B"], "edges": []}, "c")
        self.assertEqual(label["root_status"], "unknown")
        self.assertNotIn("root_device", label)

    def test_no_gt_local_check_does_not_read_labels(self):
        cases, _, _ = make_cases(2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dump_json(root / "inputs.json", {"incidents": cases})
            with patch("Baseline.RQ1.runner.labels_from_path", side_effect=AssertionError("GT must not be read")):
                with redirect_stdout(StringIO()) as output:
                    main(["--check-inputs", "--inputs", str(root / "inputs.json"),
                          "--labels", str(root / "absent"), "--output", str(root / "no-write")])
            self.assertIn('"n_cases": 2', output.getvalue())
            self.assertFalse((root / "no-write").exists())

    def test_missing_gt_has_actionable_error(self):
        cases, _, _ = make_cases(2)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FileNotFoundError, "check-inputs"):
                labels_from_path(Path(tmp) / "absent", cases)

    def test_automatic_groups_not_verified_and_inference_manifest_reloads(self):
        cases, _, _ = make_cases(2)
        manifest = prepare_manifest(cases)
        self.assertFalse(manifest["groups_verified"])
        self.assertEqual(manifest["folds"][0]["train"], [])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "folds.json"
            dump_json(path, manifest)
            self.assertEqual(prepare_manifest(cases, manifest_path=path), manifest)

    def test_reviewed_groups_generate_folds(self):
        cases, _, groups = make_cases(4)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "groups.json"
            dump_json(path, groups)
            manifest = prepare_manifest(cases, groups_path=path)
            self.assertTrue(manifest["groups_verified"])
            self.assertEqual(len(manifest["folds"]), 4)

    def test_server_directory_end_to_end_and_rescore(self):
        cases, _, _ = make_cases(2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dump_json(root / "inputs.json", {"incidents": cases})
            for case in cases:
                dump_json(root / "gt" / case["case_id"] / "propagation_label.json", {
                    "root_scope": "device", "root_devices": ["A"], "graph_complete": True,
                    "edges": [{"from": "A", "to": "B", "membership": "definite"},
                              {"from": "B", "to": "C", "membership": "definite"}]})
            env = {"PINGMESH_DATA": str(root / "inputs.json"),
                   "PINGMESH_PROPAGATION_LABELS_ROOT": str(root / "gt"),
                   "PINGMESH_RESULTS": str(root / "results"), "PINGMESH_RQ1_CONDITION": "oracle",
                   "PINGMESH_RQ1_MANIFEST": "", "PINGMESH_RQ1_GROUPS": "", "PINGMESH_RQ1_ROOTS": ""}
            with patch.dict("os.environ", env), redirect_stdout(StringIO()):
                main(["--methods", "timeorder"])
                run = next((root / "results").iterdir())
                summary = read_json(run / "summary.json")
                self.assertEqual(summary["tables"]["rooted"]["complete_all"]["timeorder"]["metrics"]["AH-F1"]["mean"], 1)
                self.assertIsNone(summary["tables"]["rooted"]["complete_all"]["timeorder"]["metrics"]["AH-F1"]["ci95"])
                main(["evaluate", "--methods", "timeorder", "--manifest", str(run / "folds.json"),
                      "--predictions", str(run / "predictions.json"), "--output", str(root / "rescore")])
                self.assertEqual(read_json(root / "rescore" / "summary.json"), summary)


if __name__ == "__main__":
    unittest.main()
