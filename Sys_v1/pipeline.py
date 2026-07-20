from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Sequence

from Sys.utils.case_utils import find_full_link_file, get_device_ip, load_case_info, load_case_nodes

from .config import AblationSpec, get_ablation_spec
from .evidence import build_evidence_table, build_raw_review_context, load_semantic_cache
from .gate import assess_confidence, disabled_gate
from .llm import LocalVllmReviewer, parse_llm_ranking
from .prompts import PROMPT_VERSION, build_review_prompt
from .scoring import device_ips, mean_enabled_scores, ranking_rows, score_temporal
from .topology import ranked_score_rows, score_topology


RESULT_SCHEMA_VERSION = "sys-v1-ablation-result-v1"


@dataclass
class PipelineSettings:
    top_k: int = 10
    directed_topology: bool = True
    single_source_accept_margin: float = 0.15
    multi_source_accept_margin: float = 0.08
    semantic_cache_dir: str | None = None
    max_events_per_device: int = 30
    save_prompts: bool = False
    llm_batch_size: int = 8


def discover_case_dirs(data_root: str) -> list[str]:
    case_dirs: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(data_root):
        if "info.json" not in filenames:
            continue
        if not find_full_link_file(dirpath, filenames):
            continue
        case_dirs.append(dirpath)
    return sorted(case_dirs)


def _node_subset(node_list: Sequence[Dict[str, Any]], ips: Iterable[str]) -> list[Dict[str, Any]]:
    ip_set = set(ips)
    return [node for node in node_list if get_device_ip(node) in ip_set]


def _ranked_ips(rows: Sequence[Mapping[str, Any]], limit: int | None = None) -> list[str]:
    selected = rows[:limit] if limit is not None else rows
    return [
        str(row["ip"])
        for row in selected
        if isinstance(row, Mapping) and isinstance(row.get("ip"), str) and row.get("ip")
    ]


def _compact_info(info: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "alarm_name",
        "alarm_time",
        "source_ip",
        "sink_ip",
        "src_tunnel_ip",
        "dst_tunnel_ip",
        "analysis_type",
        "scenario_code",
        "alarm_description",
    )
    return {key: info[key] for key in keys if info.get(key) not in (None, "", "[]", "--")}


