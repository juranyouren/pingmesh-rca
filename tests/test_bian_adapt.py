"""UNIT CONTRACT TESTS ONLY: injected fake transport is not a model experiment.

These tests validate orchestration, provenance, isolation, and error accounting.
They do not reproduce BiAn model behavior or establish any RCA accuracy.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from Baseline.BiAnAdapt import BiAnAdapt, BiAnConfig
from Baseline.BiAnAdapt.__main__ import public_synthetic_incident
from Baseline.BiAnAdapt.backend import BackendFailure, validate_local_url
from Baseline.BiAnAdapt.pipeline import (ANOMALY_SCENARIOS, aggregate_rank_of_ranks,
                                        select_top_p)
from Baseline.BiAnAdapt.structure import (BudgetExceeded, InputIneligible,
                                         build_timeline, observable_input,
                                         paper_topology_summary)


def fixture_case(device_count=8):
    value = public_synthetic_incident()
    value["case_id"] = "unit-contract-only"
    value["devices"] = [{"id": f"d{i}", "type": "switch"} for i in range(device_count)]
    value["physical_links"] = [{"u": f"d{i}", "v": f"d{i+1}", "evidence_ids": [f"p{i}"]}
                               for i in range(device_count - 1)]
    value["events"] = [
        {"event_id": f"e{i}", "device_id": f"d{i}", "event_type": "observed_alert",
         "event_time": "2026-01-01T00:01:00Z", "record_time": "2026-01-01T00:01:01Z",
         "source": "alarm", "message": "Synthetic unit-test observation.", "severity": "warning"}
        for i in range(max(0, device_count - 2))
    ]
    return value


def parse_request(request):
    user = request["messages"][1]["content"]
    stage = user.splitlines()[0].split("=", 1)[1]
    body = user.split("INPUT_JSON=", 1)[1].split("\nOUTPUT_SCHEMA=", 1)[0]
    return stage, json.loads(body)


class ContractTransport:
    """Intentionally fabricated valid JSON for unit tests; never a real backend."""

    def __init__(self, mutate=None):
        self.requests = []
        self.mutate = mutate

    def __call__(self, request, timeout):
        self.requests.append(copy.deepcopy(request))
        stage, body = parse_request(request)
        if stage == "pipeline1.monitor_summary":
            value = {"reports": [{"device_id": device["device_id"], "summary": "UNIT TEST summary",
                                   "evidence_ids": [e["event_id"] for e in device["events"]]}
                                  for device in body["devices"]]}
        elif stage.startswith("pipeline1.anomaly."):
            value = {"reports": [{"device_id": device["device_id"], "summary": "UNIT TEST unknown assessment",
                                   "assessment": "unknown",
                                   "evidence_ids": sorted({e for row in device["source_summaries"] for e in row["evidence_ids"]})}
                                  for device in body["devices"]]}
        elif stage == "pipeline2.topology":
            evidence = sorted({e for rows in body["device_analyses"].values() for row in rows for e in row["evidence_ids"]})
            value = {"summary": "UNIT TEST spatial summary", "evidence_ids": evidence}
        elif stage == "pipeline3.timeline":
            value = {"summary": "UNIT TEST timeline summary", "evidence_ids": [row["event_id"] for row in body["events"]]}
        else:
            ids = list(body["candidate_device_ids"])
            # A third-round disagreement ensures tests exercise rank aggregation.
            if stage.endswith("round_3") and len(ids) > 1:
                ids[0], ids[1] = ids[1], ids[0]
            denominator = len(ids) * (len(ids) + 1) / 2
            value = {"ranking": [{"device_id": did, "failure_score": (len(ids) - i) / denominator,
                                   "summary": "UNIT TEST fabricated score", "evidence_ids": []}
                                  for i, did in enumerate(ids)]}
        if self.mutate:
            value = self.mutate(stage, value, len(self.requests))
        return {"id": "unit-test-fake-envelope", "model": "unit-contract-transport",
                "choices": [{"message": {"content": json.dumps(value),
                                            "reasoning_content": "PRIVATE_FIELD_MUST_NOT_PERSIST"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}


def unit_config(**overrides):
    return replace(BiAnConfig(), candidate_top_p=1.0, retries=0, **overrides)


def test_all_candidates_three_pipelines_and_three_rank_rounds():
    transport = ContractTransport()
    result = BiAnAdapt(unit_config(), transport).predict_root(fixture_case())
    assert result["status"] == "ok", result["diagnostics"].get("failure")
    assert len(result["root_ranking"]) == 8
    assert {row["device_id"] for row in result["root_ranking"]} == {f"d{i}" for i in range(8)}
    diagnostics = result["diagnostics"]
    assert len(diagnostics["initial_ranking"]) == 8
    assert all(len(rows) == 7 for rows in diagnostics["device_analyses"].values())
    assert len(diagnostics["joint_rounds"]) == 3
    stages = [parse_request(request)[0] for request in transport.requests]
    assert "pipeline2.topology" in stages and "pipeline3.timeline" in stages
    assert all("pipeline1.anomaly." + name in stages for name in ANOMALY_SCENARIOS)
    assert result["root_ranking"] == aggregate_rank_of_ranks(diagnostics["joint_rounds"], diagnostics["initial_ranking"])
    assert result["native_graph"] is None and result["device_graph"] is None
    assert diagnostics["token_usage"]["reported_totals"]["total_tokens"] == 30 * len(transport.requests)
    assert "PRIVATE_FIELD_MUST_NOT_PERSIST" not in json.dumps(result)


def test_prompt_projection_ignores_extra_labels_at_every_level():
    clean = fixture_case()
    dirty = copy.deepcopy(clean)
    sentinel = "TEST_LABEL_SECRET_NEVER_SEND"
    dirty.update(root_device=sentinel, labels={"positive_nodes": [sentinel]}, precomputed_scores=sentinel)
    dirty["window"]["root"] = sentinel
    dirty["endpoint_context"]["groud_truth"] = sentinel
    dirty["observation_coverage"] = {"root": sentinel}
    for row in dirty["devices"] + dirty["physical_links"] + dirty["events"]:
        row.update(score=sentinel, root_cause=sentinel, labels={"root": sentinel})
    first, second = ContractTransport(), ContractTransport()
    result_a = BiAnAdapt(unit_config(), first).predict_root(clean)
    result_b = BiAnAdapt(unit_config(), second).predict_root(dirty)
    assert result_a["status"] == result_b["status"] == "ok"
    assert first.requests == second.requests
    assert sentinel not in json.dumps(second.requests)
    assert result_a["root_ranking"] == result_b["root_ranking"]
    assert result_a["diagnostics"]["input_sha256"] == result_b["diagnostics"]["input_sha256"]


def test_endpoint_scalar_lists_preserved_nested_unknown_removed():
    case = fixture_case()
    case["endpoint_context"] = {"source_ip": ["192.0.2.1", {"root": "SECRET"}],
                                "sink_ip": ["192.0.2.2"], "source_az": ["az-a"],
                                "alarm_name": "probe_loss", "labels": {"root": "SECRET"}}
    safe = observable_input(case, 1000)
    assert safe["endpoint_context"] == {"source_ip": ["192.0.2.1"], "sink_ip": ["192.0.2.2"],
                                         "source_az": ["az-a"], "alarm_name": "probe_loss"}


@pytest.mark.parametrize("change", ["missing_window", "future_event", "future_record", "past_event", "bad_cutoff"])
def test_invalid_window_and_future_observations_rejected_before_model(change):
    case = fixture_case()
    if change == "missing_window":
        case.pop("window")
    elif change == "future_event":
        case["events"][0]["event_time"] = "2026-01-01T00:06:00Z"
    elif change == "future_record":
        case["events"][0]["record_time"] = "2026-01-01T00:06:00Z"
    elif change == "past_event":
        case["events"][0]["event_time"] = "2025-12-31T23:59:00Z"
    else:
        case["window"]["cutoff"] = "2026-01-01T00:06:00Z"
    transport = ContractTransport()
    result = BiAnAdapt(unit_config(), transport).predict_root(case)
    assert result["status"] == "input_ineligible"
    assert result["root_ranking"] == [] and not transport.requests


def test_all_unknown_and_simultaneous_event_times_are_not_fabricated():
    events = fixture_case(5)["events"]
    events[2]["event_time"] = None
    timeline = build_timeline(events, "UTC")
    assert timeline["simultaneous_groups"] == [["e0", "e1"]]
    assert timeline["unknown_event_time_ids"] == ["e2"]
    assert timeline["record_time_only_ids"] == ["e2"]
    assert timeline["events"][-1]["event_epoch_seconds"] is None


def test_uniform_event_budget_retains_all_devices_and_records_every_omission():
    case = fixture_case(4)
    extra = copy.deepcopy(case["events"][0])
    extra.update(event_id="extra", event_time="2026-01-01T00:02:00Z")
    case["events"].append(extra)
    result = BiAnAdapt(unit_config(max_events_per_device=1), ContractTransport()).predict_root(case)
    assert result["status"] == "ok"
    assert result["diagnostics"]["evidence_budget"]["omitted_event_ids_by_device"] == {"d0": ["extra"]}
    assert len(result["root_ranking"]) == 4
    assert "extra" not in {e["event_id"] for e in result["diagnostics"]["global_timeline"]["events"]}


def test_invalid_evidence_fails_without_ranking_fallback():
    def corrupt(stage, value, count):
        if count == 1:
            value["reports"][0]["evidence_ids"] = ["invented-event"]
        return value
    result = BiAnAdapt(unit_config(), ContractTransport(corrupt)).predict_root(fixture_case())
    assert result["status"] == "runtime_failure" and result["root_ranking"] == []
    assert "unknown or invalid event evidence" in result["diagnostics"]["failure"]["reason"]
    assert result["diagnostics"]["calls"][0]["raw_output"]


def test_invalid_late_joint_round_cannot_be_dropped_for_success():
    def corrupt(stage, value, count):
        if stage.endswith("round_3"):
            value["ranking"].pop()
        return value
    result = BiAnAdapt(unit_config(), ContractTransport(corrupt)).predict_root(fixture_case())
    assert result["status"] == "runtime_failure" and result["root_ranking"] == []
    assert result["diagnostics"]["initial_ranking"]
    assert result["diagnostics"]["calls"][-1]["stage"].endswith("round_3")


def test_retry_is_explicit_and_preserves_invalid_raw_output():
    def corrupt(stage, value, count):
        if count == 1:
            value["reports"].pop()
        return value
    config = replace(unit_config(), retries=1)
    result = BiAnAdapt(config, ContractTransport(corrupt)).predict_root(fixture_case(3))
    assert result["status"] == "ok"
    calls = result["diagnostics"]["calls"]
    assert calls[0]["status"] == "runtime_failure" and calls[1]["attempt"] == 1
    assert calls[0]["raw_output"] and "FORMAT_RETRY" in calls[1]["request"]["messages"][1]["content"]


def test_backend_failure_is_saved_and_has_no_heuristic_fallback():
    def unavailable(request, timeout):
        raise BackendFailure("local model backend unavailable or timed out")
    result = BiAnAdapt(unit_config(), unavailable).predict_root(fixture_case())
    assert result["status"] == "runtime_failure"
    assert result["root_ranking"] == []
    assert result["case_id"] == "unit-contract-only"
    assert result["timing"]["call_count"] == 1


def test_untrusted_transport_exception_does_not_leak_api_key(monkeypatch):
    monkeypatch.setenv("BIAN_API_KEY", "SECRET-API-KEY")
    def unavailable(request, timeout):
        raise RuntimeError("SECRET-API-KEY")
    result = BiAnAdapt(unit_config(), unavailable).predict_root(fixture_case())
    assert "SECRET-API-KEY" not in json.dumps(result)
    assert result["status"] == "runtime_failure"


def test_prompt_and_call_budget_fail_instead_of_candidate_truncation():
    result = BiAnAdapt(unit_config(max_prompt_chars=100), ContractTransport()).predict_root(fixture_case())
    assert result["status"] == "runtime_failure" and result["timing"]["call_count"] == 0
    result = BiAnAdapt(unit_config(max_calls_per_case=1), ContractTransport()).predict_root(fixture_case())
    assert result["status"] == "runtime_failure" and result["timing"]["call_count"] == 1
    assert not result["root_ranking"]


def test_top_p_softmax_and_excluded_initial_tail_are_recomputable():
    initial = [{"device_id": "a", "failure_score": 0.8}, {"device_id": "b", "failure_score": 0.15},
               {"device_id": "c", "failure_score": 0.05}]
    selection = select_top_p(initial, 0.45)
    assert selection["selected_device_ids"] == ["a"]
    assert selection["excluded_device_ids"] == ["b", "c"]
    assert sum(selection["softmax_masses"].values()) == pytest.approx(1)
    aggregate = aggregate_rank_of_ranks([[{"device_id": "a", "failure_score": 1}]] * 3, initial)
    assert [r["device_id"] for r in aggregate] == ["a", "b", "c"]
    assert [r["score"] for r in aggregate] == [-1, -2, -3]
    assert aggregate[-1]["stage"] == "retained_initial_tail"


def test_rank_of_ranks_uses_mean_rank_not_mean_score_with_average_ties():
    initial = [{"device_id": "a", "failure_score": 0.6}, {"device_id": "b", "failure_score": 0.4}]
    rounds = [[{"device_id": "a", "failure_score": a}, {"device_id": "b", "failure_score": b}]
              for a, b in [(0.51, 0.49), (0.51, 0.49), (0.01, 0.99)]]
    result = aggregate_rank_of_ranks(rounds, initial)
    assert result[0]["device_id"] == "a"
    assert result[0]["average_rank"] == pytest.approx(4 / 3)
    tie = aggregate_rank_of_ranks([[{"device_id": "a", "failure_score": .5},
                                    {"device_id": "b", "failure_score": .5}]], initial)
    assert all(r["average_rank"] == 1.5 for r in tie)


def test_paper_topology_removes_internal_suspect_path_without_inventing_groups():
    case = fixture_case(4)
    value = paper_topology_summary(case["devices"], case["physical_links"], ["d0", "d1", "d3"])
    assert ["d0", "d1", "d2", "d3"] in value["removed_paths_with_internal_suspect"]
    assert ["d1", "d2", "d3"] in value["retained_shortest_paths"]
    assert len(value["physical_links"]) == 3
    assert value["group_aggregation"].startswith("disabled")


def test_topology_preserves_all_shortest_paths_and_fails_explicitly_on_budget():
    devices = [{"id": d} for d in "abcd"]
    links = [{"u": u, "v": v, "evidence_ids": [u + v]} for u, v in ("ab", "ac", "bd", "cd")]
    value = paper_topology_summary(devices, links, ["a", "d"])
    assert sorted(value["retained_shortest_paths"]) == [["a", "b", "d"], ["a", "c", "d"]]
    with pytest.raises(BudgetExceeded):
        paper_topology_summary(devices, links, ["a", "d"], path_budget=1)


@pytest.mark.parametrize("url", ["https://api.openai.com/v1", "http://10.10.1.226:8000/v1",
                                  "http://user:secret@127.0.0.1:8000/v1", "http://127.0.0.1/v1?key=secret"])
def test_nonlocal_or_credential_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_local_url(url)


def test_single_round_has_distinct_ablation_identity():
    result = BiAnAdapt(unit_config(joint_rounds=1), ContractTransport()).predict_root(fixture_case(3))
    assert result["status"] == "ok"
    assert result["method"].endswith("single-round-ablation")
    assert len(result["diagnostics"]["joint_rounds"]) == 1


def test_no_observations_is_ineligible_and_never_guesses_a_ranking():
    case = fixture_case(3)
    case["events"] = []
    transport = ContractTransport()
    result = BiAnAdapt(unit_config(), transport).predict_root(case)
    assert result["status"] == "input_ineligible"
    assert result["root_ranking"] == []
    assert result["diagnostics"]["candidate_count"] == 3
    assert not transport.requests
