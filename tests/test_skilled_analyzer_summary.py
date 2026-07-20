import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from Sys.RootCauseAnalyze.SkilledAnalyzer import SkilledAnalyzer, _cached_evidence_mode


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
            self.assertEqual(gate["evidence_mode"], "live_summary")
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
            self.assertEqual(gate["evidence_mode"], "cached_summary")
            self.assertIn("CACHED_SUMMARY", prompt)
            self.assertFalse(hasattr(analyzer, "seen_candidate_detail"))

    def test_summary_cache_key_changes_with_evidence_top_k(self):
        from Sys.RootCauseAnalyze.SkilledAnalyzer import _case_cache_key

        self.assertNotEqual(_case_cache_key("case-a", 5), _case_cache_key("case-a", 10))

    def test_cache_evidence_modes_are_distinguishable(self):
        self.assertEqual(
            _cached_evidence_mode("Device evidence records (lossless facts only):\n{}"),
            "skeleton_v3",
        )
        self.assertEqual(
            _cached_evidence_mode(
                "Device evidence records (lossless facts + semantic annotation):\n{}"
            ),
            "hybrid_v3",
        )

    def test_cached_summary_is_not_wrapped_as_json_detail(self):
        with tempfile.TemporaryDirectory() as tmp_cache, tempfile.TemporaryDirectory() as tmp_case:
            with open(os.path.join(tmp_case, "info.json"), "w", encoding="utf-8") as f:
                json.dump({"alarm_time": 1000}, f)

            from Sys.RootCauseAnalyze.SkilledAnalyzer import _case_cache_key
            key = _case_cache_key(tmp_case)
            with open(os.path.join(tmp_cache, f"{key}.json"), "w", encoding="utf-8") as f:
                json.dump({"summary": "CACHED_SUMMARY: plain text"}, f)

            analyzer = SummaryAnalyzer(
                summarize_nodes=True, model_path="unused",
                summary_cache_dir=tmp_cache,
            )
            analyzer.executor = FakeExecutor()
            _setup_fake_llm(analyzer)
            prompt, _skill_ips, gate = analyzer._build_final_prompt("", ["1", "2"], tmp_case)

            self.assertEqual(gate["decision"], "invoke_llm")
            self.assertIn("# 3. 候选设备状态摘要", prompt)
            self.assertNotIn("```json\nCACHED_SUMMARY", prompt)
            self.assertNotIn("候选设备详情(JSON)", prompt)

    def test_cached_think_content_is_removed_from_main_prompt(self):
        with tempfile.TemporaryDirectory() as tmp_cache, tempfile.TemporaryDirectory() as tmp_case:
            from Sys.RootCauseAnalyze.SkilledAnalyzer import _case_cache_key

            key = _case_cache_key(tmp_case)
            with open(os.path.join(tmp_cache, f"{key}.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "summary": (
                        "Device state summaries:\n"
                        "- 10.0.0.1: <think>very long reasoning</think>"
                        "存在 trunkdown 告警。"
                    )
                }, f)

            analyzer = SummaryAnalyzer(model_path="unused", summary_cache_dir=tmp_cache)
            analyzer.executor = FakeExecutor()
            _setup_fake_llm(analyzer)
            prompt, _skill_ips, _gate = analyzer._build_final_prompt("", ["1", "2"], tmp_case)

            self.assertNotIn("<think>", prompt)
            self.assertNotIn("very long reasoning", prompt)
            self.assertIn("存在 trunkdown 告警", prompt)

    def test_arbitration_prompt_explains_score_scale_and_output_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            analyzer = SummaryAnalyzer(model_path="unused")
            analyzer.executor = FakeExecutor()
            _setup_fake_llm(analyzer)
            prompt, _skill_ips, _gate = analyzer._build_final_prompt("", ["1", "2"], tmp)

            self.assertIn("禁止直接比较其分数数值大小", prompt)
            self.assertIn('"invocation_reason": "confidence_gate_disabled"', prompt)
            self.assertIn('"decision": "keep_baseline | adjust_ranking | insufficient_evidence"', prompt)
            self.assertIn('"supporting_evidence"', prompt)

    def test_cli_passes_summary_cache_dir_to_workers(self):
        source = Path("Sys/RootCauseAnalyze/SkilledAnalyzer.py").read_text(encoding="utf-8")

        self.assertIn("summary_cache_dir=args.summary_cache_dir", source)

    def test_explicit_empty_cache_dir_disables_environment_default(self):
        with patch.dict(os.environ, {"PINGMESH_SUMMARY_CACHE_DIR": "ENV_CACHE"}):
            analyzer = SummaryAnalyzer(model_path="unused", summary_cache_dir="")
        self.assertEqual(analyzer.summary_cache_dir, "")

    def test_cli_and_shell_scripts_support_print_first_prompt(self):
        analyzer_source = Path("Sys/RootCauseAnalyze/SkilledAnalyzer.py").read_text(encoding="utf-8")
        run_inference = Path("scripts/run_inference.sh").read_text(encoding="utf-8")
        run_experiments = Path("scripts/run_gate_pipe_experiments.sh").read_text(encoding="utf-8")

        self.assertIn("--print-first-prompt", analyzer_source)
        self.assertIn("print_first_prompt=args.print_first_prompt", analyzer_source)
        self.assertIn("--print-first-prompt", run_inference)
        self.assertIn("--print-first-prompt", run_experiments)

    def test_v3_ablation_script_covers_raw_skeleton_and_hybrid(self):
        script = Path("scripts/run_paper_07_v3_summary_ablation.sh").read_text(encoding="utf-8")

        self.assertIn("gate_raw_llm", script)
        self.assertIn("gate_skeleton_llm", script)
        self.assertIn("gate_hybrid_v3_llm", script)
        self.assertIn("--skeleton-only", script)
        self.assertIn('cache_args+=(--summary-cache-dir "")', script)
        self.assertIn("[evidence-audit]", script)
        self.assertNotIn('PINGMESH_V3_ABLATION_TEMPERATURE:-0.0', script)

    def test_batch_infer_prints_only_first_final_prompt_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            analyzer = SummaryAnalyzer(model_path="unused")
            analyzer.executor = FakeExecutor()
            _setup_fake_llm(analyzer)

            with patch.object(
                analyzer,
                "_build_final_prompt",
                side_effect=[
                    ("FIRST_FINAL_PROMPT", ["10.0.0.1"], {"decision": "bypass_llm"}),
                    ("SECOND_FINAL_PROMPT", ["10.0.0.2"], {"decision": "bypass_llm"}),
                ],
            ):
                output = StringIO()
                with redirect_stdout(output):
                    analyzer.batch_infer(
                        dirpaths=[tmp_a, tmp_b],
                        prompts=["raw_a", "raw_b"],
                        target_skill_ids=["1", "2"],
                        batch_size=1,
                        print_first_prompt=True,
                    )

            printed = output.getvalue()
            self.assertIn("FIRST_FINAL_PROMPT", printed)
            self.assertNotIn("SECOND_FINAL_PROMPT", printed)


if __name__ == "__main__":
    unittest.main()
