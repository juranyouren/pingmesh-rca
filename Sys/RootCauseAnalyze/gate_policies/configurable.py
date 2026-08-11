"""Configurable precision-first gate policies and search candidates."""

from __future__ import annotations

import json
import os
from itertools import product
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from Sys.RootCauseAnalyze.trust_trees.common import as_float, top3_overlap, truthy, unique_ips


DEFAULT_POLICY_CONFIG: Dict[str, Any] = {
    "name": "consensus_3of4",
    "policy_version": "configurable_gate_v1",
    "always_llm": False,
    "legacy_v1": False,
    "top1_requirement": "unanimous",
    "require_top1_unanimity": True,
    "trust_requirement": "at_least_one_strong",
    "require_temporal_data": True,
    "combined_margin_percent": 15.0,
    "ranker_margin_percent": 8.0,
    "min_evidence_votes": 3,
    "topology_support": "top3",
    "temporal_support": "two_of_three",
    "ranker_margin_requirement": "any",
}


NAMED_POLICY_CONFIGS: Dict[str, Dict[str, Any]] = {
    "always_llm": {
        **DEFAULT_POLICY_CONFIG,
        "name": "always_llm",
        "always_llm": True,
        "min_evidence_votes": 4,
    },
    "legacy_v1": {
        **DEFAULT_POLICY_CONFIG,
        "name": "legacy_v1",
        "legacy_v1": True,
        "require_top1_unanimity": False,
        "require_temporal_data": False,
        "combined_margin_percent": 0.0,
        "ranker_margin_percent": 0.0,
        "min_evidence_votes": 0,
    },
    "strict_all": {
        **DEFAULT_POLICY_CONFIG,
        "name": "strict_all",
        "trust_requirement": "both_strong",
        "combined_margin_percent": 15.0,
        "ranker_margin_percent": 15.0,
        "min_evidence_votes": 4,
        "topology_support": "exact_top1",
        "temporal_support": "exact_top1",
        "ranker_margin_requirement": "both",
    },
    "consensus_3of4": dict(DEFAULT_POLICY_CONFIG),
    "consensus_2of4": {
        **DEFAULT_POLICY_CONFIG,
        "name": "consensus_2of4",
        "combined_margin_percent": 12.0,
        "min_evidence_votes": 2,
    },
    "balanced_2of4": {
        **DEFAULT_POLICY_CONFIG,
        "name": "balanced_2of4",
        "top1_requirement": "combined_matches_one",
        "require_top1_unanimity": False,
        "require_temporal_data": False,
        "combined_margin_percent": 8.0,
        "ranker_margin_percent": 5.0,
        "min_evidence_votes": 2,
        "trust_requirement": "any",
    },
    "dual_strong_margin": {
        **DEFAULT_POLICY_CONFIG,
        "name": "dual_strong_margin",
        "trust_requirement": "both_strong",
        "combined_margin_percent": 12.0,
        "min_evidence_votes": 0,
    },
}


def normalize_policy_config(config: Mapping[str, Any] | None) -> Dict[str, Any]:
    merged = dict(DEFAULT_POLICY_CONFIG)
    if config:
        merged.update(dict(config))
        if "top1_requirement" not in config and "require_top1_unanimity" in config:
            merged["top1_requirement"] = (
                "unanimous" if config["require_top1_unanimity"] else "any"
            )
    merged["name"] = str(merged.get("name") or "custom")
    merged["combined_margin_percent"] = max(float(merged.get("combined_margin_percent", 0.0)), 0.0)
    merged["ranker_margin_percent"] = max(float(merged.get("ranker_margin_percent", 0.0)), 0.0)
    merged["min_evidence_votes"] = max(0, min(4, int(merged.get("min_evidence_votes", 0))))
    if merged.get("top1_requirement") not in {"unanimous", "combined_matches_one", "any"}:
        raise ValueError(f"invalid top1_requirement: {merged.get('top1_requirement')!r}")
    if merged.get("trust_requirement") not in {
        "both_strong",
        "at_least_one_strong",
        "none_weak",
        "any",
    }:
        raise ValueError(f"invalid trust_requirement: {merged.get('trust_requirement')!r}")
    if merged.get("topology_support") not in {"exact_top1", "top3"}:
        raise ValueError(f"invalid topology_support: {merged.get('topology_support')!r}")
    if merged.get("temporal_support") not in {"exact_top1", "two_of_three"}:
        raise ValueError(f"invalid temporal_support: {merged.get('temporal_support')!r}")
    if merged.get("ranker_margin_requirement") not in {"any", "both"}:
        raise ValueError(
            f"invalid ranker_margin_requirement: {merged.get('ranker_margin_requirement')!r}"
        )
    return merged


