import json

from scripts.run_ablation_study import (
    _project_evidence_row,
    assess_ablation_gate,
    build_case_plan,
    build_evidence_ranking,
    constrain_llm_response,
)


def _table():
    return {
        "case_id": "case-a",
        "temporal_diagnostics": {"ref_time_ms": 1000},
        "rows": [
            {
                "candidate_ip": "10.0.0.1",
                "role": "LEAF",
                "cross": 2,
                "alarm_count": 1,
                "log_count": 0,
                "high_weight_alarms": ["A"],
                "semantic_summary": "目标设备出现 A 告警。",
                "topology": {"upstream": ["10.0.0.2"], "downstream": []},
                "temporal": {
                    "burst_score": 0.2,
                    "early_bird_score": 0.5,
                    "density_score": 0.1,
                    "raw_temporal_score": 0.2,
                    "timestamp_count": 1,
                },
            },
            {
                "candidate_ip": "10.0.0.2",
                "role": "SPINE",
                "cross": 1,
                "alarm_count": 2,
                "log_count": 0,
                "high_weight_alarms": ["B"],
                "semantic_summary": "目标设备及下游邻居出现 B 告警。",
                "topology": {"upstream": [], "downstream": ["10.0.0.1"]},
                "temporal": {
                    "burst_score": 1.0,
                    "early_bird_score": 1.0,
                    "density_score": 0.8,
                    "raw_temporal_score": 0.8,
                    "timestamp_count": 2,
                },
            },
        ],
    }


def test_evidence_ranking_reads_precomputed_table_values():
    scores, detail = build_evidence_ranking(
        _table(), ["10.0.0.1", "10.0.0.2"]
    )

    assert scores == {"10.0.0.1": 0.25, "10.0.0.2": 1.0}
    assert detail["rankings"][0]["ip"] == "10.0.0.2"
    assert detail["diagnostics"]["source"] == "precomputed_evidence_table"


def test_m13_high_confidence_bypasses_and_nonhigh_invokes():
    strong_topo = {
        "rankings": [
            {
                "ip": "10.0.0.1",
                "pr_score": 1.0,
                "cross": 1,
                "max_alarm_weight": 100,
                "high_weight_alarm_hit": True,
                "source_sink_related": False,
                "seed_type": "alarm_weight",
            },
            {"ip": "10.0.0.2", "pr_score": 0.1},
        ],
        "diagnostics": {
            "pagerank_available": True,
            "directed_top3": ["10.0.0.1", "10.0.0.2"],
            "undirected_top3": ["10.0.0.1", "10.0.0.2"],
        },
    }
    high = assess_ablation_gate(
        mode="m13",
        initial_ranking=["10.0.0.1", "10.0.0.2"],
        topo_detail=strong_topo,
        temporal_detail=None,
    )
    low = assess_ablation_gate(
        mode="m13",
        initial_ranking=["10.0.0.1"],
        topo_detail={"rankings": []},
        temporal_detail=None,
    )

    assert (high["confidence"], high["decision"]) == ("high", "bypass_llm")
    assert low["confidence"] in {"medium", "low"}
    assert low["decision"] == "invoke_llm"


def test_m23_view_excludes_explicit_topology_fields():
    row = _table()["rows"][0]
    projected = _project_evidence_row(row, "m23")

    assert "temporal" in projected
    assert "topology" not in projected
    assert "cross" not in projected


def test_m23_case_plan_uses_all_devices_and_cached_average(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    nodes = [
        {
            "mgmt_ip": "10.0.0.1",
            "role": "LEAF",
            "linked_from": ["10.0.0.2"],
            "linked_to": [],
            "alarms": [],
            "logs": [],
        },
        {
            "mgmt_ip": "10.0.0.2",
            "role": "SPINE",
            "linked_from": [],
            "linked_to": ["10.0.0.1"],
            "alarms": [],
            "logs": [],
        },
    ]
    (case_dir / "nodes.json").write_text(
        json.dumps(nodes, ensure_ascii=False), encoding="utf-8"
    )
    (case_dir / "info.json").write_text(
        json.dumps({"alarm_time": 1000}), encoding="utf-8"
    )

    plan = build_case_plan(
        mode="m23",
        dirpath=str(case_dir),
        data_root=str(tmp_path),
        evidence_table=_table(),
        evidence_average_seconds=2.5,
        top_k=1,
        weight_file=None,
    )

    assert plan["initial_ranking"][0] == "10.0.0.2"
    assert plan["evidence_device_count"] == 2
    assert plan["runtime"]["evidence_estimated_seconds"] == 5.0
    assert "topology" not in plan["evidence_rows_for_llm"][0]

    for mode, expected_devices, expected_seconds in (
        ("m1", 0, 0.0),
        ("m13", 1, 2.5),
        ("m123", 1, 2.5),
    ):
        other = build_case_plan(
            mode=mode,
            dirpath=str(case_dir),
            data_root=str(tmp_path),
            evidence_table=None if mode == "m1" else _table(),
            evidence_average_seconds=2.5,
            top_k=1,
            weight_file=None,
        )
        assert other["evidence_device_count"] == expected_devices
        assert other["runtime"]["evidence_estimated_seconds"] == expected_seconds


def test_llm_response_is_filtered_to_allowed_candidates():
    response, audit = constrain_llm_response(
        '```json\n{"decision":"adjust_ranking","reasoning":"x","ip":["10.0.0.2","9.9.9.9"]}\n```',
        ["10.0.0.1", "10.0.0.2"],
    )

    assert '"10.0.0.2"' in response
    assert "9.9.9.9" not in response
    assert audit["rejected_ips"] == ["9.9.9.9"]
    assert audit["output_was_filtered"] is True
