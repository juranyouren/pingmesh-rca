#!/usr/bin/env python3
"""Run selective and forced-all-LLM ablations from precomputed evidence.

Inference never reads labels.  ``Sys.Score.Score_N`` is invoked only after all
predictions have been materialized in ``res.json``.
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

os.environ.setdefault("VLLM_WORKER_MULTIPROC_METHOD", "spawn")
os.environ.setdefault("OMP_NUM_THREADS", "1")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from prompts.ablation_rca import (
    ABLATION_RCA_PROMPT,
    ABLATION_RCA_PROMPT_VERSION,
    ALL_LLM_EVIDENCE_PROMPT,
    ALL_LLM_EVIDENCE_PROMPT_VERSION,
    ALL_LLM_RERANK_PROMPT,
    ALL_LLM_RERANK_PROMPT_VERSION,
)
from Sys.RootCauseAnalyze.skills.topo_ranker import score_topo, topo_details
from Sys.RootCauseAnalyze.trust_trees.router import route_with_trust_trees
from Sys.RootCauseAnalyze.trust_trees.temporal_tree import assess_temporal_tree
from Sys.RootCauseAnalyze.trust_trees.topo_tree import assess_topo_tree
from Sys.utils.case_utils import get_device_ip, load_case_info, load_case_nodes
from Sys.utils.ranking_utils import sorted_score_items
from scripts.build_evidence_tables import case_key, discover_cases


ALL_LLM_MODES = ("m123_all_llm_rerank", "m123_all_llm_evidence")
MODES = ("m1", "m13", "m23", "m123", *ALL_LLM_MODES)
_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)
FAULT_INFO_KEYS = (
    "alarm_name",
    "alarm_time",
    "analysis_from_time",
    "analysis_to_time",
    "source_ip",
    "sink_ip",
    "src_tunnel_ip",
    "dst_tunnel_ip",
    "scenario_code",
    "analysis_type",
    "task_num",
    "alarm_description",
)


def _pipeline_mode(mode: str) -> str:
    """Return the algorithmic pipeline shared by a public experiment mode."""
    return "m123" if mode in ALL_LLM_MODES else mode


def _prompt_variant(mode: str) -> str:
    if mode == "m123_all_llm_rerank":
        return "rerank"
    if mode == "m123_all_llm_evidence":
        return "evidence_judge"
    return "selective"


def _prompt_version(mode: str) -> str:
    if mode == "m123_all_llm_rerank":
        return ALL_LLM_RERANK_PROMPT_VERSION
    if mode == "m123_all_llm_evidence":
        return ALL_LLM_EVIDENCE_PROMPT_VERSION
    return ABLATION_RCA_PROMPT_VERSION


def _prompt_template(mode: str) -> str:
    if mode == "m123_all_llm_rerank":
        return ALL_LLM_RERANK_PROMPT
    if mode == "m123_all_llm_evidence":
        return ALL_LLM_EVIDENCE_PROMPT
    return ABLATION_RCA_PROMPT


def _save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_jsonl(rows: Iterable[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _ips(rows: Sequence[Dict[str, Any]], limit: int | None = None) -> List[str]:
    values = [row.get("ip") for row in rows if isinstance(row, dict) and row.get("ip")]
    return values[:limit] if limit is not None else values


def _fault_info_view(info: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: info[key]
        for key in FAULT_INFO_KEYS
        if key in info and info[key] not in (None, "", "[]", "--")
    }


def build_evidence_ranking(
    evidence_table: Dict[str, Any], candidate_ips: Sequence[str]
) -> tuple[Dict[str, float], Dict[str, Any]]:
    """Rank candidates using only deterministic values stored in the table."""
    row_by_ip = {
        row.get("candidate_ip"): row
        for row in evidence_table.get("rows", [])
        if isinstance(row, dict) and row.get("candidate_ip")
    }
    raw_scores = {
        ip: float((row_by_ip.get(ip, {}).get("temporal") or {}).get("raw_temporal_score", 0.0) or 0.0)
        for ip in candidate_ips
    }
    max_score = max(raw_scores.values(), default=0.0)
    normalized = {
        ip: (score / max_score if max_score > 0 else 0.0)
        for ip, score in raw_scores.items()
    }
    rankings: List[Dict[str, Any]] = []
    for rank, (ip, score) in enumerate(sorted_score_items(normalized), 1):
        row = row_by_ip.get(ip, {})
        temporal = row.get("temporal") or {}
        rankings.append(
            {
                "rank": rank,
                "ip": ip,
                "score": round(float(score), 6),
                "total_alarms": int(row.get("alarm_count", 0) or 0),
                "total_logs": int(row.get("log_count", 0) or 0),
                **temporal,
            }
        )

    def top3_by(key: str) -> List[str]:
        return [
            ip
            for ip, _value in sorted(
                (
                    (
                        ip,
                        float((row_by_ip.get(ip, {}).get("temporal") or {}).get(key, 0.0) or 0.0),
                    )
                    for ip in candidate_ips
                ),
                key=lambda item: (-item[1], item[0]),
            )[:3]
        ]

    base_diagnostics = evidence_table.get("temporal_diagnostics") or {}
    diagnostics = {
        "source": "precomputed_evidence_table",
        "ref_time_ms": base_diagnostics.get("ref_time_ms"),
        "devices_with_timestamps": sum(
            1
            for ip in candidate_ips
            if float(
                (row_by_ip.get(ip, {}).get("temporal") or {}).get("timestamp_count", 0)
                or 0
            )
            > 0
        ),
        "burst_top3": top3_by("burst_score"),
        "early_top3": top3_by("early_bird_score"),
        "density_top3": top3_by("density_score"),
    }
    detail = {
        "num_devices_scored": len(candidate_ips),
        "top3": rankings[:3],
        "topk": rankings,
        "rankings": rankings,
        "diagnostics": diagnostics,
    }
    detail["trust_tree"] = assess_temporal_tree(detail)
    return normalized, detail


def _load_evidence_index(evidence_root: Path) -> tuple[Dict[str, Dict[str, Any]], float]:
    manifest_path = evidence_root / "manifest.json"
    timing_path = evidence_root / "timing.json"
    if not manifest_path.exists() or not timing_path.exists():
        raise FileNotFoundError(
            f"precomputed evidence is incomplete under {evidence_root}; "
            "manifest.json and timing.json are required"
        )
    manifest = _load_json(manifest_path)
    timing = _load_json(timing_path)
    index = {
        os.path.normcase(os.path.abspath(item["dir"])): item
        for item in manifest.get("cases", [])
        if isinstance(item, dict) and item.get("dir") and item.get("case_id")
    }
    average = float(timing.get("average_seconds_per_device", 0.0) or 0.0)
    return index, average


def _load_case_evidence(
    dirpath: str,
    evidence_root: Path,
    evidence_index: Dict[str, Dict[str, Any]],
    data_root: str,
) -> Dict[str, Any]:
    normalized = os.path.normcase(os.path.abspath(dirpath))
    item = evidence_index.get(normalized)
    cid = item.get("case_id") if item else case_key(dirpath, data_root)
    path = evidence_root / "cases" / cid / "evidence_table.json"
    if not path.exists():
        raise FileNotFoundError(f"evidence table missing for {dirpath}: {path}")
    table = _load_json(path)
    if table.get("source_dir") and os.path.normcase(os.path.abspath(table["source_dir"])) != normalized:
        raise ValueError(f"evidence source mismatch for {dirpath}: {table.get('source_dir')}")
    return table


def _single_source_gate(
    *, method: str, tree: Dict[str, Any], ranking: Sequence[str]
) -> Dict[str, Any]:
    state = tree.get("state", "weak")
    confidence = {"strong": "high", "uncertain": "medium", "weak": "low"}.get(
        state, "low"
    )
    invoke = confidence != "high"
    return {
        "enabled": True,
        "confidence": confidence,
        "decision": "invoke_llm" if invoke else "bypass_llm",
        "route": "llm" if invoke else method,
        "reason": f"single_{method}_{state}",
        "recommended_ips": list(ranking[:5]),
        "trust_trees": {method: tree},
    }


def assess_ablation_gate(
    *,
    mode: str,
    initial_ranking: Sequence[str],
    topo_detail: Dict[str, Any] | None,
    temporal_detail: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Map old trust-tree states to explicit high/medium/low confidence."""
    if mode == "m1":
        return {
            "enabled": False,
            "confidence": "not_applicable",
            "decision": "bypass_llm",
            "route": "topo",
            "reason": "m1_direct_pagerank",
            "recommended_ips": list(initial_ranking[:5]),
            "trust_trees": {},
        }
    if mode == "m13":
        return _single_source_gate(
            method="topo",
            tree=assess_topo_tree(topo_detail or {}),
            ranking=initial_ranking,
        )
    if mode == "m23":
        return _single_source_gate(
            method="evidence",
            tree=assess_temporal_tree(temporal_detail or {}),
            ranking=initial_ranking,
        )

    topo_tree = assess_topo_tree(topo_detail or {})
    temporal_tree = assess_temporal_tree(temporal_detail or {})
    topo_ips = _ips((topo_detail or {}).get("rankings", []), 5)
    temporal_ips = _ips((temporal_detail or {}).get("rankings", []), 5)
    routed = route_with_trust_trees(
        combined_ips=list(initial_ranking[:5]),
        topo_ips=topo_ips,
        temporal_ips=temporal_ips,
        topo_tree=topo_tree,
        temporal_tree=temporal_tree,
    )
    if routed.get("decision") == "bypass_llm":
        confidence = "high"
    elif topo_tree.get("state") == "weak" and temporal_tree.get("state") == "weak":
        confidence = "low"
    else:
        confidence = "medium"
    invoke = confidence != "high"
    recommended = routed.get("recommended_ips") or list(initial_ranking[:5])
    return {
        **routed,
        "confidence": confidence,
        "decision": "invoke_llm" if invoke else "bypass_llm",
        "route": "llm" if invoke else routed.get("route", "combined"),
        "recommended_ips": recommended,
        "legacy_trust_tree_decision": routed.get("decision"),
    }


