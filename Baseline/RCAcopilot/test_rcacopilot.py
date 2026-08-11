from __future__ import annotations

import json
from pathlib import Path

from Baseline.RCAcopilot.rcacopilot import (
    CaseRecord,
    FallbackLLMClient,
    RCAcopilotConfig,
    RCAcopilotPipeline,
    evaluate_predictions,
    time_aware_similarity,
)


def _case(case_id: str, ip: str, timestamp: int, text: str) -> CaseRecord:
    return CaseRecord(
        case_id=case_id,
        alarm_time_ms=timestamp,
        info={"alarm_time": timestamp, "alarm_description": text},
        nodes=[
            {
                "mgmt_ip": ip,
                "role": "LEAF",
                "alarms": [{"name": "linkDown", "alarm_time": timestamp}],
                "linked_to": [],
                "linked_from": [],
                "cross": 1,
            }
        ],
        full_link={},
        ground_truth_ips=[ip],
        diagnostic_text=text,
    )


def test_time_similarity_is_bounded_and_deterministic():
    value = time_aware_similarity(1.0, 2.0, 0.3)
    assert 0.0 < value < 1.0
    assert value == time_aware_similarity(1.0, 2.0, 0.3)


def test_pipeline_smoke_writes_topk_and_latency(tmp_path: Path):
    cases = [
        _case("a", "10.0.0.1", 1000, "link down on device 10.0.0.1"),
        _case("b", "10.0.0.2", 2000, "bgp peer down on device 10.0.0.2"),
        _case("c", "10.0.0.3", 3000, "link down on device 10.0.0.3"),
        _case("d", "10.0.0.4", 4000, "route withdrawn on device 10.0.0.4"),
    ]
    pipeline = RCAcopilotPipeline(
        RCAcopilotConfig(test_ratio=0.25, seed=42), FallbackLLMClient()
    )
    result = pipeline.run(cases, tmp_path)
    assert result["metrics"]["evaluated_cases"] == 1
    assert 0.0 <= result["metrics"]["top1"] <= 1.0
    assert 0.0 <= result["metrics"]["top3"] <= 1.0
    assert 0.0 <= result["metrics"]["top5"] <= 1.0
    assert result["metrics"]["latency_seconds"]["mean"] >= 0.0
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "records.json").exists()
    assert json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))["metrics"]


def test_evaluation_uses_any_ground_truth_ip_for_topk():
    metrics = evaluate_predictions(
        [
            {
                "ground_truth_ips": ["10.0.0.2", "10.0.0.9"],
                "predicted_ips": ["10.0.0.1", "10.0.0.9"],
                "latency_seconds": 0.5,
            }
        ]
    )
    assert metrics["top1"] == 0.0
    assert metrics["top3"] == 1.0
