from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence, Tuple

from Sys_v1.RootCauseAnalyze.skills.temporal_ranker import score_temporal, temporal_details
from Sys_v1.RootCauseAnalyze.skills.topo_ranker import score_topo, topo_details
from Sys_v1.utils.alarm_utils import (
    event_name,
    event_ts,
    extract_alarm_names,
    load_alarm_weights,
    node_alarm_weight,
)
from Sys_v1.utils.case_utils import get_device_ip, load_case_info, load_case_nodes
from Sys_v1.utils.ranking_utils import combine_scores, sorted_score_items

DETAIL_MAX_ALARMS_PER_NODE = 30
RAW_DROP_FIELDS = ("node_sign", "type", "devicetype", "verified_hops_to")
NEIGHBOR_ALARM_MODES = ("none", "highest_weight", "all")
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
    "Directed PageRank on the physical topology graph. Personalization uses only "
    "topology-derived path-crossing and source/sink proximity features; alarms and logs "
    "do not affect this score. Higher means a stronger topology-focused candidate."
)

TEMPORAL_DESC = (
    "Temporal suspicion score (0-1): Burst, Early Bird, and Temporal Density. "
    "Higher means alarms are earlier and more concentrated near the fault reference time."
)

EVIDENCE_ORGANIZATION_VERSION = "sys-v1-neighbor-alarm-context-v1"


def _build_info_brief(info: Dict[str, Any]) -> str:
    if not isinstance(info, dict):
        return "(no fault summary)"
    lines = [
        f"- {key}: {value}"
        for key in INFO_KEYS
        if (value := info.get(key)) not in (None, "", "[]", "--")
    ]
    return "\n".join(lines) if lines else "(no fault summary)"


def _build_candidate_raw(candidate_ips: Sequence[str], node_by_ip: Dict[str, Dict[str, Any]]) -> str:
    raw = {
        ip: {
            key: value
            for key, value in node_by_ip.get(ip, {}).items()
            if key not in RAW_DROP_FIELDS
        }
        for ip in candidate_ips
        if ip in node_by_ip
    }
    return json.dumps(raw, ensure_ascii=False, indent=2) if raw else "{}"


def _alarm_records(node: Dict[str, Any], weights: Dict[str, int]) -> List[Dict[str, Any]]:
    """Return de-duplicated device alarms with rule weights and known times."""
    records: List[Dict[str, Any]] = []
    seen = set()
    for alarm in node.get("alarms", []) or []:
        name = event_name(alarm)
        if not name or name in seen:
            continue
        seen.add(name)
        record: Dict[str, Any] = {
            "name": name,
            "weight": int(weights.get(name.lower(), 0)),
        }
        timestamp = event_ts(alarm)
        if timestamp is not None:
            record["time"] = timestamp
        records.append(record)
    return records


def _neighbor_relation(node: Dict[str, Any], neighbor_ip: str) -> str:
    upstream = neighbor_ip in set(node.get("linked_from", []) or [])
    downstream = neighbor_ip in set(node.get("linked_to", []) or [])
    if upstream and downstream:
        return "bidirectional"
    if upstream:
        return "upstream"
    return "downstream"


def build_neighbor_alarm_context(
    node: Dict[str, Any],
    node_by_ip: Dict[str, Dict[str, Any]],
    weights: Dict[str, int],
    *,
    mode: str = "highest_weight",
    max_neighbor_devices: int = 8,
    max_neighbor_alarms: int = 3,
) -> List[Dict[str, Any]]:
    """Select bounded alarm context from devices adjacent to ``node``.

    The default policy keeps exactly one alarm per adjacent device: the alarm
    with the highest configured rule weight. Ties retain the source-data order.
    Neighbors are then ordered by that selected weight and IP for deterministic
    prompts. ``all`` keeps up to ``max_neighbor_alarms`` alarms per neighbor.
    """
    if mode not in NEIGHBOR_ALARM_MODES:
        raise ValueError(f"neighbor alarm mode must be one of {NEIGHBOR_ALARM_MODES}, got {mode!r}")
    if mode == "none" or max_neighbor_devices <= 0:
        return []

    neighbor_ips: List[str] = []
    seen = set()
    for value in [*(node.get("linked_from", []) or []), *(node.get("linked_to", []) or [])]:
        ip = str(value) if value is not None else ""
        if ip and ip not in seen:
            seen.add(ip)
            neighbor_ips.append(ip)

    contexts: List[Dict[str, Any]] = []
    for neighbor_ip in neighbor_ips:
        neighbor = node_by_ip.get(neighbor_ip)
        if not neighbor:
            continue
        alarm_records = _alarm_records(neighbor, weights)
        if not alarm_records:
            continue
        ranked = sorted(
            enumerate(alarm_records),
            key=lambda item: (-item[1]["weight"], item[0]),
        )
        if mode == "highest_weight":
            selected = [ranked[0][1]]
        else:
            selected = [record for _index, record in ranked[: max(1, max_neighbor_alarms)]]
        contexts.append(
            {
                "neighbor_ip": neighbor_ip,
                "role": neighbor.get("role", "UNKNOWN"),
                "relation": _neighbor_relation(node, neighbor_ip),
                "selected_alarms": selected,
                "total_alarm_count": len(alarm_records),
            }
        )

    contexts.sort(
        key=lambda item: (
            -max((alarm["weight"] for alarm in item["selected_alarms"]), default=0),
            item["neighbor_ip"],
        )
    )
    return contexts[:max_neighbor_devices]


