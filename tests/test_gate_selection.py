"""Unit and integration tests for evaluate_gate_selection.py."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

# Ensure project root is on sys.path for local test runs.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
import sys as _sys

if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

from Sys.Score.evaluate_gate_selection import (
    _compute_metrics,
    _determine_best,
    _extract_llm_ips,
    _extract_method_ips,
    _extract_skill_ret_from_prompt,
    evaluate_gate_selection,
)

# ── helpers (mirroring test_trust_tree_gate.py pattern) ───────────────


def _rankings(items, score_key):
    """Build rankings list from (ip, score, extra) tuples."""
    return [
        {"rank": i + 1, "ip": ip, score_key: score, **extra}
        for i, (ip, score, extra) in enumerate(items)
    ]


def _skill_ret_json(combined, topo, temporal):
    """Build a skill_ret JSON string matching build_fused_evidence output."""
    payload = {
        "combined_score_rankings": _rankings(combined, "combined_score"),
        "topo": {"rankings": _rankings(topo, "pr_score")},
        "temporal": {"rankings": _rankings(temporal, "score")},
    }
    return json.dumps(payload, ensure_ascii=False)


def _make_skilled_prompt(skill_ret_json_str, info_text="mock info", nodes_json_str='{"devices": []}'):
    """Build a SKILLED_PROMPT-format string as SkilledAnalyzer would produce."""
    return f"""# 角色
你是数据中心网络排障专家。

# 输入数据

**1. 故障概况**
**2. 算法综合排名(JSON)**
**3. 候选设备详情(JSON)**

# 你的任务

**默认信任算法排名**。

# 约束
- 不能编造 IP
- 输出 1-3 个最可疑的设备

# 输出格式

```json
{{
  "reasoning": "...",
  "ip": ["<IP>"]
}}
```

---

# 1. 故障概况
{info_text}

# 2. 算法分析
```json
{skill_ret_json_str}
```

# 3. 候选设备详情
```json
{nodes_json_str}
```
"""


def _make_llm_response(ips):
    """Build a mock LLM response in JSON-block format."""
    payload = {"reasoning": "mock llm analysis", "ip": ips}
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"


def _make_label_v2(primary_ips, secondary_ips=None):
    """Build a label_v2.json dict."""
    label = {"primary_root_cause": primary_ips}
    if secondary_ips:
        label["secondary_root_causes"] = secondary_ips
    return label


# ── unit tests ───────────────────────────────────────────────────────


class ExtractSkillRetTest(unittest.TestCase):
    def test_extracts_skill_ret_from_skilled_prompt(self):
        skill_ret = _skill_ret_json(
            combined=[("10.0.0.1", 0.95, {}), ("10.0.0.2", 0.80, {})],
            topo=[("10.0.0.1", 98.0, {}), ("10.0.0.2", 70.0, {})],
            temporal=[("10.0.0.2", 0.90, {}), ("10.0.0.1", 0.85, {})],
        )
        prompt = _make_skilled_prompt(skill_ret)
        result = _extract_skill_ret_from_prompt(prompt)

        self.assertIsNotNone(result)
        self.assertIn("topo", result)
        self.assertIn("temporal", result)
        self.assertIn("combined_score_rankings", result)
        # Verify it is the skill_ret, not the nodes block
        self.assertNotIn("devices", result)

    def test_returns_none_for_empty_prompt(self):
        self.assertIsNone(_extract_skill_ret_from_prompt(""))
        self.assertIsNone(_extract_skill_ret_from_prompt(None))

    def test_returns_none_when_no_json_block_found(self):
        prompt = "This is a plain text prompt without any code blocks."
        self.assertIsNone(_extract_skill_ret_from_prompt(prompt))

    def test_returns_none_when_json_lacks_topo_temporal_keys(self):
        prompt = """# 2. 算法分析
