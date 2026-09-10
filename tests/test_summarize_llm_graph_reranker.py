import json

import pytest

from Sys.Score import summarize_llm_graph_reranker as summary


def baseline(path, ranking="ABCDEFG"):
    return {summary._normalized_path(path): {"dir": path, "ranked_ips": list(ranking)}}


@pytest.mark.parametrize("inputs,root,expected", [("ABC", "D", 0.0), ("ABCDEFG", "F", 1.0), ("", "A", 0.0)])
def test_candidate_recall_uses_saved_top_k_not_final_or_baseline(monkeypatch, inputs, root, expected):
    monkeypatch.setattr(summary, "load_training_label", lambda path: root)
    record = {"dir": "case", "ranked_ips": [root],
              "initial_root_rankings": [{"ip": ip} for ip in inputs]}
    result = summary._evaluate([record], baseline("case"))
    assert result["top1"] == 100.0
    assert result["input_candidate_recall"] == expected
    assert result["input_candidate_recall_known_cases"] == 1
    assert result["input_candidate_recall_status"] == "available"


def test_actual_prompt_candidates_take_precedence(monkeypatch):
    monkeypatch.setattr(summary, "load_training_label", lambda path: "C")
    record = {"dir": "case", "ranked_ips": ["C"], "initial_root_rankings": [{"ip": ip} for ip in "ABC"]}
    audits = {summary._normalized_path("case"): [{"candidate_aliases": {"N1": "A", "N2": "B"}, "input_tokens": 10}]}
    result = summary._evaluate([record], baseline("case"), audits)
    assert result["input_candidate_recall"] == 0.0


def test_missing_input_candidates_are_unknown(monkeypatch):
    monkeypatch.setattr(summary, "load_training_label", lambda path: "A")
    record = {"dir": "case", "ranked_ips": ["A"]}
    result = summary._evaluate([record], baseline("case"))
    assert result["candidate_recall"] is None
    assert result["input_candidate_recall_known_cases"] == 0
    assert result["input_candidate_recall_unknown_cases"] == 1
    assert result["input_candidate_recall_status"] == "unavailable"


def test_partial_candidate_availability_has_its_own_denominator(monkeypatch):
    monkeypatch.setattr(summary, "load_training_label", lambda path: "A")
    records = [{"dir": "known", "initial_root_rankings": [{"ip": "A"}]}, {"dir": "unknown", "ranked_ips": ["A"]}]
    result = summary._evaluate(records, {**baseline("known"), **baseline("unknown")})
    assert result["input_candidate_recall"] == 1.0
    assert result["input_candidate_recall_known_cases"] == 1
    assert result["input_candidate_recall_unknown_cases"] == 1
    assert result["input_candidate_recall_status"] == "partial"


def test_costs_include_unlabeled_and_audit_only_calls_without_double_counting(monkeypatch):
    monkeypatch.setattr(summary, "load_training_label", lambda path: "A" if path == "labeled" else "")
    records = [{"dir": "labeled", "ranked_ips": ["A"], "llm_reranking": {"input_tokens": 999}},
               {"dir": "unlabeled", "llm_reranking": {"input_tokens": 20}},
               {"dir": "fallback", "llm_reranking": {"input_tokens": 40}}]
    audits = {summary._normalized_path("labeled"): [{"input_tokens": 10}],
              summary._normalized_path("unlabeled"): [{"input_tokens": 20}],
              summary._normalized_path("audit-only"): [{"input_tokens": 30}]}
    result = summary._evaluate(records, {**baseline("labeled"), **baseline("unlabeled"), **baseline("fallback")}, audits)
    assert result["cases"] == 1
    assert result["llm_calls"] == 4
    assert result["total_input_tokens"] == 100


def test_unknown_audit_tokens_are_flagged_instead_of_claiming_zero_cost(monkeypatch):
    monkeypatch.setattr(summary, "load_training_label", lambda path: "")
    audits = {summary._normalized_path("unlabeled"): [{"input_tokens": None}, {"input_tokens": 25}]}
    result = summary._evaluate([], {}, audits)
    assert result["llm_calls"] == 2
    assert result["total_input_tokens"] == 25
    assert result["calls_missing_input_tokens"] == 1
    assert result["input_token_total_status"] == "partial"


def test_inconsistent_saved_call_candidates_are_rejected(monkeypatch):
    monkeypatch.setattr(summary, "load_training_label", lambda path: "A")
    audits = {summary._normalized_path("case"): [{"candidate_aliases": {"N1": "A"}}, {"candidate_aliases": {"N1": "B"}}]}
    with pytest.raises(ValueError, match="candidate sets differ"):
        summary._evaluate([{"dir": "case"}], baseline("case"), audits)


def test_consensus_includes_direct_and_repeat_costs_for_unlabeled_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(summary, "load_training_label", lambda path: "A" if path == "labeled" else "")
    direct = tmp_path / "llm_prior_evidence_graph"
    consensus = tmp_path / summary.CONSENSUS_METHOD
    direct.mkdir()
    consensus.mkdir()
    (direct / "llm_audit.json").write_text(json.dumps([
        {"dir": "labeled", "input_tokens": 10}, {"dir": "unlabeled", "input_tokens": 20}
    ]), encoding="utf-8")
    (consensus / "llm_audit.json").write_text(json.dumps({
        "cases": [], "repeat_calls": [{"dir": "unlabeled", "input_tokens": 30}]
    }), encoding="utf-8")
    audits = summary._load_audit(str(tmp_path), summary.CONSENSUS_METHOD)
    records = [{"dir": "labeled", "ranked_ips": ["A"]}, {"dir": "unlabeled"}]
    result = summary._evaluate(records, {**baseline("labeled"), **baseline("unlabeled")}, audits)
    assert result["cases"] == 1
    assert result["llm_calls"] == 3
    assert result["total_input_tokens"] == 60