def _project_evidence_row(row: Dict[str, Any], mode: str) -> Dict[str, Any]:
    mode = _pipeline_mode(mode)
    projected = {
        "candidate_ip": row.get("candidate_ip"),
        "role": row.get("role", "UNKNOWN"),
        "alarm_count": row.get("alarm_count", 0),
        "log_count": row.get("log_count", 0),
        "high_weight_alarms": row.get("high_weight_alarms", []),
        "neighbor_alarm_statistics": row.get("neighbor_alarm_statistics", {}),
        "semantic_summary": row.get("semantic_summary", ""),
        "summary_context": row.get("summary_context", {}),
    }
    if mode in ("m23", "m123"):
        projected["temporal"] = row.get("temporal", {})
    if mode == "m123":
        projected["cross"] = row.get("cross", 0)
        topology = row.get("topology") or {}
        projected["topology"] = {
            "upstream": list(topology.get("upstream", []) or [])[:10],
            "downstream": list(topology.get("downstream", []) or [])[:10],
        }
    return projected


def _make_bypass_response(gate: Dict[str, Any], initial_ranking: Sequence[str]) -> str:
    allowed = set(initial_ranking)
    recommended = [ip for ip in gate.get("recommended_ips", []) if ip in allowed]
    ips = (recommended or list(initial_ranking))[:5]
    payload = {
        "decision": "gate_accept",
        "reasoning": (
            f"Gate confidence={gate.get('confidence')}; "
            f"route={gate.get('route')}; reason={gate.get('reason')}"
        ),
        "ip": ips,
    }
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"


def constrain_llm_response(
    raw_response: str, allowed_candidates: Sequence[str]
) -> tuple[str, Dict[str, Any]]:
    """Filter model IPs to the predeclared candidate set; preserve raw separately."""
    allowed = list(dict.fromkeys(allowed_candidates))
    allowed_set = set(allowed)
    parsed: Dict[str, Any] = {}
    parse_success = False
    blocks = _JSON_BLOCK.findall(raw_response or "")
    candidates = [*reversed(blocks), raw_response or ""]
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            parsed = value
            parse_success = True
            break
    raw_ips = parsed.get("ip", []) if parsed else []
    if isinstance(raw_ips, str):
        raw_ips = [raw_ips]
    if not isinstance(raw_ips, list):
        raw_ips = []
    valid_ips: List[str] = []
    rejected_ips: List[str] = []
    for value in raw_ips:
        ip = str(value) if value is not None else ""
        if ip in allowed_set and ip not in valid_ips:
            valid_ips.append(ip)
        elif ip and ip not in rejected_ips:
            rejected_ips.append(ip)
    used_fallback = not valid_ips
    if used_fallback:
        valid_ips = allowed[:5]
    payload = {
        "decision": parsed.get("decision", "insufficient_evidence"),
        "reasoning": parsed.get(
            "reasoning",
            "Model output could not be parsed or contained no legal candidate; initial ranking retained.",
        ),
        "ip": valid_ips[:5],
    }
    audit = {
        "parse_success": parse_success,
        "parsed_payload": parsed,
        "raw_ips": raw_ips,
        "rejected_ips": rejected_ips,
        "used_initial_ranking_fallback": used_fallback,
        "output_was_filtered": bool(rejected_ips) or used_fallback,
    }
    return (
        "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```",
        audit,
    )


