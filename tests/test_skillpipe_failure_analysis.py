import json
import os
import tempfile
import unittest

from Sys.Score.analyze_skillpipe_failures import (
    analyze_skillpipe_records,
    write_analysis_outputs,
)


def _response(ips, details):
    payload = {
        "reasoning": "skillpipe",
        "ip": ips,
        "skill_details": details,
    }
    return "```json\n" + json.dumps(payload) + "\n```"


class SkillpipeFailureAnalysisTest(unittest.TestCase):
    def test_extracts_failure_features_and_gate_design_candidates(self):
        records = [
            {
                "dir": "/cases/case-hit",
                "skill_ips": ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
                "gt_ips": ["10.0.0.1"],
                "response": _response(
                    ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
                    {
                        "1": {"top3": [["10.0.0.1", 1.0], ["10.0.0.2", 0.4]]},
                        "2": {"top3": [["10.0.0.1", 0.9], ["10.0.0.3", 0.3]]},
                    },
                ),
            },
            {
                "dir": "/cases/case-rank2",
                "skill_ips": ["10.0.0.2", "10.0.0.1", "10.0.0.3"],
                "gt_ips": ["10.0.0.1"],
                "response": _response(
                    ["10.0.0.2", "10.0.0.1", "10.0.0.3"],
                    {
                        "1": {"top3": [["10.0.0.2", 0.7], ["10.0.0.1", 0.68]]},
                        "2": {"top3": [["10.0.0.3", 0.8], ["10.0.0.1", 0.79]]},
                    },
                ),
            },
            {
                "dir": "/cases/case-miss",
                "skill_ips": ["10.0.0.4", "10.0.0.5"],
                "gt_ips": ["10.0.0.9"],
                "response": _response(
                    ["10.0.0.4", "10.0.0.5"],
                    {"1": {"top3": [["10.0.0.4", 0.3]]}},
                ),
            },
        ]

        rows, summary = analyze_skillpipe_records(records, margin_threshold=0.05)

        self.assertEqual(summary["total_cases"], 3)
        self.assertEqual(summary["top1_failures"], 2)
        self.assertEqual(summary["failure_type_counts"]["top1_miss_gt_in_top3"], 1)
        self.assertEqual(summary["failure_type_counts"]["miss_top5"], 1)
        self.assertGreaterEqual(summary["failure_feature_counts"]["method_disagreement"], 1)

        rank2 = next(row for row in rows if row["case_id"] == "case-rank2")
        self.assertFalse(rank2["top1_hit"])
        self.assertTrue(rank2["top3_hit"])
        self.assertEqual(rank2["best_rank"], 2)
        self.assertTrue(rank2["method_disagreement"])
        self.assertTrue(rank2["low_margin"])
        self.assertEqual(rank2["suggested_gate_action"], "defer_to_llm_candidate")

        miss = next(row for row in rows if row["case_id"] == "case-miss")
        self.assertEqual(miss["suggested_gate_action"], "low_diagnosability_candidate")

    def test_writes_analysis_outputs(self):
        rows, summary = analyze_skillpipe_records(
            [
                {
                    "dir": "/cases/case-rank2",
                    "skill_ips": ["10.0.0.2", "10.0.0.1"],
                    "gt_ips": ["10.0.0.1"],
                    "response": _response(
                        ["10.0.0.2", "10.0.0.1"],
                        {"1": {"top3": [["10.0.0.2", 0.7], ["10.0.0.1", 0.68]]}},
                    ),
                }
            ],
            margin_threshold=0.05,
        )

        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_analysis_outputs(rows, summary, tmp)
            for path in outputs.values():
                self.assertTrue(os.path.exists(path), path)

            with open(outputs["failures_csv"], encoding="utf-8") as f:
                self.assertIn("top1_miss_gt_in_top3", f.read())


if __name__ == "__main__":
    unittest.main()