```json
{"combined_score_rankings": [], "other_key": "value"}
```
"""
        result = _extract_skill_ret_from_prompt(prompt)
        self.assertIsNone(result)


class ExtractMethodIpsTest(unittest.TestCase):
    def setUp(self):
        self.skill_ret = {
            "topo": {
                "rankings": [
                    {"rank": 1, "ip": "10.0.0.1", "pr_score": 98.0},
                    {"rank": 2, "ip": "10.0.0.2", "pr_score": 70.0},
                    {"rank": 3, "ip": "10.0.0.3", "pr_score": 60.0},
                ]
            },
            "temporal": {
                "rankings": [
                    {"rank": 1, "ip": "10.0.0.2", "score": 0.90},
                    {"rank": 2, "ip": "10.0.0.1", "score": 0.85},
                    {"rank": 3, "ip": "10.0.0.4", "score": 0.50},
                ]
            },
        }

    def test_extracts_topo_ips_sorted_by_pr_score(self):
        ips = _extract_method_ips(self.skill_ret, "topo")
        self.assertEqual(ips, ["10.0.0.1", "10.0.0.2", "10.0.0.3"])

    def test_extracts_temporal_ips_sorted_by_score(self):
        ips = _extract_method_ips(self.skill_ret, "temporal")
        self.assertEqual(ips, ["10.0.0.2", "10.0.0.1", "10.0.0.4"])

    def test_returns_empty_for_unknown_method(self):
        self.assertEqual(_extract_method_ips(self.skill_ret, "combined"), [])

    def test_returns_empty_for_missing_block(self):
        self.assertEqual(_extract_method_ips({}, "topo"), [])

    def test_deduplicates_ips(self):
        skill_ret = {
            "topo": {
                "rankings": [
                    {"rank": 1, "ip": "10.0.0.1", "pr_score": 98.0},
                    {"rank": 2, "ip": "10.0.0.1", "pr_score": 50.0},
                ]
            }
        }
        ips = _extract_method_ips(skill_ret, "topo")
        self.assertEqual(ips, ["10.0.0.1"])


class ExtractLlmIpsTest(unittest.TestCase):
    def test_parses_json_block_response(self):
        response = _make_llm_response(["10.0.0.1", "10.0.0.2"])
        ips = _extract_llm_ips(response)
        self.assertEqual(ips, ["10.0.0.1", "10.0.0.2"])

    def test_parses_quoted_ip_response(self):
        response = '{"reasoning": "test", "ip": "10.0.0.5"}'
        ips = _extract_llm_ips(response)
        self.assertEqual(ips, ["10.0.0.5"])

    def test_returns_empty_for_garbled_response(self):
        ips = _extract_llm_ips("The root cause is unclear, please check manually.")
        self.assertEqual(ips, [])

    def test_returns_empty_for_empty_string(self):
        self.assertEqual(_extract_llm_ips(""), [])


class ComputeMetricsTest(unittest.TestCase):
    def test_top1_hit(self):
        m = _compute_metrics(["10.0.0.1"], ["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        self.assertTrue(m["top1_hit"])
        self.assertTrue(m["top3_hit"])
        self.assertTrue(m["top5_hit"])
        self.assertEqual(m["best_rank"], 1)

    def test_top3_hit(self):
        m = _compute_metrics(["10.0.0.3"], ["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        self.assertFalse(m["top1_hit"])
        self.assertTrue(m["top3_hit"])
        self.assertTrue(m["top5_hit"])
        self.assertEqual(m["best_rank"], 3)

    def test_miss(self):
        m = _compute_metrics(["10.0.0.99"], ["10.0.0.1", "10.0.0.2"])
        self.assertFalse(m["top1_hit"])
        self.assertFalse(m["top5_hit"])
        self.assertIsNone(m["best_rank"])
        self.assertTrue(m["is_failed"])

    def test_multiple_gt_ips_best_rank_is_min(self):
        m = _compute_metrics(["10.0.0.3", "10.0.0.1"], ["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        self.assertTrue(m["top1_hit"])
        self.assertEqual(m["best_rank"], 1)


class DetermineBestTest(unittest.TestCase):
    def test_llm_best_when_only_llm_hits_top1(self):
        topo_m = _compute_metrics(["10.0.0.1"], ["10.0.0.3", "10.0.0.2"])
        temp_m = _compute_metrics(["10.0.0.1"], ["10.0.0.4", "10.0.0.5"])
        llm_m = _compute_metrics(["10.0.0.1"], ["10.0.0.1"])
        self.assertEqual(_determine_best(topo_m, temp_m, llm_m), "llm")

    def test_topo_best_when_only_topo_hits(self):
        topo_m = _compute_metrics(["10.0.0.1"], ["10.0.0.1"])
        temp_m = _compute_metrics(["10.0.0.1"], ["10.0.0.3"])
        llm_m = _compute_metrics(["10.0.0.1"], ["10.0.0.5"])
        self.assertEqual(_determine_best(topo_m, temp_m, llm_m), "topo")

    def test_tie_when_all_hit_top1(self):
        topo_m = _compute_metrics(["10.0.0.1"], ["10.0.0.1", "10.0.0.2"])
        temp_m = _compute_metrics(["10.0.0.1"], ["10.0.0.1", "10.0.0.3"])
        llm_m = _compute_metrics(["10.0.0.1"], ["10.0.0.1"])
        self.assertEqual(_determine_best(topo_m, temp_m, llm_m), "tie")

    def test_tie_when_all_miss(self):
        topo_m = _compute_metrics(["10.0.0.99"], ["10.0.0.1", "10.0.0.2"])
        temp_m = _compute_metrics(["10.0.0.99"], ["10.0.0.3", "10.0.0.4"])
        llm_m = _compute_metrics(["10.0.0.99"], ["10.0.0.5", "10.0.0.6"])
        self.assertEqual(_determine_best(topo_m, temp_m, llm_m), "tie")

    def test_best_rank_tiebreak(self):
        # topo hits at rank 1, llm hits at rank 2 → topo wins
        topo_m = _compute_metrics(["10.0.0.1"], ["10.0.0.1", "10.0.0.2"])
        llm_m = _compute_metrics(["10.0.0.1"], ["10.0.0.3", "10.0.0.1"])
        temp_m = _compute_metrics(["10.0.0.1"], ["10.0.0.5"])
        self.assertEqual(_determine_best(topo_m, temp_m, llm_m), "topo")

    def test_temporal_best_when_best_rank(self):
        topo_m = _compute_metrics(["10.0.0.1"], ["10.0.0.3", "10.0.0.1"])  # rank 2
        temp_m = _compute_metrics(["10.0.0.1"], ["10.0.0.1"])               # rank 1
        llm_m = _compute_metrics(["10.0.0.1"], ["10.0.0.4"])               # miss
        self.assertEqual(_determine_best(topo_m, temp_m, llm_m), "temporal")

    def test_llm_empty_output_never_best(self):
        topo_m = _compute_metrics(["10.0.0.1"], ["10.0.0.2", "10.0.0.1"])  # rank 2
        temp_m = _compute_metrics(["10.0.0.1"], ["10.0.0.5"])               # miss
        llm_m = _compute_metrics(["10.0.0.1"], [])                          # empty → miss
        self.assertEqual(_determine_best(topo_m, temp_m, llm_m), "topo")


# ── integration test ─────────────────────────────────────────────────


class GateSelectionIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def _make_case_dir(self, name, gt_ips):
        """Create a mock case directory with label_v2.json."""
        case_dir = os.path.join(self.tmp_dir.name, name)
        os.makedirs(case_dir, exist_ok=True)
        label_path = os.path.join(case_dir, "label_v2.json")
        with open(label_path, "w", encoding="utf-8") as f:
            json.dump(_make_label_v2(gt_ips), f, ensure_ascii=False, indent=2)
        return case_dir

    def _make_record(self, case_dir, topo_rankings, temporal_rankings, llm_ips, gate_reason="topo_strong_defer_to_llm"):
        """Build a single mock SkilledAnalyzer record."""
        skill_ret = _skill_ret_json(
            combined=topo_rankings,  # not critical for test
            topo=topo_rankings,
            temporal=temporal_rankings,
        )
        prompt = _make_skilled_prompt(skill_ret)
        response = _make_llm_response(llm_ips)
        return {
            "dir": case_dir,
            "prompt": prompt,
            "response": response,
            "skill_ips": [ip for ip, _score, _extra in topo_rankings],
            "confidence_gate": {
                "enabled": True,
                "decision": "invoke_llm",
                "route": "llm",
                "reason": gate_reason,
                "recommended_ips": [ip for ip, _score, _extra in topo_rankings],
            },
        }

    def test_evaluates_invoke_llm_cases(self):
        # Case 1: LLM is best (hits top-1, others miss)
        dir1 = self._make_case_dir("case_001", ["10.0.0.5"])
        rec1 = self._make_record(
            dir1,
            topo_rankings=[("10.0.0.1", 98.0, {}), ("10.0.0.2", 70.0, {})],
            temporal_rankings=[("10.0.0.3", 0.90, {}), ("10.0.0.4", 0.50, {})],
            llm_ips=["10.0.0.5", "10.0.0.1"],
        )

        # Case 2: topo is best (LLM misses)
        dir2 = self._make_case_dir("case_002", ["10.0.0.1"])
        rec2 = self._make_record(
            dir2,
            topo_rankings=[("10.0.0.1", 98.0, {}), ("10.0.0.2", 70.0, {})],
            temporal_rankings=[("10.0.0.3", 0.90, {}), ("10.0.0.4", 0.50, {})],
            llm_ips=["10.0.0.9", "10.0.0.8"],
            gate_reason="strong_ranker_conflict_invoke_llm",
        )

        # Case 3: bypass_llm (should be skipped)
        dir3 = self._make_case_dir("case_003", ["10.0.0.1"])
        skill_ret3 = _skill_ret_json(
            combined=[("10.0.0.1", 0.95, {}), ("10.0.0.2", 0.80, {})],
            topo=[("10.0.0.1", 98.0, {}), ("10.0.0.2", 70.0, {})],
            temporal=[("10.0.0.2", 0.90, {}), ("10.0.0.1", 0.85, {})],
        )
        rec3 = {
            "dir": dir3,
            "prompt": _make_skilled_prompt(skill_ret3),
            "response": _make_llm_response(["10.0.0.1"]),
            "skill_ips": ["10.0.0.1", "10.0.0.2"],
            "confidence_gate": {
                "enabled": True,
                "decision": "bypass_llm",
                "route": "combined",
                "reason": "rankers_near_accept_combined",
                "recommended_ips": ["10.0.0.1", "10.0.0.2"],
            },
        }

        records = [rec1, rec2, rec3]
        out_dir = os.path.join(self.tmp_dir.name, "output")

        summary = evaluate_gate_selection.__wrapped__(
            _res_path=None, records=records, out_dir=out_dir
        ) if hasattr(evaluate_gate_selection, "__wrapped__") else self._run_eval(records, out_dir)

    def _run_eval(self, records, out_dir):
        """Run evaluate_gate_selection bypassing file loading."""
        # Save temp res.json and run normally
        res_path = os.path.join(self.tmp_dir.name, "res.json")
        with open(res_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        return evaluate_gate_selection(res_path, out_dir)

    def test_full_pipeline(self):
        # Case 1: LLM best
        dir1 = self._make_case_dir("case_001", ["10.0.0.5"])
        rec1 = self._make_record(
            dir1,
            topo_rankings=[("10.0.0.1", 98.0, {}), ("10.0.0.2", 70.0, {})],
            temporal_rankings=[("10.0.0.3", 0.90, {}), ("10.0.0.4", 0.50, {})],
            llm_ips=["10.0.0.5", "10.0.0.1"],
        )

        # Case 2: topo best (LLM worse)
        dir2 = self._make_case_dir("case_002", ["10.0.0.1"])
        rec2 = self._make_record(
            dir2,
            topo_rankings=[("10.0.0.1", 98.0, {}), ("10.0.0.2", 70.0, {})],
            temporal_rankings=[("10.0.0.3", 0.90, {}), ("10.0.0.4", 0.50, {})],
            llm_ips=["10.0.0.9", "10.0.0.8"],
            gate_reason="strong_ranker_conflict_invoke_llm",
        )

        # Case 3: tie (all hit top-1)
        dir3 = self._make_case_dir("case_003", ["10.0.0.1"])
        rec3 = self._make_record(
            dir3,
            topo_rankings=[("10.0.0.1", 98.0, {}), ("10.0.0.2", 70.0, {})],
            temporal_rankings=[("10.0.0.1", 0.90, {}), ("10.0.0.2", 0.50, {})],
            llm_ips=["10.0.0.1"],
        )

        records = [rec1, rec2, rec3]
        out_dir = os.path.join(self.tmp_dir.name, "output")

        summary = self._run_eval(records, out_dir)

        self.assertEqual(summary["total_invoke_llm_cases"], 3)
        self.assertEqual(summary["evaluated"], 3)
        self.assertEqual(summary["skipped"]["no_gt"], 0)
        self.assertEqual(summary["llm_best"], 1)
        self.assertEqual(summary["llm_worse"], 1)
        self.assertEqual(summary["llm_tied_for_best"], 1)
        self.assertEqual(summary["when_llm_worse"]["better_is_topo"], 1)

        # Check output files exist
        self.assertTrue(os.path.exists(os.path.join(out_dir, "gate_selection_cases.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(out_dir, "gate_selection_summary.json")))
        self.assertTrue(os.path.exists(os.path.join(out_dir, "gate_selection_summary.csv")))

        # Check JSONL content
        with open(os.path.join(out_dir, "gate_selection_cases.jsonl"), encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0]["case_id"], "case_001")
        self.assertEqual(lines[0]["llm_vs_best"], "llm_best")
        self.assertEqual(lines[1]["llm_vs_best"], "llm_worse")
        self.assertEqual(lines[2]["llm_vs_best"], "llm_tied_for_best")

    def test_skips_cases_without_gt(self):
        """Cases without ground truth should be skipped."""
        dir_no_gt = os.path.join(self.tmp_dir.name, "case_no_gt")
        os.makedirs(dir_no_gt, exist_ok=True)
        # No label file → no GT

        rec = self._make_record(
            dir_no_gt,
            topo_rankings=[("10.0.0.1", 98.0, {})],
            temporal_rankings=[("10.0.0.2", 0.90, {})],
            llm_ips=["10.0.0.1"],
        )

        out_dir = os.path.join(self.tmp_dir.name, "output")
        summary = self._run_eval([rec], out_dir)

        self.assertEqual(summary["total_invoke_llm_cases"], 1)
        self.assertEqual(summary["evaluated"], 0)
        self.assertEqual(summary["skipped"]["no_gt"], 1)

    def test_skips_cases_with_malformed_prompt(self):
        """Cases where prompt cannot yield skill_ret should be skipped."""
        dir1 = self._make_case_dir("case_001", ["10.0.0.1"])
        rec = {
            "dir": dir1,
            "prompt": "garbled prompt without json blocks",
            "response": _make_llm_response(["10.0.0.1"]),
            "confidence_gate": {
                "enabled": True,
                "decision": "invoke_llm",
                "route": "llm",
                "reason": "topo_strong_defer_to_llm",
            },
        }

        out_dir = os.path.join(self.tmp_dir.name, "output")
        summary = self._run_eval([rec], out_dir)

        self.assertEqual(summary["total_invoke_llm_cases"], 1)
        self.assertEqual(summary["evaluated"], 0)
        self.assertEqual(summary["skipped"]["skill_ret_error"], 1)


if __name__ == "__main__":
    unittest.main()
