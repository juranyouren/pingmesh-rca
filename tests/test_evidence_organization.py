import json
from unittest.mock import patch

from Sys.RootCauseAnalyze.gate.evidence import _ranked_ip_union, build_fused_evidence
from scripts.precompute_node_summaries import gib_to_bytes


def test_kv_cache_gib_conversion_rejects_non_positive_values():
    assert gib_to_bytes(4) == 4 * 1024**3
    for value in (0, -1):
        try:
            gib_to_bytes(value)
        except ValueError:
            pass
        else:
            raise AssertionError("non-positive cache sizes must be rejected")


def test_ranked_ip_union_interleaves_and_deduplicates_two_rankings():
    topo = [{"ip": "topo-1"}, {"ip": "shared"}, {"ip": "topo-3"}]
    temporal = [{"ip": "temp-1"}, {"ip": "shared"}, {"ip": "temp-3"}]

    assert _ranked_ip_union(topo, temporal) == [
        "topo-1", "temp-1", "shared", "topo-3", "temp-3"
    ]


def test_llm_evidence_uses_topology_temporal_union_but_returns_fused_ranking():
    nodes = [
        {"mgmt_ip": ip, "role": "LEAF", "alarms": [], "logs": []}
        for ip in ("topo-1", "topo-2", "temp-1", "temp-2", "fused-1")
    ]
    details = {
        "1": {"topk": [{"rank": 1, "ip": "topo-1"}, {"rank": 2, "ip": "topo-2"}]},
        "2": {"topk": [{"rank": 1, "ip": "temp-1"}, {"rank": 2, "ip": "temp-2"}]},
        "combined": {"topk": [{"rank": 1, "ip": "fused-1", "combined_score": 1.0}]},
    }

    with patch(
        "Sys.RootCauseAnalyze.gate.evidence.rank_devices_by_skills",
        return_value=(["fused-1"], details),
    ):
        _skill_ret, _info, detail, raw, skill_ips = build_fused_evidence(
            node_list=nodes,
            info={"alarm_time": 1000},
            dirpath="unused",
            top_k=2,
        )

    organized = json.loads(detail)
    evidence_ips = [device["ip"] for device in organized["devices"]]

    assert evidence_ips == ["topo-1", "temp-1", "topo-2", "temp-2"]
    assert organized["organization"]["strategy"] == "topology_top_k_union_temporal_top_k"
    assert "fused-1" not in json.loads(raw)
    assert skill_ips == ["fused-1"]