def _ranking_evidence(
    mode: str,
    initial_rows: Sequence[Dict[str, Any]],
    topo_detail: Dict[str, Any] | None,
    temporal_detail: Dict[str, Any] | None,
    top_k: int,
) -> Dict[str, Any]:
    mode = _pipeline_mode(mode)
    result: Dict[str, Any] = {
        "initial_ranking": list(initial_rows[:top_k]),
        "allowed_candidate_ips": _ips(initial_rows, top_k),
    }
    if mode in ("m13", "m123"):
        result["pagerank"] = {
            "rankings": (topo_detail or {}).get("rankings", [])[:top_k],
            "diagnostics": (topo_detail or {}).get("diagnostics", {}),
        }
    if mode in ("m23", "m123"):
        result["evidence_ranking"] = {
            "rankings": (temporal_detail or {}).get("rankings", [])[:top_k],
            "diagnostics": (temporal_detail or {}).get("diagnostics", {}),
        }
    return result


def _build_llm_prompt(
    *,
    mode: str,
    info: Dict[str, Any],
    gate: Dict[str, Any],
    ranking_evidence: Dict[str, Any],
    evidence_rows: Sequence[Dict[str, Any]],
) -> str:
    if mode == "m123_all_llm_evidence":
        pagerank_rows = (
            (ranking_evidence.get("pagerank") or {}).get("rankings", [])
        )
        pagerank_by_ip = {
            row.get("ip"): {
                key: value
                for key, value in row.items()
                if key not in {"rank", "combined_score", "evidence_score"}
            }
            for row in pagerank_rows
            if isinstance(row, dict) and row.get("ip")
        }
        allowed = sorted(ranking_evidence.get("allowed_candidate_ips", []))
        pagerank_evidence = {
            "allowed_candidate_ips": allowed,
            "pagerank_features": [
                {"ip": ip, **pagerank_by_ip.get(ip, {})}
                for ip in allowed
            ],
        }
        rows_by_ip = {
            row.get("candidate_ip"): row
            for row in evidence_rows
            if isinstance(row, dict) and row.get("candidate_ip")
        }
        ordered_rows = [
            rows_by_ip.get(ip, {"candidate_ip": ip})
            for ip in allowed
        ]
        return ALL_LLM_EVIDENCE_PROMPT.format(
            FAULT_INFO=json.dumps(_fault_info_view(info), ensure_ascii=False, indent=2),
            PAGERANK_EVIDENCE=json.dumps(
                pagerank_evidence, ensure_ascii=False, indent=2
            ),
            EVIDENCE_ROWS=json.dumps(ordered_rows, ensure_ascii=False, indent=2),
        )

    gate_context = {
        "confidence": gate.get("confidence"),
        "reason": gate.get("reason"),
        "trust_states": {
            name: tree.get("state")
            for name, tree in (gate.get("trust_trees") or {}).items()
            if isinstance(tree, dict)
        },
        "allowed_candidate_ips": ranking_evidence.get("allowed_candidate_ips", []),
    }
    template = (
        ALL_LLM_RERANK_PROMPT
        if mode == "m123_all_llm_rerank"
        else ABLATION_RCA_PROMPT
    )
    return template.format(
        MODE=mode.upper(),
        GATE_CONTEXT=json.dumps(gate_context, ensure_ascii=False, indent=2),
        FAULT_INFO=json.dumps(_fault_info_view(info), ensure_ascii=False, indent=2),
        RANKING_EVIDENCE=json.dumps(ranking_evidence, ensure_ascii=False, indent=2),
        EVIDENCE_ROWS=json.dumps(list(evidence_rows), ensure_ascii=False, indent=2),
    )


def build_case_plan(
    *,
    mode: str,
    dirpath: str,
    data_root: str,
    evidence_table: Dict[str, Any] | None,
    evidence_average_seconds: float,
    top_k: int,
    weight_file: str | None,
) -> Dict[str, Any]:
    started = time.perf_counter()
    pipeline_mode = _pipeline_mode(mode)
    nodes = load_case_nodes(dirpath)
    info = load_case_info(dirpath)
    node_by_ip = {
        get_device_ip(node): node
        for node in nodes
        if get_device_ip(node) not in ("", "unknown")
    }
    all_ips = sorted(node_by_ip)
    effective_k = min(top_k, len(all_ips))

    topo_detail: Dict[str, Any] | None = None
    topo_scores: Dict[str, float] = {}
    topo_candidates: List[str] = []
    topo_seconds = 0.0
    if pipeline_mode in ("m1", "m13", "m123"):
        stage = time.perf_counter()
        raw_topo_scores = score_topo(nodes, info, weight_path=weight_file, directed=True)
        if pipeline_mode == "m1" and raw_topo_scores:
            pure_rankings = [
                {"rank": rank, "ip": ip, "pr_score": round(float(score), 6)}
                for rank, (ip, score) in enumerate(
                    sorted_score_items(raw_topo_scores, effective_k), 1
                )
            ]
            topo_detail = {
                "num_devices_scored": len(raw_topo_scores),
                "top3": pure_rankings[:3],
                "topk": pure_rankings,
                "rankings": pure_rankings,
                "diagnostics": {
                    "pagerank_available": True,
                    "directed_top3": _ips(pure_rankings, 3),
                    "undirected_top3": [],
                    "pure_m1": True,
                },
            }
        else:
            topo_detail = topo_details(
                nodes,
                info,
                raw_topo_scores,
                weight_path=weight_file,
                directed=True,
                top_k=effective_k,
            )
        topo_scores = raw_topo_scores or {
            row["ip"]: float(row.get("pr_score", 0.0))
            for row in topo_detail.get("rankings", [])
            if row.get("ip")
        }
        topo_candidates = _ips(topo_detail.get("rankings", []), effective_k)
        topo_seconds = time.perf_counter() - stage

    candidate_ips = all_ips if pipeline_mode == "m23" else topo_candidates
    temporal_detail: Dict[str, Any] | None = None
    temporal_scores: Dict[str, float] = {}
    evidence_rank_seconds = 0.0
    if pipeline_mode in ("m23", "m123"):
        stage = time.perf_counter()
        if evidence_table is None:
            raise ValueError(f"{mode} requires a precomputed evidence table")
        temporal_scores, temporal_detail = build_evidence_ranking(
            evidence_table, candidate_ips
        )
        evidence_rank_seconds = time.perf_counter() - stage

    if pipeline_mode in ("m1", "m13"):
        initial_rows = list((topo_detail or {}).get("rankings", []))
    elif pipeline_mode == "m23":
        initial_rows = list((temporal_detail or {}).get("rankings", []))
    else:
        combined_scores = {
            ip: (float(topo_scores.get(ip, 0.0)) + float(temporal_scores.get(ip, 0.0))) / 2.0
            for ip in candidate_ips
        }
        initial_rows = [
            {
                "rank": rank,
                "ip": ip,
                "combined_score": round(score, 6),
                "pagerank_score": round(float(topo_scores.get(ip, 0.0)), 6),
                "evidence_score": round(float(temporal_scores.get(ip, 0.0)), 6),
            }
            for rank, (ip, score) in enumerate(
                sorted_score_items(combined_scores, effective_k), 1
            )
        ]
    initial_ips = _ips(initial_rows)

    gate_started = time.perf_counter()
    gate = assess_ablation_gate(
        mode=pipeline_mode,
        initial_ranking=initial_ips,
        topo_detail=topo_detail,
        temporal_detail=temporal_detail,
    )
    if mode in ALL_LLM_MODES:
        gate = {
            **gate,
            "natural_decision": gate.get("decision"),
            "natural_route": gate.get("route"),
            "forced_llm": True,
            "decision": "invoke_llm",
            "route": "llm",
        }
    gate_seconds = time.perf_counter() - gate_started

    table_rows = (evidence_table or {}).get("rows", [])
    row_by_ip = {
        row.get("candidate_ip"): row
        for row in table_rows
        if isinstance(row, dict) and row.get("candidate_ip")
    }
    allowed_ips = initial_ips[:effective_k]
    projected_rows = [
        _project_evidence_row(row_by_ip.get(ip, {"candidate_ip": ip}), pipeline_mode)
        for ip in allowed_ips
    ]
    ranking = _ranking_evidence(
        pipeline_mode, initial_rows, topo_detail, temporal_detail, effective_k
    )
    prompt = ""
    if gate.get("decision") == "invoke_llm":
        prompt = _build_llm_prompt(
            mode=mode,
            info=info,
            gate=gate,
            ranking_evidence=ranking,
            evidence_rows=projected_rows,
        )

    if pipeline_mode == "m1":
        evidence_devices = 0
    elif pipeline_mode == "m23":
        evidence_devices = len(all_ips)
    else:
        evidence_devices = len(topo_candidates)
    estimated_evidence_seconds = evidence_devices * evidence_average_seconds
    cid = (
        evidence_table.get("case_id")
        if evidence_table and evidence_table.get("case_id")
        else case_key(dirpath, data_root)
    )
    return {
        "case_id": cid,
        "dir": dirpath,
        "mode": mode,
        "pipeline_mode": pipeline_mode,
        "prompt_variant": _prompt_variant(mode),
        "prompt_version": _prompt_version(mode),
        "device_count": len(all_ips),
        "evidence_device_count": evidence_devices,
        "initial_ranking": initial_ips,
        "initial_rows": initial_rows,
        "topo_detail": topo_detail,
        "temporal_detail": temporal_detail,
        "ranking_evidence": ranking,
        "evidence_rows_for_llm": projected_rows,
        "gate": gate,
        "prompt": prompt,
        "runtime": {
            "pagerank_seconds": topo_seconds,
            "evidence_ranking_seconds": evidence_rank_seconds,
            "gate_seconds": gate_seconds,
            "plan_seconds": time.perf_counter() - started,
            "evidence_estimated_seconds": estimated_evidence_seconds,
        },
    }


