from __future__ import annotations

import os
import tempfile

from Sys.Score.evaluate_gate_recall import evaluate_gate_recall


def _tree_details(top_ip: str, second_ip: str, *, temporal: bool):
    if temporal:
        return {
            "topk": [
                {"ip": top_ip, "score": 0.9},
                {"ip": second_ip, "score": 0.5},
            ],
            "trust_tree": {
                "state": "strong",
                "passed": [],
                "failed": [],
                "evidence": {
                    "ref_time_ms": 123,
                    "devices_with_timestamps": 3,
                    "top_event_count": 2,
                    "burst_top3": [top_ip, second_ip],
                    "early_top3": [top_ip, second_ip],
                },
            },
        }
    return {
        "topk": [
            {"ip": top_ip, "pr_score": 0.95},
            {"ip": second_ip, "pr_score": 0.5},
        ],
        "trust_tree": {
            "state": "strong",
            "passed": [],
            "failed": [],
            "evidence": {
                "directed_top3": [top_ip, second_ip],
                "undirected_top3": [top_ip, second_ip],
                "top_entry": {"ip": top_ip, "high_weight_alarm_hit": True},
            },
        },
    }


def _record(case_id: str, gt_ip: str, combined_top: str, topo_top: str, temporal_top: str):
    second = "10.0.0.99"
    return {
        "dir": f"/cases/{case_id}",
        "gt_ips": [gt_ip],
        "skill_ips": [combined_top, second],
        "skill_details": {
            "combined": {
                "topk": [
                    {"ip": combined_top, "combined_score": 0.9},
                    {"ip": second, "combined_score": 0.5},
                ]
            },
            "1": _tree_details(topo_top, second, temporal=False),
            "2": _tree_details(temporal_top, second, temporal=True),
        },
    }


def test_gate_recall_catches_deterministic_error_and_preserves_safe_bypass():
    records = [
        _record("safe", "10.0.0.1", "10.0.0.1", "10.0.0.1", "10.0.0.1"),
        _record("caught", "10.0.0.8", "10.0.0.9", "10.0.0.9", "10.0.0.8"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        summary = evaluate_gate_recall(records, out_dir=tmp, target_k=1)

        target = summary["target"]
        assert target["deterministic_error_cases"] == 1
        assert target["caught_error_cases"] == 1
        assert target["error_recall"] == 1.0
        assert target["unsafe_bypass_count"] == 0
        assert target["bypass_precision"] == 1.0
        assert summary["safety_target_passed"] is True
        assert os.path.exists(os.path.join(tmp, "gate_recall_cases.jsonl"))
        assert os.path.exists(os.path.join(tmp, "gate_recall_summary.json"))
        assert os.path.exists(os.path.join(tmp, "gate_recall_by_reason.csv"))


def test_gate_recall_reports_unanimous_but_wrong_bypass_as_unsafe():
    records = [
        _record("unsafe", "10.0.0.8", "10.0.0.9", "10.0.0.9", "10.0.0.9")
    ]
    with tempfile.TemporaryDirectory() as tmp:
        summary = evaluate_gate_recall(records, out_dir=tmp, target_k=1)

        assert summary["target"]["unsafe_bypass_count"] == 1
        assert summary["target"]["error_recall"] == 0.0
        assert summary["safety_target_passed"] is False
