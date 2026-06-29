import csv
import json
import os
import tempfile
import unittest


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class CredenceArtifactPipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.case_a = os.path.join(self.root, "cases", "case_a")
        self.case_b = os.path.join(self.root, "cases", "case_b")
        self.case_c = os.path.join(self.root, "cases", "case_c")
        os.makedirs(self.case_a, exist_ok=True)
        os.makedirs(self.case_b, exist_ok=True)
        os.makedirs(self.case_c, exist_ok=True)

        self.res_path = os.path.join(self.root, "res.json")
        _write_json(
            self.res_path,
            [
                {
                    "dir": self.case_a,
                    "skill_ips": ["10.0.0.1", "10.0.0.2"],
                    "gt_ips": ["10.0.0.1"],
                    "response": '```json\n{"ip": ["10.0.0.2"]}\n```',
                    "confidence_gate": {
                        "decision": "bypass_llm",
                        "reason": "combined_high_margin",
                        "recommended_ips": ["10.0.0.1", "10.0.0.2"],
                        "methods": {
                            "combined": {"top_score": 95.0, "runner_up_score": 70.0, "margin": 25.0},
                            "topo": {"margin": 12.0},
                            "temporal": {"margin": 9.0},
                        },
                        "agreement": {"top1_votes_for_combined": 2},
                    },
                },
                {
                    "dir": self.case_b,
                    "skill_ips": ["10.0.0.3", "10.0.0.4"],
                    "gt_ips": ["10.0.0.4"],
                    "response": '```json\n{"ip": ["10.0.0.4"]}\n```',
                    "confidence_gate": {
                        "decision": "invoke_llm",
                        "reason": "low_confidence_or_disagreement",
                        "recommended_ips": ["10.0.0.3", "10.0.0.4"],
                        "methods": {
                            "combined": {"top_score": 55.0, "runner_up_score": 51.0, "margin": 4.0},
                            "topo": {"margin": 1.0},
                            "temporal": {"margin": 2.0},
                        },
                        "agreement": {"top1_votes_for_combined": 1},
                    },
                },
                {
                    "dir": self.case_c,
                    "skill_ips": ["10.0.0.5", "10.0.0.6"],
                    "gt_ips": ["10.0.0.7"],
                    "response": '```json\n{"ip": ["10.0.0.7"]}\n```',
                    "confidence_gate": {
                        "decision": "invoke_llm",
                        "reason": "low_confidence_or_disagreement",
                        "recommended_ips": ["10.0.0.5", "10.0.0.6"],
                        "methods": {
                            "combined": {"top_score": 53.0, "runner_up_score": 52.0, "margin": 1.0},
                            "topo": {"margin": 0.5},
                            "temporal": {"margin": 0.0},
                        },
                        "agreement": {"top1_votes_for_combined": 1},
                    },
                },
            ],
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_cases_keeps_label_only_fields_out_of_features(self):
        from Sys.Score.export_confidence_cases import export_confidence_cases

        out = os.path.join(self.root, "credence", "confidence_cases.jsonl")
        summary = os.path.join(self.root, "credence", "confidence_extraction_summary.json")
        manifest = os.path.join(self.root, "credence", "confidence_manifest.json")

        export_confidence_cases(
            res_path=self.res_path,
            out_path=out,
            summary_path=summary,
            manifest_path=manifest,
            data_version="unit",
        )

        rows = _read_jsonl(out)
        self.assertEqual([row["case_id"] for row in rows], ["case_a", "case_b", "case_c"])
        self.assertTrue(rows[0]["deterministic_hit_top1"])
        self.assertFalse(rows[1]["deterministic_hit_top1"])
        self.assertTrue(rows[1]["llm_hit_top1"])

        with open(manifest, encoding="utf-8") as f:
            manifest_data = json.load(f)
        self.assertIn("raw_confidence_score", manifest_data["feature_columns"])
        self.assertIn("deterministic_hit_top1", manifest_data["label_only_columns"])
        self.assertFalse(set(manifest_data["feature_columns"]) & set(manifest_data["label_only_columns"]))

    def test_export_uses_separate_always_llm_responses_for_llm_value(self):
        from Sys.Score.export_confidence_cases import export_confidence_cases

        gated_res = os.path.join(self.root, "gated_res.json")
        always_llm_res = os.path.join(self.root, "always_llm_res.json")
        _write_json(
            gated_res,
            [
                {
                    "dir": self.case_a,
                    "skill_ips": ["10.0.0.1", "10.0.0.2"],
                    "gt_ips": ["10.0.0.1"],
                    "response": '```json\n{"ip": ["10.0.0.1", "10.0.0.2"]}\n```',
                    "confidence_gate": {
                        "decision": "bypass_llm",
                        "reason": "combined_high_margin",
                        "methods": {"combined": {"top_score": 95.0, "runner_up_score": 70.0, "margin": 25.0}},
                        "agreement": {"top1_votes_for_combined": 2},
                    },
                }
            ],
        )
        _write_json(
            always_llm_res,
            [
                {
                    "dir": self.case_a,
                    "response": '```json\n{"ip": ["10.0.0.2"]}\n```',
                }
            ],
        )

        out = os.path.join(self.root, "credence", "merged_cases.jsonl")
        export_confidence_cases(
            res_path=gated_res,
            llm_res_path=always_llm_res,
            out_path=out,
            summary_path=os.path.join(self.root, "credence", "merged_summary.json"),
            manifest_path=os.path.join(self.root, "credence", "merged_manifest.json"),
            data_version="unit",
        )

        row = _read_jsonl(out)[0]
        self.assertTrue(row["deterministic_hit_top1"])
        self.assertFalse(row["llm_hit_top1"])
        self.assertEqual(row["llm_response_source"], "always_llm_res")

    def test_calibration_and_value_artifacts_have_denominators(self):
        from Sys.Score.calibrate_confidence import calibrate_confidence
        from Sys.Score.evaluate_diagnosability import evaluate_diagnosability
        from Sys.Score.evaluate_llm_value import evaluate_llm_value
        from Sys.Score.export_confidence_cases import export_confidence_cases

        out_dir = os.path.join(self.root, "credence")
        cases = os.path.join(out_dir, "confidence_cases.jsonl")
        export_confidence_cases(
            res_path=self.res_path,
            out_path=cases,
            summary_path=os.path.join(out_dir, "confidence_extraction_summary.json"),
            manifest_path=os.path.join(out_dir, "confidence_manifest.json"),
            data_version="unit",
        )

        calibrate_confidence(cases_path=cases, out_dir=out_dir, risk_budget=0.25, delta=0.1, bootstrap_repeats=50, seed=7)
        evaluate_llm_value(cases_path=cases, out_path=os.path.join(out_dir, "llm_value.csv"))
        evaluate_diagnosability(cases_path=cases, out_path=os.path.join(out_dir, "diagnosability_frontier.csv"))

        with open(os.path.join(out_dir, "risk_coverage.csv"), newline="", encoding="utf-8") as f:
            risk_rows = list(csv.DictReader(f))
        self.assertTrue(risk_rows)
        self.assertIn("n_selected", risk_rows[0])
        self.assertIn("wrong_bypass_upper", risk_rows[0])

        with open(os.path.join(out_dir, "llm_value.csv"), newline="", encoding="utf-8") as f:
            value_rows = list(csv.DictReader(f))
        all_row = next(row for row in value_rows if row["region_or_bin"] == "all")
        self.assertEqual(int(all_row["n"]), 3)
        self.assertEqual(int(all_row["rescue"]), 2)
        self.assertEqual(int(all_row["harm"]), 1)

        with open(os.path.join(out_dir, "diagnosability_frontier.csv"), newline="", encoding="utf-8") as f:
            diag_rows = list(csv.DictReader(f))
        self.assertTrue(diag_rows)
        self.assertIn("n", diag_rows[0])


if __name__ == "__main__":
    unittest.main()