def _chunk_evenly(items: Sequence[Any], count: int) -> List[List[Any]]:
    chunks: List[List[Any]] = [[] for _ in range(count)]
    for index, item in enumerate(items):
        chunks[index % count].append(item)
    return chunks


def _llm_worker(spec: Dict[str, Any]) -> Dict[str, Any]:
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = spec["npu_group"]
    from vllm import LLM, SamplingParams

    worker_started = time.perf_counter()
    cards = [part for part in spec["npu_group"].split(",") if part.strip()]
    init_started = time.perf_counter()
    llm = LLM(
        model=spec["model_path"],
        tensor_parallel_size=len(cards),
        gpu_memory_utilization=spec["gpu_memory_utilization"],
        max_model_len=spec["max_model_len"],
        max_num_seqs=spec["max_num_seqs"],
        trust_remote_code=True,
    )
    sampling = SamplingParams(
        temperature=spec["temperature"],
        top_p=spec["top_p"],
        max_tokens=spec["max_tokens"],
        repetition_penalty=spec["repetition_penalty"],
    )
    init_seconds = time.perf_counter() - init_started
    records: List[Dict[str, Any]] = []
    inference_seconds = 0.0
    tokenizer = None
    for offset in range(0, len(spec["tasks"]), spec["batch_size"]):
        batch = spec["tasks"][offset : offset + spec["batch_size"]]
        applied = [[{"role": "user", "content": item["prompt"]}] for item in batch]
        started = time.perf_counter()
        outputs = llm.chat(applied, sampling)
        batch_seconds = time.perf_counter() - started
        inference_seconds += batch_seconds
        amortized = batch_seconds / max(len(batch), 1)
        for task, messages, output in zip(batch, applied, outputs):
            completion = output.outputs[0]
            prompt_token_ids = getattr(output, "prompt_token_ids", None)
            completion_token_ids = getattr(completion, "token_ids", None)
            token_count_source = "vllm_token_ids"
            if prompt_token_ids is None or completion_token_ids is None:
                if tokenizer is None:
                    tokenizer = llm.get_tokenizer()
                token_count_source = "tokenizer_fallback"
            if prompt_token_ids is None:
                try:
                    prompt_token_ids = tokenizer.apply_chat_template(
                        messages, tokenize=True, add_generation_prompt=True
                    )
                except (AttributeError, TypeError, ValueError):
                    prompt_token_ids = tokenizer.encode(
                        task["prompt"], add_special_tokens=True
                    )
            if completion_token_ids is None:
                completion_token_ids = tokenizer.encode(
                    completion.text, add_special_tokens=False
                )
            prompt_tokens = len(prompt_token_ids)
            completion_tokens = len(completion_token_ids)
            records.append(
                {
                    "case_id": task["case_id"],
                    "raw_response": completion.text.strip(),
                    "worker_id": spec["worker_id"],
                    "npu_group": spec["npu_group"],
                    "amortized_batch_inference_seconds": amortized,
                    "token_usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                        "source": token_count_source,
                    },
                }
            )
    part_path = Path(spec["part_path"])
    _write_jsonl(records, part_path)
    del llm
    gc.collect()
    return {
        "worker_id": spec["worker_id"],
        "npu_group": spec["npu_group"],
        "task_count": len(spec["tasks"]),
        "model_init_seconds": init_seconds,
        "inference_seconds": inference_seconds,
        "worker_wall_seconds": time.perf_counter() - worker_started,
        "prompt_tokens": sum(
            record["token_usage"]["prompt_tokens"] for record in records
        ),
        "completion_tokens": sum(
            record["token_usage"]["completion_tokens"] for record in records
        ),
        "total_tokens": sum(
            record["token_usage"]["total_tokens"] for record in records
        ),
        "part_path": str(part_path),
    }


