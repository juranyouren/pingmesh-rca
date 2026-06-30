import json
import unittest

from Sys.RootCauseAnalyze.gate.node_summarizer import build_candidate_summary_prompt, summarize_nodes_with


class NodeSummarizerTest(unittest.TestCase):
    def test_builds_prompt_from_candidate_detail(self):
        candidate_detail = json.dumps(
            {
                "devices": [
                    {
                        "ip": "10.0.0.1",
                        "role": "leaf",
                        "cross": 3,
                        "alarm_count": 2,
                        "alarms": ["trunkdown", "bgp_down"],
                        "high_severity_alarms": ["trunkdown"],
                        "topology": {"upstream": ["10.0.0.2"], "downstream": ["10.0.0.3"]},
                    }
                ]
            },
            ensure_ascii=False,
        )

        prompt = build_candidate_summary_prompt(candidate_detail)

        self.assertIn("10.0.0.1", prompt)
        self.assertIn("trunkdown", prompt)
        self.assertIn("JSON", prompt)

    def test_summarize_nodes_with_replaces_detail_with_model_summary(self):
        def fake_model(prompts):
            self.assertEqual(len(prompts), 1)
            return ["summary: 10.0.0.1 has high severity trunkdown and cross=3"]

        summary = summarize_nodes_with(
            '{"devices": [{"ip": "10.0.0.1", "cross": 3}]}',
            summarize_batch=fake_model,
        )

        self.assertIn("summary:", summary)
        self.assertIn("10.0.0.1", summary)


if __name__ == "__main__":
    unittest.main()