def load_policy_config(path_or_config: str | os.PathLike[str] | Mapping[str, Any] | None) -> Dict[str, Any]:
    if path_or_config is None:
        return normalize_policy_config(None)
    if isinstance(path_or_config, Mapping):
        raw: Any = dict(path_or_config)
    else:
        with open(os.fspath(path_or_config), encoding="utf-8") as handle:
            raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("gate policy config must be a JSON object")
    for key in ("config", "selected_config", "selected_policy_config"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            raw = nested
            break
    return normalize_policy_config(raw)


def resolve_policy_config(
    config: str | os.PathLike[str] | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    if config is not None:
        return load_policy_config(config)
    env_path = os.environ.get("PINGMESH_GATE_POLICY_CONFIG", "").strip()
    return load_policy_config(env_path) if env_path else normalize_policy_config(None)


def named_policy_configs(names: Iterable[str] | None = None) -> List[Dict[str, Any]]:
    selected = (
        list(names)
        if names is not None
        else [name for name in NAMED_POLICY_CONFIGS if name != "legacy_v1"]
    )
    missing = [name for name in selected if name not in NAMED_POLICY_CONFIGS]
    if missing:
        raise KeyError(f"unknown gate policies: {missing}; available={sorted(NAMED_POLICY_CONFIGS)}")
    return [normalize_policy_config(NAMED_POLICY_CONFIGS[name]) for name in selected]


def grid_policy_configs() -> List[Dict[str, Any]]:
    """Return a compact search grid spanning strict through balanced policies."""
    configs: List[Dict[str, Any]] = []
    for (
        combined_margin,
        ranker_margin,
        votes,
        trust_requirement,
        top1_requirement,
        require_temporal_data,
    ) in product(
        (0.0, 5.0, 10.0, 15.0, 20.0),
        (0.0, 8.0, 15.0),
        (2, 3, 4),
        ("both_strong", "at_least_one_strong", "any"),
        ("unanimous", "combined_matches_one"),
        (True, False),
    ):
        name = (
            f"grid_c{combined_margin:g}_r{ranker_margin:g}_v{votes}_"
            f"{trust_requirement}_{top1_requirement}_"
            f"temporal_required_{int(require_temporal_data)}"
        )
        configs.append(
            normalize_policy_config(
                {
                    **DEFAULT_POLICY_CONFIG,
                    "name": name,
                    "combined_margin_percent": combined_margin,
                    "ranker_margin_percent": ranker_margin,
                    "min_evidence_votes": votes,
                    "trust_requirement": trust_requirement,
                    "top1_requirement": top1_requirement,
                    "require_top1_unanimity": top1_requirement == "unanimous",
                    "require_temporal_data": require_temporal_data,
                }
            )
        )
    for combined_margin, ranker_margin, votes in product(
        (5.0, 10.0, 15.0, 20.0),
        (0.0, 8.0, 15.0),
        (2, 3, 4),
    ):
        name = f"grid_strict_c{combined_margin:g}_r{ranker_margin:g}_v{votes}"
        configs.append(
            normalize_policy_config(
                {
                    **NAMED_POLICY_CONFIGS["strict_all"],
                    "name": name,
                    "combined_margin_percent": combined_margin,
                    "ranker_margin_percent": ranker_margin,
                    "min_evidence_votes": votes,
                }
            )
        )
    return configs


def _state(tree: Dict[str, Any]) -> str:
    value = tree.get("state") if isinstance(tree, dict) else None
    return value if value in {"strong", "weak", "uncertain"} else "uncertain"


def _evidence(tree: Dict[str, Any]) -> Dict[str, Any]:
    value = tree.get("evidence", {}) if isinstance(tree, dict) else {}
    return value if isinstance(value, dict) else {}


def _margin_ok(value: float | None, threshold: float) -> bool:
    return value is not None and value > 0 and value >= max(float(threshold), 0.0)


def _trust_ok(topo_state: str, temporal_state: str, requirement: str) -> bool:
    if requirement == "both_strong":
        return topo_state == temporal_state == "strong"
    if requirement == "at_least_one_strong":
        return "strong" in {topo_state, temporal_state}
    if requirement == "none_weak":
        return topo_state != "weak" and temporal_state != "weak"
    return True


def _legacy_route(
    *,
    combined_ips: Sequence[str],
    topo_ips: Sequence[str],
    temporal_ips: Sequence[str],
    topo_tree: Dict[str, Any],
    temporal_tree: Dict[str, Any],
) -> Dict[str, Any]:
    from Sys.RootCauseAnalyze.gate_policies.baseline import route

    return route(
        combined_ips=combined_ips,
        topo_ips=topo_ips,
        temporal_ips=temporal_ips,
        topo_tree=topo_tree,
        temporal_tree=temporal_tree,
    )


def _failure_reason(checks: Dict[str, bool]) -> str:
    priorities = (
        ("rankings_complete", "config_incomplete_rankings_invoke_llm"),
        ("top1_agreement", "config_top1_disagreement_invoke_llm"),
        ("ranker_trust_acceptable", "config_ranker_trust_insufficient_invoke_llm"),
        ("temporal_data_available", "config_temporal_data_insufficient_invoke_llm"),
        ("combined_margin_ok", "config_combined_margin_too_small_invoke_llm"),
        ("evidence_quorum", "config_evidence_quorum_not_met_invoke_llm"),
    )
    for check, reason in priorities:
        if not checks.get(check, False):
            return reason
    return "config_safety_certificate_failed_invoke_llm"


def route_with_policy(
    *,
    combined_ips: Sequence[str],
    topo_ips: Sequence[str],
    temporal_ips: Sequence[str],
    topo_tree: Dict[str, Any],
    temporal_tree: Dict[str, Any],
    combined_margin_percent: float | None = None,
    topo_margin_percent: float | None = None,
    temporal_margin_percent: float | None = None,
    policy_config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    config = normalize_policy_config(policy_config)
    combined_ips = unique_ips(combined_ips)
    topo_ips = unique_ips(topo_ips)
    temporal_ips = unique_ips(temporal_ips)

    if config["legacy_v1"]:
        gate = _legacy_route(
            combined_ips=combined_ips,
            topo_ips=topo_ips,
            temporal_ips=temporal_ips,
            topo_tree=topo_tree,
            temporal_tree=temporal_tree,
        )
        gate["policy_version"] = config["policy_version"]
        gate["policy_name"] = config["name"]
        gate["policy_config"] = config
        return gate

    if config["always_llm"]:
        return {
            "enabled": True,
            "decision": "invoke_llm",
            "route": "llm",
            "reason": "policy_always_llm",
            "policy_version": config["policy_version"],
            "policy_name": config["name"],
            "policy_config": config,
            "recommended_ips": list(combined_ips),
            "agreement": {
                "rank_near": False,
                "top3_overlap": 0,
                "top3_overlap_ips": [],
                "method_top_ips": {
                    "topo": topo_ips[0] if topo_ips else None,
                    "temporal": temporal_ips[0] if temporal_ips else None,
                    "combined": combined_ips[0] if combined_ips else None,
                },
            },
            "safety_certificate": {
                "safe_to_bypass": False,
                "checks": {"always_llm": True},
                "passed": ["always_llm"],
                "failed": [],
                "evidence_votes": {"count": 0, "required": 4, "available": 4},
            },
            "trust_trees": {"topo": topo_tree, "temporal": temporal_tree},
        }

    topo_state = _state(topo_tree)
    temporal_state = _state(temporal_tree)
    topo_evidence = _evidence(topo_tree)
    temporal_evidence = _evidence(temporal_tree)
    topo_entry = topo_evidence.get("top_entry", {})
    topo_entry = topo_entry if isinstance(topo_entry, dict) else {}

    directed_top3 = topo_evidence.get("directed_top3", [])
    undirected_top3 = topo_evidence.get("undirected_top3", [])
    burst_top3 = temporal_evidence.get("burst_top3", [])
    early_top3 = temporal_evidence.get("early_top3", [])
    density_top3 = temporal_evidence.get("density_top3", [])
    directed_top3 = directed_top3 if isinstance(directed_top3, list) else []
    undirected_top3 = undirected_top3 if isinstance(undirected_top3, list) else []
    burst_top3 = burst_top3 if isinstance(burst_top3, list) else []
    early_top3 = early_top3 if isinstance(early_top3, list) else []
    density_top3 = density_top3 if isinstance(density_top3, list) else []

    if topo_margin_percent is None:
        topo_margin_percent = topo_evidence.get("top1_margin_percent")
    if temporal_margin_percent is None:
        temporal_margin_percent = temporal_evidence.get("top1_margin_percent")

    top_ip = combined_ips[0] if combined_ips else None
    overlap_n, overlap_ips = top3_overlap(topo_ips, temporal_ips)
    temporal_supported_by = {
        name
        for name, ips in (
            ("burst", burst_top3),
            ("early", early_top3),
            ("density", density_top3),
        )
        if top_ip and top_ip in set(ips[:3])
    }
    temporal_data_available = truthy(temporal_evidence.get("temporal_data_available")) or (
        temporal_evidence.get("ref_time_ms") is not None
        and as_float(temporal_evidence.get("devices_with_timestamps")) >= 2
        and as_float(temporal_evidence.get("top_event_count")) > 0
    )
    top1_unanimous = bool(
        combined_ips
        and topo_ips
        and temporal_ips
        and combined_ips[0] == topo_ips[0] == temporal_ips[0]
    )
    combined_matches_one = bool(
        combined_ips
        and (
            (topo_ips and combined_ips[0] == topo_ips[0])
            or (temporal_ips and combined_ips[0] == temporal_ips[0])
        )
    )
    top1_requirement = str(config["top1_requirement"])
    top1_agreement = (
        top1_unanimous
        if top1_requirement == "unanimous"
        else combined_matches_one
        if top1_requirement == "combined_matches_one"
        else True
    )
    hard_checks = {
        "rankings_complete": bool(combined_ips and topo_ips and temporal_ips),
        "top1_agreement": top1_agreement,
        "ranker_trust_acceptable": _trust_ok(
            topo_state, temporal_state, str(config["trust_requirement"])
        ),
        "temporal_data_available": (
            temporal_data_available if config["require_temporal_data"] else True
        ),
        "combined_margin_ok": _margin_ok(
            combined_margin_percent, float(config["combined_margin_percent"])
        ),
    }

    topology_exact = bool(
        top_ip
        and directed_top3
        and undirected_top3
        and directed_top3[0] == undirected_top3[0] == top_ip
    )
    topology_top3 = bool(
        top_ip
        and directed_top3
        and undirected_top3
        and directed_top3[0] == top_ip
        and top_ip in set(undirected_top3[:3])
    )
    temporal_exact = bool(
        top_ip and burst_top3 and early_top3 and burst_top3[0] == early_top3[0] == top_ip
    )
    temporal_two = bool(
        len(temporal_supported_by) >= 2
        and temporal_supported_by.intersection({"burst", "density"})
    )
    topo_margin_ok = _margin_ok(topo_margin_percent, float(config["ranker_margin_percent"]))
    temporal_margin_ok = _margin_ok(
        temporal_margin_percent, float(config["ranker_margin_percent"])
    )
    evidence_checks = {
        "topology_direction_support": (
            topology_exact if config["topology_support"] == "exact_top1" else topology_top3
        ),
        "direct_root_evidence": truthy(topo_entry.get("high_weight_alarm_hit"))
        or as_float(topo_entry.get("max_alarm_weight")) > 0,
        "temporal_multisignal_support": (
            temporal_exact if config["temporal_support"] == "exact_top1" else temporal_two
        ),
        "independent_ranker_margin_support": (
            topo_margin_ok and temporal_margin_ok
            if config["ranker_margin_requirement"] == "both"
            else topo_margin_ok or temporal_margin_ok
        ),
    }
    evidence_vote_count = sum(1 for ok in evidence_checks.values() if ok)
    checks = {
        **hard_checks,
        **evidence_checks,
        "evidence_quorum": evidence_vote_count >= int(config["min_evidence_votes"]),
    }
    safe_to_bypass = all(hard_checks.values()) and checks["evidence_quorum"]
    decision = "bypass_llm" if safe_to_bypass else "invoke_llm"
    route = "combined" if safe_to_bypass else "llm"
    reason = (
        f"{config['name']}_accept_combined"
        if safe_to_bypass
        else _failure_reason(checks)
    )
    recommended_ips = [combined_ips[0]] if safe_to_bypass and combined_ips else list(combined_ips)

    return {
        "enabled": True,
        "decision": decision,
        "route": route,
        "reason": reason,
        "policy_version": config["policy_version"],
        "policy_name": config["name"],
        "policy_config": config,
        "recommended_ips": recommended_ips,
        "agreement": {
            "rank_near": bool(topo_ips and temporal_ips and topo_ips[0] == temporal_ips[0])
            or overlap_n >= 2,
            "top3_overlap": overlap_n,
            "top3_overlap_ips": overlap_ips,
            "method_top_ips": {
                "topo": topo_ips[0] if topo_ips else None,
                "temporal": temporal_ips[0] if temporal_ips else None,
                "combined": combined_ips[0] if combined_ips else None,
            },
        },
        "safety_certificate": {
            "safe_to_bypass": safe_to_bypass,
            "checks": checks,
            "passed": [name for name, ok in checks.items() if ok],
            "failed": [name for name, ok in checks.items() if not ok],
            "margins_percent": {
                "combined": combined_margin_percent,
                "topo": topo_margin_percent,
                "temporal": temporal_margin_percent,
            },
            "thresholds_percent": {
                "combined": config["combined_margin_percent"],
                "ranker": config["ranker_margin_percent"],
            },
            "evidence_votes": {
                "count": evidence_vote_count,
                "required": config["min_evidence_votes"],
                "available": len(evidence_checks),
            },
        },
        "trust_trees": {"topo": topo_tree, "temporal": temporal_tree},
    }
