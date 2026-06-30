from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from Sys.RootCauseAnalyze.skills.fusion import rank_devices_by_skills
from Sys.utils.alarm_utils import extract_alarm_names, load_alarm_weights, node_alarm_weight
from Sys.utils.case_utils import get_device_ip, load_case_info, load_case_nodes

DETAIL_MAX_ALARMS_PER_NODE = 30
RAW_DROP_FIELDS = ("node_sign", "type", "devicetype", "verified_hops_to")
INFO_KEYS = [
    "alarm_name",
    "alarm_time",
    "source_ip",
    "sink_ip",
    "src_tunnel_ip",
    "dst_tunnel_ip",
    "scenario_code",
    "analysis_type",
    "task_num",
    "alarm_description",
]

TOPO_DESC = (
    "Personalized PageRank (directed) on physical topology graph. "
    "Initial weight = max alarm weight hits + cross_count multiplier + source/sink proximity bonus. "
    "Higher score = device at topology bottleneck traversed by multiple anomaly paths."
)

TEMPORAL_DESC = (
    "Temporal suspicion score (0-1): Burst, Early Bird, and Temporal Density. "
    "Higher = alarms earlier and more concentrated near the fault reference time."
)


def _build_info_brief(info: Dict[str, Any]) -> str:
    if not isinstance(info, dict):
        return "(no fault summary)"
    lines = [f"- {key}: {value}" for key in INFO_KEYS if (value := info.get(key)) not in (None, "", "[]", "--")]
    return "\n".join(lines) if lines else "(no fault summary)"


def _build_candidate_raw(candidate_ips: List[str], node_by_ip: Dict[str, Dict[str, Any]]) -> str:
    raw = {
        ip: {key: value for key, value in node_by_ip.get(ip, {}).items() if key not in RAW_DROP_FIELDS}
        for ip in candidate_ips
        if ip in node_by_ip
    }
    return json.dumps(raw, ensure_ascii=False, indent=2) if raw else "{}"


def build_fused_evidence(
    node_list: List[Dict[str, Any]] | None,
    info: Dict[str, Any] | None,
    dirpath: str,
    skill_map: Dict[str, Any] | None = None,
    weight_dirpath: str | None = None,
    top_k: int = 10,
) -> Tuple[str, str, str, str, List[str]]:
    """Build LLM-ready evidence and deterministic candidate ranking for one case."""
    del skill_map  # Kept for backward signature compatibility.
    node_list = node_list or load_case_nodes(dirpath)
    info = info or load_case_info(dirpath)

    candidate_ips, skill_details = rank_devices_by_skills(
        node_list,
        info,
        dirpath=dirpath,
        skill_ids=(1, 2),
        directed=True,
        weight_dirpath=weight_dirpath,
        top_k=top_k,
    )
    topo_detail = skill_details.get("1", {})
    temporal_detail = skill_details.get("2", {})
    combined_detail = skill_details.get("combined", {})

    weights = load_alarm_weights(weight_dirpath)
    node_by_ip = {get_device_ip(node): node for node in node_list}
    combined_list = combined_detail.get("topk", [])

    skill_ret = json.dumps(
        {
            "topo": {
                "description": TOPO_DESC,
                "rankings": topo_detail.get("topk", []),
                "diagnostics": topo_detail.get("diagnostics", {}),
                "trust_tree": topo_detail.get("trust_tree", {}),
            },
            "temporal": {
                "description": TEMPORAL_DESC,
                "rankings": temporal_detail.get("topk", []),
                "diagnostics": temporal_detail.get("diagnostics", {}),
                "trust_tree": temporal_detail.get("trust_tree", {}),
            },
            "combined_score_rankings": [
                {
                    **item,
                    "role": node_by_ip.get(item.get("ip"), {}).get("role", "UNKNOWN"),
                }
                for item in combined_list
            ],
        },
        ensure_ascii=False,
        indent=2,
    )

    devices_detail = []
    for ip in candidate_ips:
        node = node_by_ip.get(ip)
        if not node:
            continue
        names = extract_alarm_names(node)
        _max_weight, high_alarms = node_alarm_weight(node, weights)
        devices_detail.append(
            {
                "ip": ip,
                "role": node.get("role", "UNKNOWN"),
                "cross": node.get("cross", 0),
                "alarm_count": len(names),
                "alarms": names[:DETAIL_MAX_ALARMS_PER_NODE],
                "high_severity_alarms": high_alarms[:10],
                "topology": {
                    "upstream": node.get("linked_from", [])[:10],
                    "downstream": node.get("linked_to", [])[:10],
                },
            }
        )

    candidate_detail = json.dumps({"devices": devices_detail}, ensure_ascii=False, indent=2)
    candidate_raw = _build_candidate_raw(candidate_ips, node_by_ip)
    return skill_ret, _build_info_brief(info), candidate_detail, candidate_raw, candidate_ips
