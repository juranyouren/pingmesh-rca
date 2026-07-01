import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from Sys.RootCauseAnalyze.SkilledAnalyzer import SkilledAnalyzer


class FakeExecutor:
    skill_map = {}

    def get_skill_conf(self):
        return [{"skill_id": "1"}, {"skill_id": "2"}]

    def get_node_list(self, _dirpath):
        return [
            {
                "mgmt_ip": "10.0.0.1",
                "role": "leaf",
                "cross": 3,
                "linked_to": ["10.0.0.2"],
                "linked_from": [],
                "alarms": [{"alarm_name": "trunkdown", "alarm_time": 1000}],
                "logs": [],
            }
        ]

    def get_alarminfo(self, _dirpath):
        return {"alarm_time": 1000}


class SummaryAnalyzer(SkilledAnalyzer):
    """SkilledAnalyzer with _summarize_candidate_detail mocked to avoid
    instantiating VllmNodeSummarizer (which would try to allocate NPU memory).
    """

    def _summarize_candidate_detail(self, candidate_detail: str) -> str:
        self.seen_candidate_detail = candidate_detail
        return "SMALL_MODEL_SUMMARY: 10.0.0.1 trunkdown cross=3"


def _setup_fake_llm(analyzer):
    """Inject a mock LLM + tokenizer so _build_final_prompt can do truncation."""
    mock_llm = MagicMock()
    mock_llm.llm_engine.model_config.max_model_len = 16384
    mock_tokenizer = MagicMock()
    # ~4 chars per token
    mock_tokenizer.encode.side_effect = lambda s: list(range(len(s) // 4)) if s else []
    mock_llm.get_tokenizer.return_value = mock_tokenizer
    analyzer.llm = mock_llm
    analyzer.sampling_params = MagicMock()


class SkilledAnalyzerSummaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._ensure_patcher = patch.object(
            SkilledAnalyzer, "_ensure_llm", autospec=True,
        )
        cls._mock_ensure = cls._ensure_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._ensure_patcher.stop()

    def test_summary_replaces_nodes_in_final_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "info.json"), "w", encoding="utf-8") as f:
                json.dump({"alarm_time": 1000}, f)

            analyzer = SummaryAnalyzer(summarize_nodes=True, model_path="unused")
            analyzer.executor = FakeExecutor()
            _setup_fake_llm(analyzer)
            prompt, _skill_ips, gate = analyzer._build_final_prompt("", ["1", "2"], tmp)

            self.assertEqual(gate["decision"], "invoke_llm")
            self.assertIn("SMALL_MODEL_SUMMARY", prompt)
            self.assertNotIn('"devices"', prompt)
            self.assertIn('"devices"', analyzer.seen_candidate_detail)

    def test_cache_path_reads_summary(self):
        """When summary_cache_dir is set, _summarize_candidate_detail is never called."""
        with tempfile.TemporaryDirectory() as tmp_cache, tempfile.TemporaryDirectory() as tmp_case:
            with open(os.path.join(tmp_case, "info.json"), "w", encoding="utf-8") as f:
                json.dump({"alarm_time": 1000}, f)

            from Sys.RootCauseAnalyze.SkilledAnalyzer import _case_cache_key
            key = _case_cache_key(tmp_case)
            cache_path = os.path.join(tmp_cache, f"{key}.json")
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"summary": "CACHED_SUMMARY: 10.0.0.1 trunkdown"}, f)

            analyzer = SummaryAnalyzer(
                summarize_nodes=True, model_path="unused",
                summary_cache_dir=tmp_cache,
            )
            analyzer.executor = FakeExecutor()
            _setup_fake_llm(analyzer)
            prompt, _skill_ips, gate = analyzer._build_final_prompt("", ["1", "2"], tmp_case)

            self.assertEqual(gate["decision"], "invoke_llm")
            self.assertIn("CACHED_SUMMARY", prompt)
            self.assertFalse(hasattr(analyzer, "seen_candidate_detail"))


if __name__ == "__main__":
    unittest.main()
