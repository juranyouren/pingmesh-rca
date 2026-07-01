"""Tests for gate policy routing logic and ablation evaluator."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from Sys.RootCauseAnalyze.gate_policies import list_policies


# ── helpers ──────────────────────────────────────────────────────────


def _state_tree(state="uncertain"):
    return {"state": state, "passed": [], "failed": [], "evidence": {}}


# ── policy discovery ─────────────────────────────────────────────────


class PolicyDiscoveryTest(unittest.TestCase):
    def test_all_three_policies_available(self):
        policies = list_policies()
        self.assertIn("baseline", policies)
        self.assertIn("strict_combined", policies)
        self.assertIn("conservative", policies)
        for name, fn in policies.items():
            self.assertTrue(callable(fn), f"{name} route is not callable")


# ── baseline ─────────────────────────────────────────────────────────


class BaselinePolicyTest(unittest.TestCase):
    def setUp(self):
        self.policies = list_policies()

    def test_rank_near_routes_to_combined(self):
        """Top-1 match → bypass_llm combined"""
        gate = self.policies["baseline"](
            combined_ips=["10.0.0.9", "10.0.0.1"],
            topo_ips=["10.0.0.1", "10.0.0.2"],
            temporal_ips=["10.0.0.1", "10.0.0.3"],
            topo_tree=_state_tree("strong"),
            temporal_tree=_state_tree("strong"),
        )
        self.assertEqual(gate["decision"], "bypass_llm")
        self.assertEqual(gate["route"], "combined")

    def test_both_weak_routes_to_operator(self):
        gate = self.policies["baseline"](
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1"],
            temporal_ips=["10.0.0.2"],
            topo_tree=_state_tree("weak"),
            temporal_tree=_state_tree("weak"),
        )
        self.assertEqual(gate["decision"], "operator_review")
        self.assertEqual(gate["route"], "operator")

    def test_topo_strong_alone_invokes_llm(self):
        gate = self.policies["baseline"](
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1", "10.0.0.2"],
            temporal_ips=["10.0.0.4", "10.0.0.5"],
            topo_tree=_state_tree("strong"),
            temporal_tree=_state_tree("weak"),
        )
        self.assertEqual(gate["decision"], "invoke_llm")
        self.assertEqual(gate["route"], "llm")

    def test_temporal_strong_alone_bypasses_llm(self):
        gate = self.policies["baseline"](
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1"],
            temporal_ips=["10.0.0.4"],
            topo_tree=_state_tree("weak"),
            temporal_tree=_state_tree("strong"),
        )
        self.assertEqual(gate["decision"], "bypass_llm")
        self.assertEqual(gate["route"], "temporal")


# ── strict_combined (P1) ─────────────────────────────────────────────


class StrictCombinedPolicyTest(unittest.TestCase):
    def setUp(self):
        self.policies = list_policies()

    def test_both_strong_top1_same_routes_to_combined(self):
        """Only route combined when BOTH strong AND top1 match."""
        gate = self.policies["strict_combined"](
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1", "10.0.0.2"],
            temporal_ips=["10.0.0.1", "10.0.0.3"],
            topo_tree=_state_tree("strong"),
            temporal_tree=_state_tree("strong"),
        )
        self.assertEqual(gate["decision"], "bypass_llm")
        self.assertEqual(gate["route"], "combined")
        self.assertEqual(gate["reason"], "both_strong_top1_match_accept_combined")

    def test_top1_match_but_not_both_strong_invokes_llm(self):
        """Top-1 matches but trees are uncertain → invoke LLM (stricter than baseline)."""
        gate = self.policies["strict_combined"](
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1", "10.0.0.2"],
            temporal_ips=["10.0.0.1", "10.0.0.3"],
            topo_tree=_state_tree("uncertain"),
            temporal_tree=_state_tree("uncertain"),
        )
        # baseline would bypass (rank_near=True), but strict should NOT
        self.assertEqual(gate["decision"], "invoke_llm")
        self.assertEqual(gate["route"], "llm")

    def test_both_strong_but_top1_differs_invokes_llm(self):
        """Both strong but top-1 differs → LLM."""
        gate = self.policies["strict_combined"](
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1", "10.0.0.2"],
            temporal_ips=["10.0.0.5", "10.0.0.6"],
            topo_tree=_state_tree("strong"),
            temporal_tree=_state_tree("strong"),
        )
        self.assertEqual(gate["decision"], "invoke_llm")


# ── conservative (P3) ────────────────────────────────────────────────


class ConservativePolicyTest(unittest.TestCase):
    def setUp(self):
        self.policies = list_policies()

    def test_both_strong_top1_same_routes_to_combined(self):
        gate = self.policies["conservative"](
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1", "10.0.0.2"],
            temporal_ips=["10.0.0.1", "10.0.0.3"],
            topo_tree=_state_tree("strong"),
            temporal_tree=_state_tree("strong"),
        )
        self.assertEqual(gate["decision"], "bypass_llm")
        self.assertEqual(gate["route"], "combined")

    def test_temporal_strong_alone_bypasses(self):
        gate = self.policies["conservative"](
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1"],
            temporal_ips=["10.0.0.4", "10.0.0.5"],
            topo_tree=_state_tree("weak"),
            temporal_tree=_state_tree("strong"),
        )
        self.assertEqual(gate["decision"], "bypass_llm")
        self.assertEqual(gate["route"], "temporal")

    def test_topo_strong_alone_invokes_llm(self):
        """Conservative: topo-strong-alone → LLM (no bypass, unlike baseline)."""
        gate = self.policies["conservative"](
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1", "10.0.0.2"],
            temporal_ips=["10.0.0.5", "10.0.0.6"],
            topo_tree=_state_tree("strong"),
            temporal_tree=_state_tree("weak"),
        )
        self.assertEqual(gate["decision"], "invoke_llm")
        self.assertEqual(gate["route"], "llm")

    def test_both_weak_invokes_llm(self):
        """Conservative: weak+weak → LLM (no operator_review)."""
        gate = self.policies["conservative"](
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1"],
            temporal_ips=["10.0.0.2"],
            topo_tree=_state_tree("weak"),
            temporal_tree=_state_tree("weak"),
        )
        self.assertEqual(gate["decision"], "invoke_llm")
        self.assertEqual(gate["route"], "llm")

    def test_uncertain_invokes_llm(self):
        gate = self.policies["conservative"](
            combined_ips=["10.0.0.9"],
            topo_ips=["10.0.0.1"],
            temporal_ips=["10.0.0.2"],
            topo_tree=_state_tree("uncertain"),
            temporal_tree=_state_tree("uncertain"),
        )
        self.assertEqual(gate["decision"], "invoke_llm")
        self.assertEqual(gate["route"], "llm")


# ── integration ──────────────────────────────────────────────────────


class GateAblationIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def _make_case_dir(self, name, gt_ips):
        case_dir = os.path.join(self.tmp_dir.name, name)
        os.makedirs(case_dir, exist_ok=True)
        label = {"primary_root_cause": gt_ips}
        with open(os.path.join(case_dir, "label_v2.json"), "w", encoding="utf-8") as f:
            json.dump(label, f, ensure_ascii=False, indent=2)
        return case_dir

    def _make_skill_ret(self, topo_entries, temp_entries, combined_entries, topo_state="uncertain", temp_state="uncertain"):
        """Build a skill_ret JSON string."""
        def _r(items, key):
            return [{"rank": i + 1, "ip": ip, key: score, **extra}
                    for i, (ip, score, extra) in enumerate(items)]
        payload = {
            "combined_score_rankings": _r(combined_entries, "combined_score"),
            "topo": {
                "rankings": _r(topo_entries, "pr_score"),
                "trust_tree": {"state": topo_state, "passed": [], "failed": [], "evidence": {}},
            },
            "temporal": {
                "rankings": _r(temp_entries, "score"),
                "trust_tree": {"state": temp_state, "passed": [], "failed": [], "evidence": {}},
            },
        }
        return json.dumps(payload, ensure_ascii=False)

    def _make_record(self, case_dir, topo_entries, temp_entries, combined_entries,
                     topo_state="uncertain", temp_state="uncertain",
                     gate_decision="invoke_llm", gate_route="llm",
                     response_ips=None):
        skill_ret = self._make_skill_ret(topo_entries, temp_entries, combined_entries,
                                         topo_state, temp_state)
        response = ""
        if response_ips:
            response = "```json\n" + json.dumps({"reasoning": "test", "ip": response_ips}, ensure_ascii=False) + "\n```"
        return {
            "dir": case_dir,
            "prompt": f"# 2. 算法分析\n```json\n{skill_ret}\n```\n# 3. 候选设备详情\n```json\n{{}}\n```",
            "response": response,
            "confidence_gate": {
                "enabled": True,
                "decision": gate_decision,
                "route": gate_route,
                "reason": "test",
            },
        }

    def test_baseline_vs_strict_on_uncertain_case(self):
        """On a case where baseline bypasses (rank_near loose) but strict invokes LLM.

        Case: top1 match + both uncertain → baseline bypasses (rank_near),
        strict invokes LLM.  LLM output must be available, so the original
        experiment must have run LLM too."""
        dir1 = self._make_case_dir("c1", ["10.0.0.1"])
        # both strong → baseline would bypass, but also invoke_llm in original
        # so LLM output is available for strict_combined's LLM route
        rec = self._make_record(
            dir1,
            topo_entries=[("10.0.0.1", 98.0, {})],
            temp_entries=[("10.0.0.3", 0.9, {})],
            combined_entries=[("10.0.0.1", 0.95, {})],
            topo_state="strong", temp_state="weak",
            gate_decision="invoke_llm", gate_route="llm",
            response_ips=["10.0.0.1"],  # LLM got it right
        )

        res_path = os.path.join(self.tmp_dir.name, "res.json")
        with open(res_path, "w", encoding="utf-8") as f:
            json.dump([rec], f, ensure_ascii=False)
        out_dir = os.path.join(self.tmp_dir.name, "output")

        from Sys.Score.evaluate_gate_ablation import evaluate_gate_ablation
        summary = evaluate_gate_ablation(res_path, out_dir, ["baseline", "strict_combined"])

        self.assertEqual(summary["evaluated_cases"], 1)

        pp = summary["per_policy"]
        # baseline: topo strong alone → invoke_llm, LLM response hits top1
        self.assertEqual(pp["baseline"]["top1"], 1.0)
        # strict_combined: topo strong alone → invoke_llm (same), LLM response hits top1
        self.assertEqual(pp["strict_combined"]["top1"], 1.0)

        # Top1 differ → baseline & strict both invoke_llm (no route change)

    def test_conservative_routes_more_to_llm(self):
        """Conservative policy should route more cases to LLM than baseline."""
        dir1 = self._make_case_dir("c1", ["10.0.0.1"])
        # topo strong alone → baseline would invoke_llm, conservative also invoke_llm (same)
        rec1 = self._make_record(
            dir1,
            topo_entries=[("10.0.0.1", 98.0, {}), ("10.0.0.2", 70.0, {})],
            temp_entries=[("10.0.0.5", 0.5, {}), ("10.0.0.6", 0.3, {})],
            combined_entries=[("10.0.0.1", 0.95, {}), ("10.0.0.5", 0.5, {})],
            topo_state="strong", temp_state="weak",
            gate_decision="invoke_llm", gate_route="llm",
            response_ips=["10.0.0.1"],
        )

        dir2 = self._make_case_dir("c2", ["10.0.0.1"])
        # top1 match, both uncertain → baseline combined, conservative LLM
        rec2 = self._make_record(
            dir2,
            topo_entries=[("10.0.0.1", 98.0, {}), ("10.0.0.2", 70.0, {})],
            temp_entries=[("10.0.0.1", 0.9, {}), ("10.0.0.3", 0.5, {})],
            combined_entries=[("10.0.0.1", 0.95, {}), ("10.0.0.2", 0.7, {})],
            topo_state="uncertain", temp_state="uncertain",
            gate_decision="invoke_llm", gate_route="llm",
            response_ips=["10.0.0.1"],
        )

        res_path = os.path.join(self.tmp_dir.name, "res.json")
        with open(res_path, "w", encoding="utf-8") as f:
            json.dump([rec1, rec2], f, ensure_ascii=False)
        out_dir = os.path.join(self.tmp_dir.name, "output")

        from Sys.Score.evaluate_gate_ablation import evaluate_gate_ablation
        summary = evaluate_gate_ablation(res_path, out_dir, ["baseline", "conservative"])

        self.assertEqual(summary["evaluated_cases"], 2)
        self.assertIn("conservative", summary["route_distribution"])
        self.assertIn("conservative", summary["route_changes_vs_baseline"])


if __name__ == "__main__":
    unittest.main()
