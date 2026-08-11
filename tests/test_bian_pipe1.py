import json
from pathlib import Path

from Baseline.BiAn.bian_pipe1 import (
    BiAnPipe1Analyzer,
    MockBackend,
    find_case_dirs,
    select_candidates,
)


def test_select_candidates_prefers_explicit_list_and_never_needs_labels():
    nodes = [
        {"mgmt_ip": "10.0.0.1", "alarms": [{"name": "a"}], "logs": []},
        {"mgmt_ip": "10.0.0.2", "alarms": [{"name": "a"}, {"name": "b"}], "logs": []},
    ]
    selected = select_candidates(nodes, {"candidate_devices": ["10.0.0.1"]}, 6)
    assert [node["mgmt_ip"] for node in selected] == ["10.0.0.1"]


def test_pipe1_records_stage_and_inference_time(tmp_path: Path):
    case_dir = tmp_path / "case-1"
    case_dir.mkdir()
    (case_dir / "info.json").write_text(
        json.dumps({"alarm_name": "test", "label": [{"should_not": "be used"}]}),
        encoding="utf-8",
    )
    (case_dir / "label.json").write_text(
        json.dumps([{ "abnormal_node": [{"ip": "10.0.0.2"}] }]),
        encoding="utf-8",
    )
    (case_dir / "nodes.json").write_text(
        json.dumps(
            {
                "a": {
                    "mgmt_ip": "10.0.0.1",
                    "alarms": [{"name": "linkDown"}],
                    "logs": [],
                },
                "b": {
                    "mgmt_ip": "10.0.0.2",
                    "alarms": [{"name": "linkDown"}, {"name": "bgpDown"}],
                    "logs": [],
                },
            }
        ),
        encoding="utf-8",
    )

    cases = find_case_dirs(tmp_path)
    assert cases == [case_dir]

    analyzer = BiAnPipe1Analyzer(MockBackend(), max_candidates=6)
    results, summary = analyzer.process_cases(cases)

    assert len(results) == 1
    result = results[0]
    assert result["method"] == "BiAn-Pipeline1-32B"
    assert result["skill_ips"] == ["10.0.0.2", "10.0.0.1"]
    assert result["timing_s"]["num_candidates"] == 2
    assert result["timing_s"]["num_prompts"] == 5
    assert result["timing_s"]["num_batches"] == 3
    assert result["timing_s"]["end_to_end_s"] >= 0
    assert result["timing_s"]["llm_inference_s"] >= 0
    assert summary["cases"] == 1
    assert summary["mean_end_to_end_s"] >= 0
