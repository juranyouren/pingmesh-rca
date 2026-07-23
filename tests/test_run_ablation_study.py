import json

from scripts.run_ablation_study import (
    _prompt_version,
    _project_evidence_row,
    _summarize_token_usage,
    _write_all_llm_evaluation_artifacts,
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


def test_all_llm_modes_force_every_gate_route_and_use_distinct_prompts(tmp_path):
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

    rerank = build_case_plan(
        mode="m123_all_llm_rerank",
        dirpath=str(case_dir),
        data_root=str(tmp_path),
        evidence_table=_table(),
        evidence_average_seconds=2.5,
        top_k=2,
        weight_file=None,
    )
    evidence = build_case_plan(
        mode="m123_all_llm_evidence",
        dirpath=str(case_dir),
        data_root=str(tmp_path),
        evidence_table=_table(),
        evidence_average_seconds=2.5,
        top_k=2,
        weight_file=None,
    )

    for plan in (rerank, evidence):
        assert plan["pipeline_mode"] == "m123"
        assert plan["gate"]["forced_llm"] is True
        assert plan["gate"]["decision"] == "invoke_llm"
        assert plan["gate"]["natural_decision"] in {"invoke_llm", "bypass_llm"}
        assert plan["evidence_device_count"] == 2
        assert plan["runtime"]["evidence_estimated_seconds"] == 5.0

    assert rerank["prompt_variant"] == "rerank"
    assert '"initial_ranking"' in rerank["prompt"]
    assert "Gate 上下文" in rerank["prompt"]
    assert evidence["prompt_variant"] == "evidence_judge"
    assert '"initial_ranking"' not in evidence["prompt"]
    assert '"combined_score"' not in evidence["prompt"]
    assert "raw_temporal_score_i / max(raw_temporal_score)" in evidence["prompt"]
    assert "Gate 上下文" not in evidence["prompt"]
    assert _prompt_version(rerank["mode"]) != _prompt_version(evidence["mode"])


def test_token_usage_summary_keeps_each_prompt_count():
    summary = _summarize_token_usage(
        [
            {
                "case_id": "b",
                "prompt_variant": "rerank",
                "reran_with_llm": True,
                "token_usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 10,
                    "total_tokens": 40,
                    "source": "vllm_token_ids",
                },
            },
            {
                "case_id": "a",
                "prompt_variant": "rerank",
                "reran_with_llm": True,
                "token_usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 5,
                    "total_tokens": 25,
                    "source": "vllm_token_ids",
                },
            },
        ]
    )

    assert [row["case_id"] for row in summary["per_case"]] == ["a", "b"]
    assert summary["prompt_tokens"] == {
        "total": 50,
        "average_per_llm_case": 25.0,
    }
    assert summary["total_tokens"]["total"] == 65


def test_all_llm_badcase_writes_detailed_folder(tmp_path):
    case_dir = tmp_path / "source_case"
    case_dir.mkdir()
    (case_dir / "label_v2.json").write_text(
        json.dumps({"primary_root_cause": {"ip": "10.0.0.2"}}),
        encoding="utf-8",
    )
    evidence_root = tmp_path / "evidence"
    evidence_path = evidence_root / "cases" / "case-a" / "evidence_table.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text(json.dumps(_table()), encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    plans = [
        {
            "case_id": "case-a",
            "dir": str(case_dir),
            "initial_ranking": ["10.0.0.1", "10.0.0.2"],
            "initial_rows": [{"rank": 1, "ip": "10.0.0.1"}],
            "topo_detail": {"rankings": [{"ip": "10.0.0.1"}]},
            "temporal_detail": {"rankings": [{"ip": "10.0.0.2"}]},
            "gate": {
                "confidence": "high",
                "decision": "invoke_llm",
                "natural_decision": "bypass_llm",
                "forced_llm": True,
            },
        }
    ]
    results = [
        {
            "case_id": "case-a",
            "dir": str(case_dir),
            "prompt_variant": "evidence_judge",
            "prompt_version": "v1",
            "prompt": "actual prompt",
            "llm_raw_response": '{"ip":["10.0.0.1"]}',
            "llm_output_filter": {
                "parse_success": True,
                "parsed_payload": {"ip": ["10.0.0.1"]},
                "used_initial_ranking_fallback": False,
            },
            "response": '```json\n{"ip":["10.0.0.1"]}\n```',
            "token_usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "source": "vllm_token_ids",
            },
            "runtime": {"llm_effective_wall_seconds": 1.0},
        }
    ]

    summary = _write_all_llm_evaluation_artifacts(
        mode="m123_all_llm_evidence",
        plans=plans,
        results=results,
        run_dir=run_dir,
        evidence_root=evidence_root,
    )

    badcase_dir = run_dir / "badcases" / "case-a"
    assert summary["badcase_count"] == 1
    assert summary["transition_matrix"]["wrong_to_wrong"] == 1
    assert (run_dir / "cases.jsonl").exists()
    assert (run_dir / "transition_matrix.json").exists()
    assert (run_dir / "badcase_index.csv").exists()
    for name in (
        "00_overview.md",
        "01_evaluation.json",
        "02_gate.json",
        "03_rankings.json",
        "04_evidence_table.json",
        "05_prompt.txt",
        "06_llm_raw_output.txt",
        "07_llm_parsed_output.json",
        "08_rank_diff.json",
        "09_timing.json",
        "10_source_refs.json",
    ):
        assert (badcase_dir / name).exists()
