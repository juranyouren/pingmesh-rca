import json

import pytest

from Sys_v1.pipeline import PipelineSettings, build_case_plan, finalize_case_plan


@pytest.fixture
def synthetic_case(tmp_path):
    case_dir = tmp_path / "case-001"
    case_dir.mkdir()
    nodes = {
        "device-a": {
            "mgmt_ip": "10.0.0.1",
            "role": "SPINE",
            "linked_from": [],
            "linked_to": ["10.0.0.2"],
            "cross": 4,
            "alarms": [
                {"alarm_name": "link_down", "alarm_time": 900, "alarm_description": "port down"},
                {"alarm_name": "link_down", "alarm_time": 1000, "alarm_description": "port down"},
            ],
            "logs": [],
        },
        "device-b": {
            "mgmt_ip": "10.0.0.2",
            "role": "LEAF",
            "linked_from": ["10.0.0.1"],
            "linked_to": ["10.0.0.3"],
            "cross": 2,
            "alarms": [{"alarm_name": "peer_down", "alarm_time": 990}],
            "logs": [],
        },
        "device-c": {
            "mgmt_ip": "10.0.0.3",
            "role": "TOR",
            "linked_from": ["10.0.0.2"],
            "linked_to": [],
            "cross": 0,
            "alarms": [],
            "logs": [],
        },
    }
    (case_dir / "nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
    (case_dir / "info.json").write_text(
        json.dumps(
            {
                "alarm_time": 1000,
                "source_ip": '["10.0.0.1"]',
                "sink_ip": '["10.0.0.3"]',
            }
        ),
        encoding="utf-8",
    )
    # Inference must not need this file. It is intentionally malformed.
    (case_dir / "label.json").write_text("not-json", encoding="utf-8")
    return str(case_dir)


def test_four_ablation_contracts(synthetic_case):
    settings = PipelineSettings(top_k=3)

    m1 = build_case_plan(synthetic_case, "m1", settings)
    assert m1["topology"]["enabled"] is True
    assert m1["temporal"]["enabled"] is False
    assert m1["evidence_table"] == []
    assert m1["confidence_gate"]["enabled"] is False

    m1_m3 = build_case_plan(synthetic_case, "m1_m3", settings)
    assert m1_m3["fusion"]["sources_used"] == ["topology"]
    assert m1_m3["temporal"]["enabled"] is False
    assert m1_m3["evidence_table"] == []
    assert m1_m3["confidence_gate"]["enabled"] is True

    m2_m3 = build_case_plan(synthetic_case, "m2_m3", settings)
    assert m2_m3["topology"]["enabled"] is False
    assert m2_m3["candidate_scope"] == "all_devices"
    assert m2_m3["candidate_count"] == 3
    assert len(m2_m3["evidence_table"]) == 3
    assert m2_m3["fusion"]["sources_used"] == ["temporal"]

    full = build_case_plan(synthetic_case, "m123", settings)
    assert full["topology"]["enabled"] is True
    assert full["temporal"]["enabled"] is True
    assert full["fusion"]["sources_used"] == ["topology", "temporal"]
    assert full["fusion"]["weights"] == {"topology": 0.5, "temporal": 0.5}


def test_dry_run_keeps_preliminary_ranking_when_llm_is_requested(synthetic_case):
    settings = PipelineSettings(top_k=3, single_source_accept_margin=2.0)
    plan = build_case_plan(synthetic_case, "m1_m3", settings)
    assert plan["confidence_gate"]["action"] == "llm_review"

    preliminary = [row["ip"] for row in plan["preliminary_ranking"]]
    final = finalize_case_plan(plan, settings=settings, llm_backend="none")

    assert final["final_ranking"] == preliminary[:3]
    assert final["final_decision"] == "llm_unavailable_keep_preliminary"
    assert final["llm"]["executed"] is False