def _combined_rankings(
    skill_id_to_scores: Dict[int, Dict[str, float]],
    candidate_ips: Sequence[str],
    top_k: int,
) -> List[Dict[str, Any]]:
    # Round only to remove binary floating-point tie noise; the underlying
    # fusion remains the strict arithmetic mean.
    scores = {
        ip: round(score, 12)
        for ip, score in combine_scores(skill_id_to_scores, candidate_ips).items()
    }
    return [
        {"rank": rank, "ip": ip, "combined_score": round(score, 6)}
        for rank, (ip, score) in enumerate(sorted_score_items(scores, top_k), 1)
    ]


def _build_rankings(
    node_list: List[Dict[str, Any]],
    info: Dict[str, Any],
    dirpath: str,
    *,
    skill_ids: Sequence[int],
    candidate_strategy: str,
    weight_dirpath: str | None,
    top_k: int,
) -> Tuple[List[str], Dict[str, Any]]:
    """Run the selected deterministic modules with stage-boundary isolation."""
    normalized_ids = tuple(dict.fromkeys(int(skill_id) for skill_id in skill_ids))
    all_ips = sorted(
        {get_device_ip(node) for node in node_list if get_device_ip(node) not in ("", "unknown")}
    )
    node_by_ip = {get_device_ip(node): node for node in node_list}
    details: Dict[str, Any] = {}
    score_sources: Dict[int, Dict[str, float]] = {}

    topology_scores: Dict[str, float] = {}
    focused_ips = list(all_ips)
    if 1 in normalized_ids:
        topology_scores = score_topo(node_list, info, weight_path=weight_dirpath, directed=True)
        topology_block = topo_details(
            node_list,
            info,
            topology_scores,
            weight_path=weight_dirpath,
            directed=True,
            top_k=top_k,
        )
        details["1"] = topology_block
        score_sources[1] = topology_scores or {
            row["ip"]: float(row.get("pr_score", 0.0))
            for row in topology_block.get("topk", [])
            if row.get("ip")
        }
        focused_ips = [row["ip"] for row in topology_block.get("topk", []) if row.get("ip")]

    if candidate_strategy == "all_devices":
        evidence_ips = list(all_ips)
    elif candidate_strategy == "topology_top_k":
        evidence_ips = focused_ips[:top_k]
    else:
        raise ValueError(f"unknown candidate strategy: {candidate_strategy!r}")

    if 2 in normalized_ids:
        temporal_nodes = (
            node_list
            if candidate_strategy == "all_devices"
            else [node_by_ip[ip] for ip in evidence_ips if ip in node_by_ip]
        )
        temporal_scores = score_temporal(temporal_nodes, info, dirpath=dirpath)
        details["2"] = temporal_details(
            temporal_nodes,
            info,
            dirpath,
            temporal_scores,
            top_k=len(evidence_ips) if candidate_strategy == "all_devices" else top_k,
        )
        score_sources[2] = temporal_scores

    # In the full pipeline this is the strict arithmetic mean of M1 and M2.
    # In a single-source ablation it is simply that source's score.
    combined_limit = len(evidence_ips) if candidate_strategy == "all_devices" else top_k
    combined = _combined_rankings(score_sources, evidence_ips, combined_limit)
    details["combined"] = {
        "top3": combined[:3],
        "topk": combined,
        "rankings": combined,
        "fusion": "arithmetic_mean" if len(score_sources) > 1 else "single_source_identity",
    }
    ranked_ips = [row["ip"] for row in combined]
    return ranked_ips, details