def build_case_plan(
    case_dir: str,
    variant: str | AblationSpec,
    settings: PipelineSettings | None = None,
) -> dict[str, Any]:
    """Build a label-free case plan and optional LLM prompt."""

    settings = settings or PipelineSettings()
    spec = variant if isinstance(variant, AblationSpec) else get_ablation_spec(variant)
    node_list = load_case_nodes(case_dir)
    info = load_case_info(case_dir)
    all_ips = device_ips(node_list)
    node_by_ip = {get_device_ip(node): node for node in node_list}

    topology_scores: dict[str, float] = {}
    topology_diagnostics: dict[str, Any] = {"available": False, "reason": "m1_disabled"}
    if spec.enable_m1:
        topology_scores, topology_diagnostics = score_topology(
            node_list,
            info,
            directed=settings.directed_topology,
        )
    topology_ranking_all = ranked_score_rows(topology_scores, score_key="topology_score")

    if spec.candidate_scope == "topology_top_k":
        candidate_ips = [row["ip"] for row in topology_ranking_all[: settings.top_k]]
    elif spec.candidate_scope == "all_devices":
        candidate_ips = list(all_ips)
    else:
        raise ValueError(f"Unsupported candidate scope: {spec.candidate_scope}")

    candidate_nodes = [node_by_ip[ip] for ip in candidate_ips if ip in node_by_ip]
    temporal_scores: dict[str, float] = {}
    temporal_features: dict[str, dict[str, float]] = {}
    temporal_diagnostics: dict[str, Any] = {"available": False, "reason": "m2_disabled"}
    if spec.enable_m2 and spec.use_temporal_score:
        temporal_scores, temporal_features, temporal_diagnostics = score_temporal(
            candidate_nodes,
            info,
            dirpath=case_dir,
        )
        temporal_diagnostics = {"available": bool(temporal_scores), **temporal_diagnostics}

    semantics = load_semantic_cache(settings.semantic_cache_dir, case_dir) if spec.enable_m2 else {}
    evidence_table: list[dict[str, Any]] = []
    if spec.enable_m2:
        evidence_table = build_evidence_table(
            candidate_nodes,
            candidate_ips,
            topology_scores=topology_scores if spec.use_topology_score else {},
            temporal_scores=temporal_scores,
            temporal_features=temporal_features,
            semantic_annotations=semantics,
            max_events_per_device=settings.max_events_per_device,
        )

    source_scores: dict[str, Mapping[str, float]] = {}
    if spec.use_topology_score:
        source_scores["topology"] = topology_scores
    if spec.use_temporal_score:
        source_scores["temporal"] = temporal_scores

    combined_scores, fusion = mean_enabled_scores(source_scores, candidate_ips)
    preliminary_ranking = ranking_rows(combined_scores, source_scores)
    if not preliminary_ranking and spec.name == "m1":
        preliminary_ranking = [
            {
                "rank": row["rank"],
                "ip": row["ip"],
                "combined_score": row["topology_score"],
                "source_scores": {"topology": row["topology_score"]},
            }
            for row in topology_ranking_all[: settings.top_k]
        ]

    if spec.enable_gate:
        gate = assess_confidence(
            preliminary_ranking,
            source_scores,
            single_source_accept_margin=settings.single_source_accept_margin,
            multi_source_accept_margin=settings.multi_source_accept_margin,
        )
    else:
        gate = disabled_gate(preliminary_ranking)

    legal_candidate_ips = _ranked_ips(preliminary_ranking, settings.top_k)
    review_rows: list[dict[str, Any]] = []
    if gate.get("action") == "llm_review":
        if spec.enable_m2:
            legal_set = set(legal_candidate_ips)
            review_rows = [
                row for row in evidence_table if row.get("candidate_ip") in legal_set
            ]
        else:
            review_rows = build_raw_review_context(
                node_list,
                legal_candidate_ips,
                topology_scores=topology_scores,
                max_events_per_device=settings.max_events_per_device,
            )

    llm_prompt = None
    if gate.get("action") == "llm_review" and legal_candidate_ips:
        llm_prompt = build_review_prompt(
            variant=spec.name,
            info=_compact_info(info),
            preliminary_ranking=preliminary_ranking[: settings.top_k],
            gate=gate,
            evidence_rows=review_rows,
            legal_candidate_ips=legal_candidate_ips,
        )

    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "dir": case_dir,
        "case_id": os.path.basename(os.path.normpath(case_dir)),
        "ablation": spec.name,
        "ablation_spec": asdict(spec),
        "candidate_scope": spec.candidate_scope,
        "all_device_count": len(all_ips),
        "candidate_count": len(candidate_ips),
        "candidate_ips": candidate_ips,
        "topology": {
            "enabled": spec.enable_m1,
            "diagnostics": topology_diagnostics,
            "ranking": topology_ranking_all,
        },
        "temporal": {
            "enabled": spec.enable_m2 and spec.use_temporal_score,
            "diagnostics": temporal_diagnostics,
            "ranking": ranked_score_rows(temporal_scores, score_key="temporal_score"),
        },
        "evidence_table": evidence_table,
        "semantic_cache": {
            "configured": bool(settings.semantic_cache_dir),
            "matched_device_count": len(semantics),
            "used_for_scoring": False,
        },
        "fusion": fusion,
        "preliminary_scores": combined_scores,
        "preliminary_ranking": preliminary_ranking,
        "confidence_gate": gate,
        "legal_llm_candidate_ips": legal_candidate_ips,
        "llm": {
            "requested": bool(llm_prompt),
            "executed": False,
            "backend": None,
            "prompt_version": PROMPT_VERSION,
        },
        "_llm_prompt": llm_prompt,
    }


def _merge_review_ranking(
    llm_ips: Sequence[str],
    preliminary_ips: Sequence[str],
    legal_ips: Sequence[str],
    *,
    top_k: int,
) -> tuple[list[str], list[str]]:
    legal_set = set(legal_ips)
    accepted = list(dict.fromkeys(ip for ip in llm_ips if ip in legal_set))
    rejected = list(dict.fromkeys(ip for ip in llm_ips if ip not in legal_set))
    final = list(accepted)
    for ip in preliminary_ips:
        if ip in legal_set and ip not in final:
            final.append(ip)
    return final[:top_k], rejected


def _response_json(decision: str, ips: Sequence[str], reasoning: str) -> str:
    payload = {"decision": decision, "reasoning": reasoning, "ip": list(ips)}
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"


