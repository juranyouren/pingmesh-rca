import json
import os
import tempfile
import unittest

from Sys.Score.apply_trust_gate import apply_trust_gate_records


class ApplyTrustGateTest(unittest.TestCase):
    def test_gate_pipe_outputs_auto_routes_and_leaves_llm_route_empty(self):
        records = [
            {
                "dir": "/cases/near",
                "skill_ips": ["10.0.0.1", "10.0.0.2"],
                "gt_ips": ["10.0.0.1"],
                "response": "unused",
                "skill_details": {
                    "combined": {"topk": [{"ip": "10.0.0.1", "combined_score": 0.9}]},
                    "1": {"topk": [{"ip": "10.0.0.1", "pr_score": 0.9}], "trust_tree": {"state": "strong"}},
                    "2": {"topk": [{"ip": "10.0.0.1", "score": 0.8}], "trust_tree": {"state": "strong"}},
                },
            },
            {
                "dir": "/cases/llm",
                "skill_ips": ["10.0.0.9", "10.0.0.8"],
                "gt_ips": ["10.0.0.8"],
                "response": "unused",
                "skill_details": {
                    "combined": {"topk": [{"ip": "10.0.0.9", "combined_score": 0.9}]},
                    "1": {"topk": [{"ip": "10.0.0.1", "pr_score": 0.9}], "trust_tree": {"state": "strong"}},
                    "2": {"topk": [{"ip": "10.0.0.2", "score": 0.8}], "trust_tree": {"state": "weak"}},
                },
            },
        ]

        converted = apply_trust_gate_records(records)

        self.assertEqual(converted[0]["confidence_gate"]["route"], "combined")
        self.assertEqual(converted[0]["skill_ips"], ["10.0.0.1"])
        first_payload = json.loads(converted[0]["response"].split("```json\n", 1)[1].rsplit("\n```", 1)[0])
        self.assertEqual(first_payload["ip"], ["10.0.0.1"])

        self.assertEqual(converted[1]["confidence_gate"]["route"], "llm")
        self.assertEqual(converted[1]["skill_ips"], [])
        second_payload = json.loads(converted[1]["response"].split("```json\n", 1)[1].rsplit("\n```", 1)[0])
        self.assertEqual(second_payload["ip"], [])
        self.assertIn("offline gate+pipe", second_payload["reasoning"])

    def test_writes_res_json(self):
        records = [
            {
                "dir": "/cases/operator",
                "skill_ips": ["10.0.0.9"],
                "gt_ips": ["10.0.0.7"],
                "skill_details": {
                    "combined": {"topk": [{"ip": "10.0.0.9", "combined_score": 0.3}]},
                    "1": {"topk": [{"ip": "10.0.0.9", "pr_score": 0.3}], "trust_tree": {"state": "weak"}},
                    "2": {"topk": [{"ip": "10.0.0.8", "score": 0.3}], "trust_tree": {"state": "weak"}},
                },
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "res.json")
            converted = apply_trust_gate_records(records, output_path=out_path)

            self.assertTrue(os.path.exists(out_path))
            self.assertEqual(json.load(open(out_path, encoding="utf-8")), converted)


if __name__ == "__main__":
    unittest.main()