def _run_llm_tasks(
    tasks: Sequence[Dict[str, Any]], args: argparse.Namespace, run_dir: Path
) -> tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]], float]:
    if not tasks:
        return {}, [], 0.0
    groups = [group.strip() for group in args.npu_groups.split(";") if group.strip()]
    if not groups:
        raise ValueError("--npu-groups must contain at least one tensor-parallel group")
    chunks = _chunk_evenly(tasks, min(len(groups), len(tasks)))
    specs = []
    part_dir = run_dir / "_llm_worker_parts"
    for index, (group, chunk) in enumerate(zip(groups, chunks), 1):
        if not chunk:
            continue
        specs.append(
            {
                "worker_id": index,
                "npu_group": group,
                "tasks": chunk,
                "part_path": str(part_dir / f"worker_{index}.jsonl"),
                "model_path": args.model_path,
                "batch_size": args.batch_size,
                "max_num_seqs": args.max_num_seqs,
                "max_model_len": args.max_model_len,
                "max_tokens": args.max_tokens,
                "temperature": args.temperature,
                "top_p": args.top_p,
                "repetition_penalty": args.repetition_penalty,
                "gpu_memory_utilization": args.gpu_memory_utilization,
            }
        )
    import multiprocessing as mp

    stage_started = time.perf_counter()
    stats: List[Dict[str, Any]] = []
    with ProcessPoolExecutor(
        max_workers=len(specs), mp_context=mp.get_context("spawn")
    ) as executor:
        futures = [executor.submit(_llm_worker, spec) for spec in specs]
        for future in as_completed(futures):
            stats.append(future.result())
    wall_seconds = time.perf_counter() - stage_started
    records: List[Dict[str, Any]] = []
    for stat in sorted(stats, key=lambda item: item["worker_id"]):
        records.extend(_read_jsonl(Path(stat["part_path"])))
    result = {record["case_id"]: record for record in records}
    if len(result) != len(tasks):
        raise RuntimeError(f"LLM output count mismatch: expected {len(tasks)}, got {len(result)}")
    return result, sorted(stats, key=lambda item: item["worker_id"]), wall_seconds


