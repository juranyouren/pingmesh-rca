import json

import pytest

from Sys_v1.RootCauseAnalyze.gate import evidence
from Sys_v1.RootCauseAnalyze.gate.evidence import (
    build_fused_evidence,
    build_neighbor_alarm_context,
)
from Sys_v1.RootCauseAnalyze.skills import topo_ranker


def _node(ip, *, alarms=None, upstream=None, downstream=None, cross=0):
    return {
        "mgmt_ip": ip,
        "role": "leaf",
        "cross": cross,
        "alarms": alarms or [],
        "logs": [],
        "linked_from": upstream or [],
        "linked_to": downstream or [],
    }


def test_neighbor_context_keeps_highest_weight_alarm_per_neighbor():
    target = _node("A", downstream=["B", "C"])
    nodes = {
        "A": target,
        "B": _node(
            "B",
            alarms=[{"alarm_name": "low"}, {"alarm_name": "critical"}],
            upstream=["A"],
        ),
        "C": _node("C", alarms=[{"alarm_name": "medium"}], upstream=["A"]),
    }
    context = build_neighbor_alarm_context(
        target,
        nodes,
        {"low": 1, "critical": 100, "medium": 20},
        mode="highest_weight",
        max_neighbor_devices=8,
        max_neighbor_alarms=3,
    )

    assert [row["neighbor_ip"] for row in context] == ["B", "C"]
    assert context[0]["selected_alarms"] == [{"name": "critical", "weight": 100}]
    assert context[0]["relation"] == "downstream"
    assert len(context[0]["selected_alarms"]) == 1


def test_neighbor_context_all_mode_is_bounded():
    target = _node("A", downstream=["B", "C"])
    nodes = {
        "A": target,
        "B": _node("B", alarms=["a", "b", "c"]),
        "C": _node("C", alarms=["d"]),
    }
    context = build_neighbor_alarm_context(
        target,
        nodes,
        {"a": 1, "b": 3, "c": 2, "d": 4},
        mode="all",
        max_neighbor_devices=1,
        max_neighbor_alarms=2,
    )

    assert len(context) == 1
    assert context[0]["neighbor_ip"] == "C"
    assert len(context[0]["selected_alarms"]) <= 2


def test_m2_m3_collects_evidence_for_all_devices_even_when_top_k_is_one():
    nodes = [
        _node("A", alarms=[{"alarm_name": "a", "alarm_time": 1000}], downstream=["B"]),
        _node("B", alarms=[{"alarm_name": "b", "alarm_time": 1100}], upstream=["A"]),
        _node("C", alarms=[{"alarm_name": "c", "alarm_time": 1200}]),
    ]
    skill_ret, _info, detail, _raw, ranked_ips = build_fused_evidence(
        nodes,
        {"alarm_time": 1000},
        "",
        top_k=1,
        skill_ids=(2,),
        candidate_strategy="all_devices",
        enable_m2=True,
    )
    table = json.loads(skill_ret)
    devices = json.loads(detail)["devices"]

    assert "topo" not in table
    assert len(ranked_ips) == 3
    assert {device["ip"] for device in devices} == {"A", "B", "C"}
    assert "adjacent_alarm_context" in devices[0]


def test_m1_does_not_collect_alarm_evidence_or_load_alarm_weights(monkeypatch):
    nodes = [
        _node("A", alarms=[{"alarm_name": "critical"}], downstream=["B"], cross=2),
        _node("B", alarms=[{"alarm_name": "peer"}], upstream=["A"]),
    ]
    monkeypatch.setattr(
        evidence,
        "load_alarm_weights",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("M2 leaked into M1")),
    )

    _skill_ret, _info, detail, raw, _ranked = build_fused_evidence(
        nodes,
        {},
        "",
        top_k=2,
        skill_ids=(1,),
        candidate_strategy="topology_top_k",
        enable_m2=False,
    )
    devices = json.loads(detail)["devices"]

    assert raw == "{}"
    assert all("alarms" not in device for device in devices)
    assert all("adjacent_alarm_context" not in device for device in devices)


def test_full_pipeline_fuses_topology_and_temporal_with_strict_mean(monkeypatch):
    nodes = [_node("A"), _node("B"), _node("C")]

    monkeypatch.setattr(evidence, "score_topo", lambda *args, **kwargs: {"A": 1.0, "B": 0.4, "C": 0.1})
    monkeypatch.setattr(
        evidence,
        "topo_details",
        lambda *args, **kwargs: {
            "topk": [
                {"rank": 1, "ip": "A", "pr_score": 1.0},
                {"rank": 2, "ip": "B", "pr_score": 0.4},
            ],
            "diagnostics": {},
            "trust_tree": {},
        },
    )

    def fake_temporal(selected_nodes, *args, **kwargs):
        assert [node["mgmt_ip"] for node in selected_nodes] == ["A", "B"]
        return {"A": 0.2, "B": 0.8}

    monkeypatch.setattr(evidence, "score_temporal", fake_temporal)
    monkeypatch.setattr(
        evidence,
        "temporal_details",
        lambda *args, **kwargs: {
            "topk": [],
            "diagnostics": {},
            "trust_tree": {},
        },
    )

    ranked, details = evidence._build_rankings(
        nodes,
        {},
        "",
        skill_ids=(1, 2),
        candidate_strategy="topology_top_k",
        weight_dirpath=None,
        top_k=2,
    )

    assert ranked == ["A", "B"]
    assert details["combined"]["fusion"] == "arithmetic_mean"
    assert [row["combined_score"] for row in details["combined"]["topk"]] == [0.6, 0.6]


def test_topology_score_is_independent_of_alarm_content():
    base = [
        _node("A", downstream=["B"], cross=2),
        _node("B", upstream=["A"], downstream=["C"]),
        _node("C", upstream=["B"]),
    ]
    changed = [dict(node) for node in base]
    changed[2] = dict(changed[2], alarms=[{"alarm_name": "critical"}] * 50)

    if topo_ranker.nx is None:
        detail_a = topo_ranker.topo_details(
            base, {}, {}, weight_path=None, directed=True, top_k=3
        )
        detail_b = topo_ranker.topo_details(
            changed, {}, {}, weight_path=None, directed=True, top_k=3
        )
        score_a = {row["ip"]: row["pr_score"] for row in detail_a["rankings"]}
        score_b = {row["ip"]: row["pr_score"] for row in detail_b["rankings"]}
    else:
        score_a = topo_ranker.score_topo(base, {})
        score_b = topo_ranker.score_topo(changed, {})

    assert score_a == pytest.approx(score_b)
