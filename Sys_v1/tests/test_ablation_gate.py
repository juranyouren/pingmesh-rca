import json

from Sys_v1.RootCauseAnalyze.ablation import get_ablation_spec
from Sys_v1.RootCauseAnalyze.gate.decision import assess_gate


def test_ablation_boundaries():
    m1 = get_ablation_spec("m1")
    m1_m3 = get_ablation_spec("m1_m3")
    m2_m3 = get_ablation_spec("m2_m3")
    full = get_ablation_spec("m123")

    assert m1.skill_ids == (1,) and not m1.enable_m2 and not m1.enable_llm
    assert m1_m3.skill_ids == (1,) and not m1_m3.enable_m2 and m1_m3.enable_gate
    assert m2_m3.skill_ids == (2,) and m2_m3.candidate_strategy == "all_devices"
    assert full.skill_ids == (1, 2) and full.enable_m2 and full.enable_llm


def test_single_topology_source_can_be_auto_accepted_when_strong():
    rows = [
        {
            "rank": 1,
            "ip": "A",
            "pr_score": 1.0,
            "cross": 5,
            "source_sink_related": True,
            "seed_type": "path_crossing",
        },
        {"rank": 2, "ip": "B", "pr_score": 0.2, "cross": 0, "seed_type": "baseline"},
    ]
    payload = {
        "topo": {
            "rankings": rows,
            "diagnostics": {
                "pagerank_available": True,
                "directed_top3": ["A", "B"],
                "undirected_top3": ["A", "B"],
            },
        },
        "combined_score_rankings": [
            {"rank": 1, "ip": "A", "combined_score": 1.0},
            {"rank": 2, "ip": "B", "combined_score": 0.2},
        ],
    }

    gate = assess_gate(json.dumps(payload))

    assert gate["decision"] == "bypass_llm"
    assert gate["route"] == "topo"
    assert gate["recommended_ips"][0] == "A"


def test_weak_single_temporal_source_is_sent_to_llm():
    payload = {
        "temporal": {
            "rankings": [{"rank": 1, "ip": "A", "score": 0.0}],
            "diagnostics": {"ref_time_ms": None, "devices_with_timestamps": 0},
        },
        "combined_score_rankings": [{"rank": 1, "ip": "A", "combined_score": 0.0}],
    }

    gate = assess_gate(json.dumps(payload))

    assert gate["decision"] == "invoke_llm"
    assert gate["route"] == "llm"