def _summarize_token_usage(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    per_case = []
    for result in results:
        usage = result.get("token_usage") or {}
        if not result.get("reran_with_llm"):
            continue
        per_case.append(
            {
                "case_id": result.get("case_id"),
                "prompt_variant": result.get("prompt_variant"),
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
                "source": usage.get("source", "unknown"),
            }
        )
    per_case.sort(key=lambda item: str(item["case_id"]))
    count = len(per_case)
    prompt_total = sum(item["prompt_tokens"] for item in per_case)
    completion_total = sum(item["completion_tokens"] for item in per_case)
    total = sum(item["total_tokens"] for item in per_case)
    return {
        "llm_case_count": count,
        "prompt_tokens": {
            "total": prompt_total,
            "average_per_llm_case": prompt_total / count if count else 0.0,
        },
        "completion_tokens": {
            "total": completion_total,
            "average_per_llm_case": completion_total / count if count else 0.0,
        },
        "total_tokens": {
            "total": total,
            "average_per_llm_case": total / count if count else 0.0,
        },
        "per_case": per_case,
    }


def _rank_diff(initial: Sequence[str], final: Sequence[str]) -> Dict[str, Any]:
    initial_top5 = list(initial[:5])
    final_top5 = list(final[:5])
    all_ips = list(dict.fromkeys([*initial_top5, *final_top5]))
    movements = []
    for ip in all_ips:
        old_rank = initial_top5.index(ip) + 1 if ip in initial_top5 else None
        new_rank = final_top5.index(ip) + 1 if ip in final_top5 else None
        movements.append(
            {
                "ip": ip,
                "initial_rank": old_rank,
                "final_rank": new_rank,
                "rank_delta": (
                    old_rank - new_rank
                    if old_rank is not None and new_rank is not None
                    else None
                ),
            }
        )
    return {
        "initial_top5": initial_top5,
        "final_top5": final_top5,
        "changed_top1": initial_top5[:1] != final_top5[:1],
        "changed_order": initial_top5 != final_top5,
        "added_to_top5": [ip for ip in final_top5 if ip not in initial_top5],
        "removed_from_top5": [ip for ip in initial_top5 if ip not in final_top5],
        "movements": movements,
    }


def _badcase_labels(
    *,
    initial_eval: Dict[str, Any],
    final_eval: Dict[str, Any],
    candidate_hit: bool,
    output_filter: Dict[str, Any],
    gate: Dict[str, Any],
    topo_top1: str | None,
    evidence_top1: str | None,
) -> Dict[str, Any]:
    tags: List[str] = []
    if not output_filter.get("parse_success", True) or output_filter.get(
        "used_initial_ranking_fallback", False
    ):
        tags.append("output_parse_failure")
    if not candidate_hit:
        tags.append("candidate_miss")
    if initial_eval.get("top1_hit") and not final_eval.get("top1_hit"):
        tags.append("llm_harm")
    if not initial_eval.get("top1_hit") and not final_eval.get("top1_hit"):
        tags.append("persistent_failure")
        if candidate_hit:
            tags.append("llm_failed_to_correct")
    if gate.get("confidence") == "high":
        tags.append("gate_overconfidence")
    if topo_top1 and evidence_top1 and topo_top1 != evidence_top1:
        tags.append("evidence_conflict")

    priority = (
        "output_parse_failure",
        "candidate_miss",
        "llm_harm",
        "llm_failed_to_correct",
        "persistent_failure",
    )
    primary = next((label for label in priority if label in tags), "persistent_failure")
    return {
        "primary_error_type": primary,
        "secondary_tags": [tag for tag in tags if tag != primary],
    }


def _write_badcase_index(rows: Sequence[Dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "case_id",
        "source_dir",
        "primary_error_type",
        "secondary_tags",
        "gate_confidence",
        "initial_top1",
        "final_top1",
        "ground_truth_ips",
        "best_final_rank",
        "prompt_tokens",
        "completion_tokens",
        "badcase_dir",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_all_llm_evaluation_artifacts(
    *,
    mode: str,
    plans: Sequence[Dict[str, Any]],
    results: Sequence[Dict[str, Any]],
    run_dir: Path,
    evidence_root: Path,
) -> Dict[str, Any]:
    """Write label-aware diagnostics only after inference has fully completed."""
    from Sys.Score.Score_N import Prediction, Scorer

    scorer = Scorer(str(run_dir / "res.json"))
    plans_by_id = {plan["case_id"]: plan for plan in plans}
    transition_counts = {
        "correct_to_correct": 0,
        "correct_to_wrong": 0,
        "wrong_to_correct": 0,
        "wrong_to_wrong": 0,
    }
    evaluated_cases = 0
    case_records: List[Dict[str, Any]] = []
    badcase_index: List[Dict[str, Any]] = []

    for result in results:
        case_id = result["case_id"]
        plan = plans_by_id[case_id]
        ground_truth = scorer._get_groundtruth(result["dir"])
        if not ground_truth.ips:
            case_records.append(
                {
                    "case_id": case_id,
                    "dir": result["dir"],
                    "prompt_variant": result.get("prompt_variant"),
                    "evaluation_status": "skipped_no_ground_truth",
                    "token_usage": result.get("token_usage", {}),
                }
            )
            continue

        evaluated_cases += 1
        initial_prediction = Prediction(ips=list(plan["initial_ranking"]))
        final_prediction = scorer.parser.parse(result.get("response", ""))
        initial_eval = scorer.evaluator.evaluate(ground_truth, initial_prediction)
        final_eval = scorer.evaluator.evaluate(ground_truth, final_prediction)
        initial_correct = bool(initial_eval.get("top1_hit"))
        final_correct = bool(final_eval.get("top1_hit"))
        transition = (
            ("correct" if initial_correct else "wrong")
            + "_to_"
            + ("correct" if final_correct else "wrong")
        )
        transition_counts[transition] += 1

        candidate_hit = any(
            ip in set(plan["initial_ranking"]) for ip in ground_truth.ips
        )
        topo_top1 = (_ips((plan.get("topo_detail") or {}).get("rankings", []), 1) or [None])[0]
        evidence_top1 = (
            _ips((plan.get("temporal_detail") or {}).get("rankings", []), 1)
            or [None]
        )[0]
        rank_diff = _rank_diff(plan["initial_ranking"], final_prediction.ips)
        labels = (
            _badcase_labels(
                initial_eval=initial_eval,
                final_eval=final_eval,
                candidate_hit=candidate_hit,
                output_filter=result.get("llm_output_filter") or {},
                gate=plan["gate"],
                topo_top1=topo_top1,
                evidence_top1=evidence_top1,
            )
            if not final_correct
            else {"primary_error_type": None, "secondary_tags": []}
        )
        evaluation = {
            "ground_truth_ips": ground_truth.ips,
            "ground_truth_source": ground_truth.source,
            "candidate_contains_ground_truth": candidate_hit,
            "initial": initial_eval,
            "final": final_eval,
            "transition": transition,
            **labels,
        }
        case_record = {
            "case_id": case_id,
            "dir": result["dir"],
            "prompt_variant": result.get("prompt_variant"),
            "prompt_version": result.get("prompt_version"),
            "gate_confidence": plan["gate"].get("confidence"),
            "gate_natural_decision": plan["gate"].get(
                "natural_decision", plan["gate"].get("decision")
            ),
            "forced_llm": bool(plan["gate"].get("forced_llm")),
            "baseline_ranking": list(plan["initial_ranking"]),
            "llm_ranking": list(final_prediction.ips),
            "rank_diff": rank_diff,
            "evaluation": evaluation,
            "token_usage": result.get("token_usage", {}),
            "runtime": result.get("runtime", {}),
        }
        case_records.append(case_record)
        if final_correct:
            continue

        badcase_dir = run_dir / "badcases" / case_id
        badcase_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_root / "cases" / case_id / "evidence_table.json"
        evidence_table = _load_json(evidence_path) if evidence_path.exists() else {
            "error": "precomputed evidence table not found",
            "expected_path": str(evidence_path),
        }
        parsed_payload = (
            result.get("llm_output_filter") or {}
        ).get("parsed_payload", {})
        rankings = {
            "baseline_ranking": plan["initial_ranking"],
            "baseline_rows": plan["initial_rows"],
            "pagerank": plan.get("topo_detail"),
            "evidence": plan.get("temporal_detail"),
        }
        source_refs = {
            "source_case_dir": result["dir"],
            "evidence_table_path": str(evidence_path),
            "prompt_path": str(run_dir / "llm_prompts" / f"{case_id}.txt"),
            "raw_output_path": str(
                run_dir / "llm_raw_outputs" / f"{case_id}.txt"
            ),
            "ground_truth_source": ground_truth.source,
        }
        overview = "\n".join(
            [
                f"# Bad case: {case_id}",
                "",
                f"- Prompt variant: `{result.get('prompt_variant')}`",
                f"- Primary error: `{labels['primary_error_type']}`",
                f"- Secondary tags: `{', '.join(labels['secondary_tags']) or 'none'}`",
                f"- Gate confidence: `{plan['gate'].get('confidence')}`",
                f"- Gate natural decision: `{plan['gate'].get('natural_decision')}`",
                f"- Ground truth: `{', '.join(ground_truth.ips)}`",
                f"- Baseline Top-5: `{', '.join(plan['initial_ranking'][:5])}`",
                f"- LLM Top-5: `{', '.join(final_prediction.ips[:5])}`",
                f"- Transition: `{transition}`",
                f"- Prompt tokens: `{(result.get('token_usage') or {}).get('prompt_tokens', 0)}`",
                f"- Completion tokens: `{(result.get('token_usage') or {}).get('completion_tokens', 0)}`",
                "",
                "按编号查看 Gate、两类排序、完整证据表、实际 Prompt、原始输出和解析结果。",
            ]
        )
        (badcase_dir / "00_overview.md").write_text(overview + "\n", encoding="utf-8")
        _save_json(evaluation, badcase_dir / "01_evaluation.json")
        _save_json(plan["gate"], badcase_dir / "02_gate.json")
        _save_json(rankings, badcase_dir / "03_rankings.json")
        _save_json(evidence_table, badcase_dir / "04_evidence_table.json")
        (badcase_dir / "05_prompt.txt").write_text(
            result.get("prompt", ""), encoding="utf-8"
        )
        (badcase_dir / "06_llm_raw_output.txt").write_text(
            result.get("llm_raw_response", ""), encoding="utf-8"
        )
        _save_json(parsed_payload, badcase_dir / "07_llm_parsed_output.json")
        _save_json(rank_diff, badcase_dir / "08_rank_diff.json")
        _save_json(
            {
                **(result.get("runtime") or {}),
                "token_usage": result.get("token_usage", {}),
            },
            badcase_dir / "09_timing.json",
        )
        _save_json(source_refs, badcase_dir / "10_source_refs.json")
        badcase_index.append(
            {
                "case_id": case_id,
                "source_dir": result["dir"],
                "primary_error_type": labels["primary_error_type"],
                "secondary_tags": "|".join(labels["secondary_tags"]),
                "gate_confidence": plan["gate"].get("confidence"),
                "initial_top1": plan["initial_ranking"][0]
                if plan["initial_ranking"]
                else "",
                "final_top1": final_prediction.ips[0] if final_prediction.ips else "",
                "ground_truth_ips": "|".join(ground_truth.ips),
                "best_final_rank": final_eval.get("best_rank") or "",
                "prompt_tokens": (result.get("token_usage") or {}).get(
                    "prompt_tokens", 0
                ),
                "completion_tokens": (result.get("token_usage") or {}).get(
                    "completion_tokens", 0
                ),
                "badcase_dir": str(badcase_dir),
            }
        )

    _write_jsonl(case_records, run_dir / "cases.jsonl")
    transition_summary = {
        "mode": mode,
        "evaluated_case_count": evaluated_cases,
        **transition_counts,
    }
    _save_json(transition_summary, run_dir / "transition_matrix.json")
    _write_badcase_index(badcase_index, run_dir / "badcase_index.csv")
    return {
        "evaluated_case_count": evaluated_cases,
        "badcase_count": len(badcase_index),
        "transition_matrix": transition_summary,
    }


def run_mode(
    *,
    mode: str,
    dirpaths: Sequence[str],
    args: argparse.Namespace,
    run_dir: Path,
    evidence_index: Dict[str, Dict[str, Any]],
    evidence_average_seconds: float,
) -> Dict[str, Any]:
    if run_dir.exists():
        raise FileExistsError(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    (run_dir / "prompt_template.txt").write_text(
        _prompt_template(mode), encoding="utf-8"
    )
    mode_started = time.perf_counter()
    plans: List[Dict[str, Any]] = []
    for index, dirpath in enumerate(dirpaths, 1):
        evidence_table = None
        if mode != "m1":
            evidence_table = _load_case_evidence(
                dirpath,
                Path(args.evidence_root),
                evidence_index,
                args.data_root,
            )
        plans.append(
            build_case_plan(
                mode=mode,
                dirpath=dirpath,
                data_root=args.data_root,
                evidence_table=evidence_table,
                evidence_average_seconds=evidence_average_seconds,
                top_k=args.top_k,
                weight_file=args.weight_file,
            )
        )
        if index % 20 == 0 or index == len(dirpaths):
            print(f"[{mode}] planned {index}/{len(dirpaths)} cases")

    _write_jsonl(plans, run_dir / "case_plans.jsonl")
    rerun_plans = [plan for plan in plans if plan["gate"].get("decision") == "invoke_llm"]
    confidence_counts: Dict[str, int] = {}
    natural_decision_counts: Dict[str, int] = {}
    for plan in plans:
        confidence = str(plan["gate"].get("confidence", "unknown"))
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1
        natural_decision = str(
            plan["gate"].get("natural_decision", plan["gate"].get("decision", "unknown"))
        )
        natural_decision_counts[natural_decision] = (
            natural_decision_counts.get(natural_decision, 0) + 1
        )
    for plan in rerun_plans:
        (run_dir / "llm_prompts").mkdir(parents=True, exist_ok=True)
        (run_dir / "llm_prompts" / f"{plan['case_id']}.txt").write_text(
            plan["prompt"], encoding="utf-8"
        )
    _save_json(
        {
            "mode": mode,
            "case_count": len(plans),
            "rerun_case_count": len(rerun_plans),
            "rerun_case_ids": [plan["case_id"] for plan in rerun_plans],
            "confidence_counts": confidence_counts,
            "natural_decision_counts": natural_decision_counts,
            "forced_llm": mode in ALL_LLM_MODES,
            "prompt_variant": _prompt_variant(mode),
            "prompt_version": _prompt_version(mode),
        },
        run_dir / "run_plan.json",
    )
    _save_json(
        {
            "mode": mode,
            "case_count": len(plans),
            "confidence_counts": confidence_counts,
            "natural_decision_counts": natural_decision_counts,
            "forced_llm": mode in ALL_LLM_MODES,
        },
        run_dir / "gate_distribution.json",
    )
    if args.plan_only:
        return {
            "mode": mode,
            "case_count": len(plans),
            "rerun_case_count": len(rerun_plans),
            "confidence_counts": confidence_counts,
            "prompt_variant": _prompt_variant(mode),
            "prompt_version": _prompt_version(mode),
            "plan_only": True,
            "run_dir": str(run_dir),
        }

    llm_tasks = [
        {"case_id": plan["case_id"], "prompt": plan["prompt"]}
        for plan in rerun_plans
    ]
    llm_results, worker_stats, llm_wall_seconds = _run_llm_tasks(
        llm_tasks, args, run_dir
    )
    llm_effective_per_case = (
        llm_wall_seconds / len(rerun_plans) if rerun_plans else 0.0
    )
    results: List[Dict[str, Any]] = []
    rerun_manifest: List[Dict[str, Any]] = []
    for plan in plans:
        reran = plan["case_id"] in llm_results
        if reran:
            llm_record = llm_results[plan["case_id"]]
            raw_response = llm_record["raw_response"]
            response, output_filter = constrain_llm_response(
                raw_response, plan["initial_ranking"]
            )
            response_dir = run_dir / "llm_raw_outputs"
            response_dir.mkdir(parents=True, exist_ok=True)
            response_path = response_dir / f"{plan['case_id']}.txt"
            response_path.write_text(raw_response, encoding="utf-8")
            rerun_manifest.append(
                {
                    "case_id": plan["case_id"],
                    "dir": plan["dir"],
                    "confidence": plan["gate"].get("confidence"),
                    "natural_decision": plan["gate"].get(
                        "natural_decision", plan["gate"].get("decision")
                    ),
                    "forced_llm": bool(plan["gate"].get("forced_llm")),
                    "reason": plan["gate"].get("reason"),
                    "prompt_variant": plan["prompt_variant"],
                    "prompt_version": plan["prompt_version"],
                    "prompt_path": str(run_dir / "llm_prompts" / f"{plan['case_id']}.txt"),
                    "response_path": str(response_path),
                    "token_usage": llm_record.get("token_usage", {}),
                }
            )
            plan["runtime"]["llm_batch_amortized_seconds"] = llm_record.get(
                "amortized_batch_inference_seconds", 0.0
            )
            plan["runtime"]["llm_effective_wall_seconds"] = llm_effective_per_case
            token_usage = llm_record.get(
                "token_usage",
                {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "source": "missing",
                },
            )
        else:
            response = _make_bypass_response(plan["gate"], plan["initial_ranking"])
            raw_response = ""
            output_filter = {
                "raw_ips": [],
                "rejected_ips": [],
                "used_initial_ranking_fallback": False,
                "output_was_filtered": False,
            }
            plan["runtime"]["llm_batch_amortized_seconds"] = 0.0
            plan["runtime"]["llm_effective_wall_seconds"] = 0.0
            token_usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "source": "not_invoked",
            }
        plan["runtime"]["estimated_case_total_seconds"] = (
            plan["runtime"]["plan_seconds"]
            + plan["runtime"]["evidence_estimated_seconds"]
            + plan["runtime"]["llm_effective_wall_seconds"]
        )
        results.append(
            {
                "dir": plan["dir"],
                "case_id": plan["case_id"],
                "ablation": mode,
                "prompt_variant": plan["prompt_variant"],
                "prompt_version": plan["prompt_version"],
                "skill_ips": plan["initial_ranking"],
                "confidence_gate": plan["gate"],
                "reran_with_llm": reran,
                "prompt": plan["prompt"] if reran else "",
                "llm_raw_response": raw_response,
                "llm_output_filter": output_filter,
                "token_usage": token_usage,
                "response": response,
                "ranking_evidence": plan["ranking_evidence"],
                "runtime": plan["runtime"],
            }
        )

    _save_json(results, run_dir / "res.json")
    _save_json(rerun_manifest, run_dir / "rerun_cases.json")
    token_usage_summary = _summarize_token_usage(results)
    _save_json(token_usage_summary, run_dir / "token_usage.json")
    observed_run_wall_seconds = time.perf_counter() - mode_started
    evidence_estimated_total = sum(
        plan["runtime"]["evidence_estimated_seconds"] for plan in plans
    )

    scoring_started = time.perf_counter()
    metrics = None
    diagnostic_summary = None
    if not args.skip_score:
        # Evaluation-only import: this is the first point at which labels may be read.
        from Sys.Score.Score_N import Scorer

        metrics = Scorer(str(run_dir / "res.json")).calculate_metrics()
        final_metrics = (
            metrics.get("skill_evaluation", {})
            if mode == "m1"
            else metrics.get("llm_evaluation", {})
        )
        _save_json(
            {"mode": mode, "evaluation_source": "skill_ips" if mode == "m1" else "response", **final_metrics},
            run_dir / "final_metrics.json",
        )
        if mode in ALL_LLM_MODES:
            diagnostic_summary = _write_all_llm_evaluation_artifacts(
                mode=mode,
                plans=plans,
                results=results,
                run_dir=run_dir,
                evidence_root=Path(args.evidence_root),
            )
    scoring_seconds = time.perf_counter() - scoring_started
    timing = {
        "mode": mode,
        "case_count": len(plans),
        "rerun_case_count": len(rerun_plans),
        "confidence_counts": confidence_counts,
        "natural_decision_counts": natural_decision_counts,
        "evidence_average_seconds_per_device": evidence_average_seconds if mode != "m1" else 0.0,
        "evidence_estimated_total_seconds": evidence_estimated_total,
        "observed_ablation_wall_seconds": observed_run_wall_seconds,
        "estimated_end_to_end_seconds": observed_run_wall_seconds + evidence_estimated_total,
        "metric_scoring_wall_seconds": scoring_seconds,
        "estimated_end_to_end_with_scoring_seconds": (
            observed_run_wall_seconds + evidence_estimated_total + scoring_seconds
        ),
        "llm_stage_wall_seconds": llm_wall_seconds,
        "token_usage": {
            key: value
            for key, value in token_usage_summary.items()
            if key != "per_case"
        },
        "llm_worker_stats": worker_stats,
    }
    _save_json(timing, run_dir / "timing.json")
    return {
        "mode": mode,
        "case_count": len(plans),
        "rerun_case_count": len(rerun_plans),
        "run_dir": str(run_dir),
        "timing": timing,
        "metrics": metrics,
        "diagnostics": diagnostic_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run M1/M13/M23/M123 and forced-all-LLM ablations from cached evidence."
        )
    )
    parser.add_argument("--data-root", "-d", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-tag", default=time.strftime("ablation_%Y%m%d_%H%M%S"))
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--weight-file", default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument(
        "--npu-groups",
        default="0,1",
        help="semicolon-separated tensor-parallel groups, e.g. '0,1;2,3'",
    )
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-num-seqs", type=int, default=4)
    parser.add_argument("--max-model-len", type=int, default=16384)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--repetition-penalty", type=float, default=1.05)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.85)
    parser.add_argument("--limit-cases", type=int, default=None)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--skip-score", action="store_true")
    args = parser.parse_args()

    args.data_root = os.path.abspath(args.data_root)
    args.evidence_root = os.path.abspath(args.evidence_root)
    if args.top_k <= 0:
        raise SystemExit("--top-k must be positive")
    if any(mode != "m1" for mode in args.modes) and not args.plan_only and not args.model_path:
        raise SystemExit("--model-path is required for any LLM ablation inference")

    dirpaths = discover_cases(args.data_root)
    if args.limit_cases is not None:
        dirpaths = dirpaths[: max(args.limit_cases, 0)]
    evidence_index: Dict[str, Dict[str, Any]] = {}
    evidence_average_seconds = 0.0
    if any(mode != "m1" for mode in args.modes):
        evidence_index, evidence_average_seconds = _load_evidence_index(
            Path(args.evidence_root)
        )

    root = Path(args.output_root).resolve() / args.run_tag
    if root.exists():
        raise SystemExit(f"run root already exists: {root}; choose a different --run-tag")
    root.mkdir(parents=True)
    (root / "large_model_prompt_template.txt").write_text(
        ABLATION_RCA_PROMPT, encoding="utf-8"
    )
    (root / "m123_all_llm_rerank_prompt_template.txt").write_text(
        ALL_LLM_RERANK_PROMPT, encoding="utf-8"
    )
    (root / "m123_all_llm_evidence_prompt_template.txt").write_text(
        ALL_LLM_EVIDENCE_PROMPT, encoding="utf-8"
    )
    prompt_versions = {
        "selective": ABLATION_RCA_PROMPT_VERSION,
        "rerank": ALL_LLM_RERANK_PROMPT_VERSION,
        "evidence_judge": ALL_LLM_EVIDENCE_PROMPT_VERSION,
    }
    model_config = {
        "model_path": args.model_path,
        "npu_groups": args.npu_groups,
        "batch_size": args.batch_size,
        "max_num_seqs": args.max_num_seqs,
        "max_model_len": args.max_model_len,
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "repetition_penalty": args.repetition_penalty,
        "gpu_memory_utilization": args.gpu_memory_utilization,
    }
    _save_json(
        {
            "run_tag": args.run_tag,
            "data_root": args.data_root,
            "evidence_root": args.evidence_root,
            "output_root": str(root),
            "modes": args.modes,
            "top_k": args.top_k,
            "weight_file": args.weight_file,
            "prompt_versions": prompt_versions,
            "model_config": model_config,
            "plan_only": args.plan_only,
            "skip_score": args.skip_score,
        },
        root / "run_config.json",
    )
    summaries = []
    for mode in args.modes:
        print(f"[ablation] mode={mode} cases={len(dirpaths)}")
        summaries.append(
            run_mode(
                mode=mode,
                dirpaths=dirpaths,
                args=args,
                run_dir=root / mode,
                evidence_index=evidence_index,
                evidence_average_seconds=evidence_average_seconds,
            )
        )
    _save_json(
        {
            "run_tag": args.run_tag,
            "data_root": args.data_root,
            "evidence_root": args.evidence_root,
            "top_k": args.top_k,
            "prompt_versions": prompt_versions,
            "model_config": model_config,
            "modes": summaries,
        },
        root / "summary.json",
    )
    print(f"[ablation] done -> {root}")


if __name__ == "__main__":
    main()