def build_fused_evidence(
    node_list: List[Dict[str, Any]] | None,
    info: Dict[str, Any] | None,
    dirpath: str,
    skill_map: Dict[str, Any] | None = None,
    weight_dirpath: str | None = None,
    top_k: int = 10,
    *,
    skill_ids: Sequence[int] = (1, 2),
    candidate_strategy: str = "topology_top_k",
    enable_m2: bool = True,
    neighbor_alarm_mode: str = "highest_weight",
    max_neighbor_devices: int = 8,
    max_neighbor_alarms: int = 3,
) -> Tuple[str, str, str, str, List[str]]:
    """Build the evidence table and deterministic ranking for one case.

    ``enable_m2`` controls evidence collection and semantic-summary input only;
    numeric ranking is controlled by ``skill_ids``. This separation prevents
    M1 and M1+M3 ablations from silently executing M2.
    """
    del skill_map  # Kept for backward signature compatibility.
    node_list = node_list or load_case_nodes(dirpath)
    info = info or load_case_info(dirpath)

    candidate_ips, skill_details = _build_rankings(
        node_list,
        info,
        dirpath,
        skill_ids=skill_ids,
        candidate_strategy=candidate_strategy,
        weight_dirpath=weight_dirpath,
        top_k=top_k,
    )
    topo_detail = skill_details.get("1")
    temporal_detail = skill_details.get("2")
    combined_detail = skill_details.get("combined", {})
    node_by_ip = {
        get_device_ip(node): node
        for node in node_list
        if get_device_ip(node) not in ("", "unknown")
    }

    skill_table: Dict[str, Any] = {
        "enabled_modules": [f"M{skill_id}" for skill_id in skill_ids],
        "score_fusion": combined_detail.get("fusion"),
    }
    if topo_detail is not None:
        skill_table["topo"] = {
            "description": TOPO_DESC,
            "rankings": topo_detail.get("topk", []),
            "diagnostics": topo_detail.get("diagnostics", {}),
            "trust_tree": topo_detail.get("trust_tree", {}),
        }
    if temporal_detail is not None:
        skill_table["temporal"] = {
            "description": TEMPORAL_DESC,
            "rankings": temporal_detail.get("topk", []),
            "diagnostics": temporal_detail.get("diagnostics", {}),
            "trust_tree": temporal_detail.get("trust_tree", {}),
        }
    skill_table["combined_score_rankings"] = [
        {
            **item,
            "role": node_by_ip.get(item.get("ip"), {}).get("role", "UNKNOWN"),
        }
        for item in combined_detail.get("topk", [])
    ]
    skill_ret = json.dumps(skill_table, ensure_ascii=False, indent=2)

    weights = load_alarm_weights(weight_dirpath) if enable_m2 else {}
    devices_detail = []
    for ip in candidate_ips:
        node = node_by_ip.get(ip)
        if not node:
            continue
        record: Dict[str, Any] = {
            "ip": ip,
            "role": node.get("role", "UNKNOWN"),
            "cross": node.get("cross", 0),
            "topology": {
                "upstream": (node.get("linked_from", []) or [])[:10],
                "downstream": (node.get("linked_to", []) or [])[:10],
            },
        }
        if enable_m2:
            names = extract_alarm_names(node)
            _max_weight, high_alarms = node_alarm_weight(node, weights)
            record.update(
                {
                    "alarm_count": len(names),
                    "alarms": names[:DETAIL_MAX_ALARMS_PER_NODE],
                    "alarm_events": _alarm_records(node, weights)[:DETAIL_MAX_ALARMS_PER_NODE],
                    "high_weight_alarms": high_alarms[:10],
                }
            )
            record["adjacent_alarm_context_policy"] = {
                "mode": neighbor_alarm_mode,
                "max_neighbor_devices": max_neighbor_devices,
                "max_alarms_per_neighbor": 1
                if neighbor_alarm_mode == "highest_weight"
                else max_neighbor_alarms,
            }
            record["adjacent_alarm_context"] = build_neighbor_alarm_context(
                node,
                node_by_ip,
                weights,
                mode=neighbor_alarm_mode,
                max_neighbor_devices=max_neighbor_devices,
                max_neighbor_alarms=max_neighbor_alarms,
            )
        devices_detail.append(record)

    organization = {
        "version": EVIDENCE_ORGANIZATION_VERSION,
        "strategy": candidate_strategy,
        "top_k": top_k,
        "device_count": len(devices_detail),
        "m2_evidence_collection": bool(enable_m2),
    }
    if enable_m2:
        organization["neighbor_alarm_policy"] = {
            "mode": neighbor_alarm_mode,
            "max_neighbor_devices": max_neighbor_devices,
            "max_alarms_per_neighbor": 1
            if neighbor_alarm_mode == "highest_weight"
            else max_neighbor_alarms,
        }
    candidate_detail = json.dumps(
        {"organization": organization, "devices": devices_detail},
        ensure_ascii=False,
        indent=2,
    )
    candidate_raw = _build_candidate_raw(candidate_ips, node_by_ip) if enable_m2 else "{}"
    return skill_ret, _build_info_brief(info), candidate_detail, candidate_raw, candidate_ips