def finalize_case_plan(
    plan: dict[str, Any],
    *,
    settings: PipelineSettings,
    llm_backend: str,
    llm_response: str | None = None,
) -> dict[str, Any]:
    preliminary_ips = _ranked_ips(plan.get("preliminary_ranking", []))
    legal_ips = list(plan.get("legal_llm_candidate_ips", []))
    gate = plan.get("confidence_gate", {})
    action = gate.get("action")
    llm_meta = dict(plan.get("llm", {}))

    if action == "operator_review":
        final_ips: list[str] = []
        final_decision = "operator_review"
        reasoning = "No usable automatic ranking evidence was available."
    elif action != "llm_review":
        final_ips = preliminary_ips[: settings.top_k]
        final_decision = "accept_preliminary"
        reasoning = "Confidence routing accepted the preliminary ranking."
    elif llm_backend == "none" or llm_response is None:
        final_ips = preliminary_ips[: settings.top_k]
        final_decision = "llm_unavailable_keep_preliminary"
        reasoning = "LLM review was requested but not executed; dry-run kept the preliminary ranking."
        llm_meta.update({"backend": llm_backend, "executed": False})
    else:
        parsed_ips, parse_meta = parse_llm_ranking(llm_response)
        final_ips, rejected = _merge_review_ranking(
            parsed_ips,
            preliminary_ips,
            legal_ips,
            top_k=settings.top_k,
        )
        if not final_ips:
            final_ips = preliminary_ips[: settings.top_k]
        final_decision = "llm_reviewed" if parse_meta.get("parse_success") else "llm_parse_failed_keep_preliminary"
        reasoning = "Local LLM reviewed the preliminary ranking under the legal candidate constraint."
        llm_meta.update(
            {
                "backend": llm_backend,
                "executed": True,
                "raw_response": llm_response,
                "parse": parse_meta,
                "rejected_out_of_scope_ips": rejected,
            }
        )

    plan["llm"] = llm_meta
    plan["final_decision"] = final_decision
    plan["final_ranking"] = final_ips
    # Compatibility with the existing Score_N evaluator.
    plan["skill_ips"] = final_ips
    plan["response"] = _response_json(final_decision, final_ips, reasoning)
    prompt = plan.pop("_llm_prompt", None)
    if settings.save_prompts and prompt:
        plan["prompt"] = prompt
    return plan


def run_variant(
    *,
    data_root: str,
    output_dir: str,
    variant: str,
    settings: PipelineSettings | None = None,
    llm_backend: str = "none",
    reviewer: LocalVllmReviewer | None = None,
    max_cases: int | None = None,
) -> str:
    settings = settings or PipelineSettings()
    if llm_backend not in {"none", "vllm"}:
        raise ValueError("llm_backend must be 'none' or 'vllm'")
    if llm_backend == "vllm" and reviewer is None:
        raise ValueError("A LocalVllmReviewer is required for the vllm backend")

    started = time.time()
    case_dirs = discover_case_dirs(data_root)
    if max_cases is not None:
        case_dirs = case_dirs[:max_cases]

    plans: list[dict[str, Any]] = []
    for case_dir in case_dirs:
        try:
            plans.append(build_case_plan(case_dir, variant, settings))
        except Exception as exc:
            plans.append(
                {
                    "schema_version": RESULT_SCHEMA_VERSION,
                    "dir": case_dir,
                    "case_id": os.path.basename(os.path.normpath(case_dir)),
                    "ablation": variant,
                    "error": f"{type(exc).__name__}: {exc}",
                    "skill_ips": [],
                    "response": _response_json("pipeline_error", [], str(exc)),
                    "_llm_prompt": None,
                }
            )

    llm_indices = [index for index, plan in enumerate(plans) if plan.get("_llm_prompt")]
    llm_responses: dict[int, str] = {}
    if llm_backend == "vllm" and llm_indices:
        prompts = [plans[index]["_llm_prompt"] for index in llm_indices]
        outputs = reviewer.review_batch(prompts, batch_size=settings.llm_batch_size)
        llm_responses = {index: output for index, output in zip(llm_indices, outputs)}

    results = [
        finalize_case_plan(
            plan,
            settings=settings,
            llm_backend=llm_backend,
            llm_response=llm_responses.get(index),
        )
        if "confidence_gate" in plan
        else {key: value for key, value in plan.items() if key != "_llm_prompt"}
        for index, plan in enumerate(plans)
    ]

    os.makedirs(output_dir, exist_ok=True)
    result_path = os.path.join(output_dir, "res.json")
    with open(result_path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)
    manifest = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "variant": variant,
        "settings": asdict(settings),
        "llm_backend": llm_backend,
        "case_count": len(results),
        "elapsed_seconds": round(time.time() - started, 3),
        "result_path": os.path.abspath(result_path),
        "inference_reads_labels": False,
    }
    with open(os.path.join(output_dir, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    return result_path
