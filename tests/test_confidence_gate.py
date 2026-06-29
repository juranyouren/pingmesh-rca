import json
import unittest

from Sys.RootCauseAnalyze.confidence_gate import assess_gate


def _skill_ret(combined, topo=None, temporal=None):
    return json.dumps(
        {
            "combined_score_rankings": [
                {"rank": i + 1, "ip": ip, "combined_score": score}
                for i, (ip, score) in enumerate(combined)
            ],
            "topo": {
                "rankings": [
                    {"rank": i + 1, "ip": ip, "pr_score": score}
                    for i, (ip, score) in enumerate(topo or [])
                ]
            },
            "temporal": {
                "rankings": [
                    {"rank": i + 1, "ip": ip, "score": score}
                    for i, (ip, score) in enumerate(temporal or [])
                ]
            },
        },
        ensure_ascii=False,
    )


class ConfidenceGateTest(unittest.TestCase):
    def test_bypasses_llm_when_combined_margin_is_high(self):
        gate = assess_gate(
            _skill_ret(
                combined=[("10.0.0.1", 96.0), ("10.0.0.2", 70.0)],
                topo=[("10.0.0.1", 94.0), ("10.0.0.2", 80.0)],
                temporal=[("10.0.0.3", 95.0), ("10.0.0.1", 88.0)],
            ),
            high_margin=15.0,
        )

        self.assertEqual(gate["decision"], "bypass_llm")
        self.assertEqual(gate["reason"], "combined_high_margin")
        self.assertEqual(gate["recommended_ips"], ["10.0.0.1", "10.0.0.2"])
        self.assertGreaterEqual(gate["methods"]["combined"]["margin"], 15.0)

    def test_invokes_llm_when_margin_is_low_and_methods_disagree(self):
        gate = assess_gate(
            _skill_ret(
                combined=[("10.0.0.1", 80.0), ("10.0.0.2", 75.0)],
                topo=[("10.0.0.2", 91.0), ("10.0.0.1", 90.0)],
                temporal=[("10.0.0.3", 96.0), ("10.0.0.1", 92.0)],
            ),
            high_margin=15.0,
            agreement_margin=8.0,
        )

        self.assertEqual(gate["decision"], "invoke_llm")
        self.assertEqual(gate["reason"], "low_confidence_or_disagreement")
        self.assertLess(gate["methods"]["combined"]["margin"], 15.0)
        self.assertEqual(gate["agreement"]["top1_votes_for_combined"], 1)

    def test_bypasses_llm_when_topo_and_temporal_agree_with_combined(self):
        gate = assess_gate(
            _skill_ret(
                combined=[("10.0.0.1", 80.0), ("10.0.0.2", 74.0)],
                topo=[("10.0.0.1", 91.0), ("10.0.0.2", 84.0)],
                temporal=[("10.0.0.1", 88.0), ("10.0.0.3", 79.0)],
            ),
            high_margin=15.0,
            agreement_margin=5.0,
        )

        self.assertEqual(gate["decision"], "bypass_llm")
        self.assertEqual(gate["reason"], "method_agreement")
        self.assertEqual(gate["agreement"]["top1_votes_for_combined"], 3)

    def test_invokes_llm_when_rankings_are_missing(self):
        gate = assess_gate("not json")

        self.assertEqual(gate["decision"], "invoke_llm")
        self.assertEqual(gate["reason"], "invalid_or_missing_rankings")
        self.assertEqual(gate["recommended_ips"], [])


class ConfidenceGateIntegrationTest(unittest.TestCase):
    def test_batch_infer_only_sends_low_confidence_cases_to_llm(self):
        from Sys.RootCauseAnalyze.SkilledAnalyzer import SkilledAnalyzer

        analyzer = SkilledAnalyzer.__new__(SkilledAnalyzer)
        analyzer.confidence_gate_enabled = True
        analyzer._read_gt_ips = lambda _dirpath: []

        bypass_gate = {
            "enabled": True,
            "decision": "bypass_llm",
            "reason": "combined_high_margin",
            "recommended_ips": ["10.0.0.1", "10.0.0.2"],
            "methods": {"combined": {"margin": 22.0}},
        }
        llm_gate = {
            "enabled": True,
            "decision": "invoke_llm",
            "reason": "low_confidence_or_disagreement",
            "recommended_ips": ["10.0.0.3"],
        }

        def fake_build_final_prompt(original_prompt, _skill_ids, _dirpath):
            if original_prompt == "high-confidence":
                return "CONFIDENCE_GATE_BYPASS", ["10.0.0.1", "10.0.0.2"], bypass_gate
            return "low-confidence prompt", ["10.0.0.3"], llm_gate

        analyzer._build_final_prompt = fake_build_final_prompt

        class FakeResponse:
            def __init__(self, text):
                output = type("Output", (), {"text": text})()
                self.outputs = [output]

        class FakeLLM:
            def __init__(self):
                self.calls = []

            def chat(self, applied_prompts, _sampling_params):
                self.calls.append(applied_prompts)
                return [FakeResponse("llm response") for _ in applied_prompts]

        fake_llm = FakeLLM()

        def fake_ensure_llm():
            analyzer.llm = fake_llm
            analyzer.sampling_params = object()

        analyzer._ensure_llm = fake_ensure_llm

        (
            responses,
            final_prompts,
            retrieval_responses,
            _skill_ids_list,
            skill_ips_list,
            _gt_ips_list,
            confidence_gates,
        ) = analyzer.batch_infer(
            ["case-high", "case-low"],
            ["high-confidence", "low-confidence"],
            ["topo", "temporal"],
            batch_size=8,
        )

        self.assertIn("10.0.0.1", responses[0])
        self.assertEqual(responses[1], "llm response")
        self.assertEqual(final_prompts, ["CONFIDENCE_GATE_BYPASS", "low-confidence prompt"])
        self.assertEqual(retrieval_responses[0], "Confidence gate bypassed LLM")
        self.assertEqual(skill_ips_list[0], ["10.0.0.1", "10.0.0.2"])
        self.assertEqual(confidence_gates, [bypass_gate, llm_gate])
        self.assertEqual(len(fake_llm.calls), 1)
        self.assertEqual(fake_llm.calls[0][0][0]["content"], "low-confidence prompt")


if __name__ == "__main__":
    unittest.main()
