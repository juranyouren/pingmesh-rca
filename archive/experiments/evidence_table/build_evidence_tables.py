#!/usr/bin/env python3
"""Precompute neighbour-aware summaries and deterministic evidence tables.

The script runs one replica of the same local small model per NPU card.  Each
replica uses vLLM continuous batching.  It never reads ``label.json``.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import inspect
import json
import math
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

from prompts.evidence_summary import EVIDENCE_SUMMARY_PROMPT, SUMMARY_PROMPT_VERSION
from Sys.RootCauseAnalyze.skills.temporal_ranker import temporal_feature_details
from Sys.utils.alarm_utils import event_name, load_alarm_weights, node_alarm_weight
from Sys.utils.case_utils import find_full_link_file, get_device_ip, load_case_info, load_case_nodes


EVIDENCE_TABLE_SCHEMA_VERSION = "evidence-table-v1"
SUMMARY_PARSER_VERSION = "json-first-after-think-v2"
_REASONING_BLOCK = re.compile(
    r"<(?:think|analysis)\b[^>]*>.*?</(?:think|analysis)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_UNCLOSED_REASONING_BLOCK = re.compile(
    r"<(?:think|analysis)\b[^>]*>.*\Z", re.IGNORECASE | re.DOTALL
)
_CLOSING_REASONING_TAG = re.compile(
    r"</(?:think|analysis)\s*>", re.IGNORECASE
)


def _save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def _write_jsonl(rows: Iterable[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def discover_cases(data_root: str) -> List[str]:
    cases: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(data_root):
        if "info.json" in filenames and find_full_link_file(dirpath, filenames):
            cases.append(os.path.abspath(dirpath))
    return sorted(cases)


def case_key(dirpath: str, data_root: str) -> str:
    relative = os.path.relpath(os.path.abspath(dirpath), os.path.abspath(data_root))
    leaf = re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.basename(dirpath)) or "case"
    digest = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:10]
    return f"{leaf}_{digest}"


def _relation(node: Dict[str, Any], neighbor_ip: str) -> str:
    upstream = neighbor_ip in set(node.get("linked_from", []) or [])
    downstream = neighbor_ip in set(node.get("linked_to", []) or [])
    if upstream and downstream:
        return "bidirectional"
    return "upstream" if upstream else "downstream"


def _alarm_with_weight(alarm: Any, weights: Dict[str, int], source_index: int) -> Dict[str, Any]:
    name = event_name(alarm)
    return {
        "source_index": source_index,
        "weight": int(weights.get(str(name).lower(), 0)) if name else 0,
        "alarm": alarm,
    }


def build_device_task(
    *,
    case_id: str,
    dirpath: str,
    node: Dict[str, Any],
    node_by_ip: Dict[str, Dict[str, Any]],
    weights: Dict[str, int],
) -> Dict[str, Any]:
    ip = get_device_ip(node)
    target_alarms = [
        _alarm_with_weight(alarm, weights, index)
        for index, alarm in enumerate(node.get("alarms", []) or [])
    ]
    neighbor_ips: List[str] = []
    seen = set()
    for raw_ip in [*(node.get("linked_from", []) or []), *(node.get("linked_to", []) or [])]:
        neighbor_ip = str(raw_ip) if raw_ip is not None else ""
        if neighbor_ip and neighbor_ip not in seen and neighbor_ip in node_by_ip:
            seen.add(neighbor_ip)
            neighbor_ips.append(neighbor_ip)

    neighbors: List[Dict[str, Any]] = []
    for neighbor_ip in neighbor_ips:
        neighbor = node_by_ip[neighbor_ip]
        alarms = [
            _alarm_with_weight(alarm, weights, index)
            for index, alarm in enumerate(neighbor.get("alarms", []) or [])
        ]
        if not alarms:
            continue
        neighbors.append(
            {
                "neighbor_ip": neighbor_ip,
                "role": neighbor.get("role", "UNKNOWN"),
                "relation": _relation(node, neighbor_ip),
                "alarms": alarms,
                "max_weight": max((item["weight"] for item in alarms), default=0),
            }
        )
    neighbors.sort(key=lambda item: (-item["max_weight"], item["neighbor_ip"]))

    task_material = f"{case_id}|{ip}|{SUMMARY_PROMPT_VERSION}"
    return {
        "task_id": hashlib.sha1(task_material.encode("utf-8")).hexdigest(),
        "case_id": case_id,
        "dir": dirpath,
        "device_ip": ip,
        "target": {
            "ip": ip,
            "role": node.get("role", "UNKNOWN"),
            "alarms": target_alarms,
        },
        "neighbors": neighbors,
        "neighbor_stats": {
            "total_neighbors": len(neighbor_ips),
            "neighbors_with_alarms": len(neighbors),
            "neighbors_without_alarms": len(neighbor_ips) - len(neighbors),
            "total_neighbor_alarms": sum(len(item["alarms"]) for item in neighbors),
        },
    }


def _public_alarm(item: Dict[str, Any]) -> Any:
    """Return model-visible alarm facts without the rule weight."""
    return item.get("alarm")


def _payload_for(
    task: Dict[str, Any],
    neighbors: Sequence[Dict[str, Any]],
    target_alarms: Sequence[Dict[str, Any]],
    *,
    mode: str,
    omitted_neighbors: int = 0,
    omitted_target_alarms: int = 0,
) -> Dict[str, Any]:
    return {
        "target_device": {
            "ip": task["target"]["ip"],
            "role": task["target"]["role"],
            "alarms": [_public_alarm(item) for item in target_alarms],
        },
        "neighbor_statistics": task["neighbor_stats"],
        "neighbor_alarm_context": [
            {
                "neighbor_ip": item["neighbor_ip"],
                "role": item["role"],
                "relation": item["relation"],
                "alarms": [_public_alarm(alarm) for alarm in item["alarms"]],
            }
            for item in neighbors
        ],
        "context_policy": {
            "mode": mode,
            "truncated": mode != "all_neighbor_alarms",
            "omitted_neighbors": omitted_neighbors,
            "omitted_target_alarms": omitted_target_alarms,
        },
    }


def _render_summary_prompt(payload: Dict[str, Any]) -> str:
    model_input = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return EVIDENCE_SUMMARY_PROMPT.format(DEVICE_AND_NEIGHBOR_ALARMS_JSON=model_input)


def _token_count(tokenizer: Any, prompt: str) -> int:
    return len(tokenizer.encode(prompt))


def prepare_summary_prompt(
    task: Dict[str, Any], tokenizer: Any, max_input_tokens: int
) -> tuple[str, Dict[str, Any]]:
    """Use all neighbour alarms first, then deterministic weight-based fallback."""
    if max_input_tokens <= 0:
        raise ValueError("max_input_tokens must be positive")
    target_alarms = list(task["target"]["alarms"])
    all_neighbors = list(task["neighbors"])
    payload = _payload_for(
        task, all_neighbors, target_alarms, mode="all_neighbor_alarms"
    )
    prompt = _render_summary_prompt(payload)
    if _token_count(tokenizer, prompt) <= max_input_tokens:
        return prompt, payload["context_policy"]

    reduced_neighbors = []
    for neighbor in all_neighbors:
        best = sorted(
            neighbor["alarms"],
            key=lambda item: (-item["weight"], item["source_index"]),
        )[:1]
        reduced_neighbors.append({**neighbor, "alarms": best})
    payload = _payload_for(
        task,
        reduced_neighbors,
        target_alarms,
        mode="highest_weight_per_neighbor",
    )
    prompt = _render_summary_prompt(payload)
    if _token_count(tokenizer, prompt) <= max_input_tokens:
        return prompt, payload["context_policy"]

    kept_neighbors = list(reduced_neighbors)
    while kept_neighbors:
        kept_neighbors.pop()  # lowest priority: list is weight-descending
        payload = _payload_for(
            task,
            kept_neighbors,
            target_alarms,
            mode="trimmed_neighbors",
            omitted_neighbors=len(reduced_neighbors) - len(kept_neighbors),
        )
        prompt = _render_summary_prompt(payload)
        if _token_count(tokenizer, prompt) <= max_input_tokens:
            return prompt, payload["context_policy"]

    # Target evidence has priority.  This final guard handles a pathological
    # single device whose own alarm payload exceeds the model context.
    ranked_target = sorted(
        target_alarms,
        key=lambda item: (-item["weight"], item["source_index"]),
    )
    kept_target = list(ranked_target)
    while kept_target:
        payload = _payload_for(
            task,
            [],
            kept_target,
            mode="trimmed_target_last_resort",
            omitted_neighbors=len(reduced_neighbors),
            omitted_target_alarms=len(target_alarms) - len(kept_target),
        )
        prompt = _render_summary_prompt(payload)
        if _token_count(tokenizer, prompt) <= max_input_tokens:
            return prompt, payload["context_policy"]
        kept_target.pop()

    payload = _payload_for(
        task,
        [],
        [],
        mode="metadata_only_last_resort",
        omitted_neighbors=len(reduced_neighbors),
        omitted_target_alarms=len(target_alarms),
    )
    prompt = _render_summary_prompt(payload)
    if _token_count(tokenizer, prompt) > max_input_tokens:
        raise ValueError("summary prompt template alone exceeds max_input_tokens")
    return prompt, payload["context_policy"]


def strip_reasoning(text: str) -> str:
    cleaned = text or ""
    # Some reasoning models omit the opening <think> tag but still emit
    # </think> before the final answer. In that case, everything before the
    # last closing reasoning tag is hidden reasoning and must not enter the
    # evidence-table summary.
    closing_tags = list(_CLOSING_REASONING_TAG.finditer(cleaned))
    if closing_tags:
        cleaned = cleaned[closing_tags[-1].end() :]
    cleaned = _REASONING_BLOCK.sub("", cleaned)
    return _UNCLOSED_REASONING_BLOCK.sub("", cleaned).strip()


def _balanced_json_objects(text: str) -> List[str]:
    """Extract balanced ``{...}`` candidates while respecting JSON strings."""
    candidates: List[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text or ""):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start : index + 1])
                start = None
    return candidates


def parse_summary(raw_response: str) -> tuple[str, str]:
    raw = raw_response or ""

    # First priority: find a valid JSON object anywhere in the complete model
    # response. The final valid object wins when the model emits more than one.
    for candidate in reversed(_balanced_json_objects(raw)):
        try:
            data = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        summary = data.get("summary") if isinstance(data, dict) else None
        if isinstance(summary, str) and summary.strip():
            return summary.strip(), "json"

    # Second priority: reasoning models may produce a plain-text final answer
    # after </think>. When JSON parsing failed, that suffix is the summary.
    closing_tags = list(_CLOSING_REASONING_TAG.finditer(raw))
    if closing_tags:
        after_think = raw[closing_tags[-1].end() :].strip()
        if after_think:
            return after_think, "after_think"

    return strip_reasoning(raw), "raw_fallback"


def _vllm_cache_kwargs(kv_cache_gb: float, num_gpu_blocks_override: int) -> Dict[str, Any]:
    from vllm.engine.arg_utils import EngineArgs

    supported = set(inspect.signature(EngineArgs).parameters)
    if "kv_cache_memory_bytes" in supported:
        return {"kv_cache_memory_bytes": int(kv_cache_gb * 1024**3)}
    if "num_gpu_blocks_override" in supported:
        return {"num_gpu_blocks_override": num_gpu_blocks_override}
    return {}


def _summary_worker(worker: Dict[str, Any]) -> Dict[str, Any]:
    worker_started = time.perf_counter()
    card = str(worker["npu_card"])
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = card
    from vllm import LLM, SamplingParams

    init_started = time.perf_counter()
    llm_kwargs = {
        "model": worker["model_path"],
        "tensor_parallel_size": 1,
        "gpu_memory_utilization": worker["gpu_memory_utilization"],
        "max_model_len": worker["max_model_len"],
        "max_num_seqs": worker["max_num_seqs"],
        "trust_remote_code": True,
    }
    llm_kwargs.update(
        _vllm_cache_kwargs(worker["kv_cache_gb"], worker["num_gpu_blocks_override"])
    )
    llm = LLM(**llm_kwargs)
    tokenizer = llm.get_tokenizer()
    sampling = SamplingParams(
        temperature=worker["temperature"],
        max_tokens=worker["max_tokens"],
        repetition_penalty=1.02,
    )
    init_seconds = time.perf_counter() - init_started

    records: List[Dict[str, Any]] = []
    inference_seconds = 0.0
    tasks = worker["tasks"]
    for offset in range(0, len(tasks), worker["batch_size"]):
        batch = tasks[offset : offset + worker["batch_size"]]
        prepared = [
            prepare_summary_prompt(task, tokenizer, worker["max_input_tokens"])
            for task in batch
        ]
        prompts = [item[0] for item in prepared]
        applied = [[{"role": "user", "content": prompt}] for prompt in prompts]
        started = time.perf_counter()
        outputs = llm.chat(applied, sampling)
        batch_seconds = time.perf_counter() - started
        inference_seconds += batch_seconds
        amortized = batch_seconds / max(len(batch), 1)
        for task, prompt, (_same_prompt, policy), output in zip(batch, prompts, prepared, outputs):
            raw = output.outputs[0].text.strip()
            summary, parse_mode = parse_summary(raw)
            records.append(
                {
                    "task_id": task["task_id"],
                    "case_id": task["case_id"],
                    "dir": task["dir"],
                    "device_ip": task["device_ip"],
                    "worker_id": worker["worker_id"],
                    "npu_card": card,
                    "prompt": prompt,
                    "prompt_tokens": _token_count(tokenizer, prompt),
                    "context_policy": policy,
                    "raw_response": raw,
                    "summary": summary,
                    "parse_mode": parse_mode,
                    "parser_version": SUMMARY_PARSER_VERSION,
                    "amortized_inference_seconds": amortized,
                }
            )

    part_path = Path(worker["part_path"])
    _write_jsonl(records, part_path)
    del llm
    gc.collect()
    return {
        "worker_id": worker["worker_id"],
        "npu_card": card,
        "task_count": len(tasks),
        "model_init_seconds": init_seconds,
        "inference_seconds": inference_seconds,
        "worker_wall_seconds": time.perf_counter() - worker_started,
        "part_path": str(part_path),
    }


def _chunk_evenly(items: Sequence[Any], count: int) -> List[List[Any]]:
    chunks: List[List[Any]] = [[] for _ in range(count)]
    for index, item in enumerate(items):
        chunks[index % count].append(item)
    return chunks


def _build_evidence_row(
    node: Dict[str, Any],
    result: Dict[str, Any],
    weights: Dict[str, int],
    temporal_features: Dict[str, Dict[str, float]],
    task: Dict[str, Any],
) -> Dict[str, Any]:
    ip = get_device_ip(node)
    max_weight, high_weight_alarms = node_alarm_weight(node, weights)
    return {
        "candidate_ip": ip,
        "role": node.get("role", "UNKNOWN"),
        "cross": node.get("cross", 0),
        "alarm_count": len(node.get("alarms", []) or []),
        "log_count": len(node.get("logs", []) or []),
        "alarms_exact": node.get("alarms", []) or [],
        "logs_exact": node.get("logs", []) or [],
        "max_alarm_rule_weight": max_weight,
        "high_weight_alarms": high_weight_alarms,
        "temporal": temporal_features.get(ip, {}),
        "topology": {
            "upstream": node.get("linked_from", []) or [],
            "downstream": node.get("linked_to", []) or [],
        },
        "neighbor_alarm_statistics": task["neighbor_stats"],
        "semantic_summary": result.get("summary", ""),
        "summary_context": {
            "prompt_version": SUMMARY_PROMPT_VERSION,
            "prompt_tokens": result.get("prompt_tokens"),
            "parse_mode": result.get("parse_mode"),
            "parser_version": result.get(
                "parser_version", SUMMARY_PARSER_VERSION
            ),
            **(result.get("context_policy") or {}),
        },
        "provenance": {
            "summary_task_id": result.get("task_id"),
            "source_device_ip": ip,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build all-device neighbour-aware summaries and evidence tables."
    )
    parser.add_argument("--data-root", "-d", required=True)
    parser.add_argument(
        "--output-root", "-o", default=str(PROJECT_ROOT / "data" / "evidence_Table")
    )
    parser.add_argument("--model-path", required=True)
    parser.add_argument(
        "--npu-cards", default="0", help="comma-separated cards; one model replica per card"
    )
    parser.add_argument("--weight-file", default=None)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-num-seqs", type=int, default=8)
    parser.add_argument("--max-model-len", type=int, default=4096)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--max-input-tokens", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.35)
    parser.add_argument("--kv-cache-gb", type=float, default=4.0)
    parser.add_argument("--num-gpu-blocks-override", type=int, default=256)
    parser.add_argument("--limit-cases", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    data_root = os.path.abspath(args.data_root)
    output_root = Path(args.output_root).resolve()
    if (output_root / "manifest.json").exists() and not args.overwrite:
        raise SystemExit(
            f"{output_root} already contains manifest.json; pass --overwrite to rebuild"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "prompt_template.txt").write_text(
        EVIDENCE_SUMMARY_PROMPT, encoding="utf-8"
    )

    cards = [part.strip() for part in args.npu_cards.split(",") if part.strip()]
    if not cards:
        raise SystemExit("--npu-cards must contain at least one card")
    if args.batch_size <= 0 or args.max_num_seqs <= 0:
        raise SystemExit("batch sizes must be positive")
    max_input_tokens = args.max_input_tokens
    if max_input_tokens is None:
        max_input_tokens = args.max_model_len - args.max_tokens - 256
    if max_input_tokens <= 0:
        raise SystemExit("model context is too small for the requested output budget")

    cases = discover_cases(data_root)
    if args.limit_cases is not None:
        cases = cases[: max(args.limit_cases, 0)]
    weights = load_alarm_weights(args.weight_file)
    tasks: List[Dict[str, Any]] = []
    case_records: List[Dict[str, Any]] = []
    task_by_id: Dict[str, Dict[str, Any]] = {}
    for dirpath in cases:
        cid = case_key(dirpath, data_root)
        nodes = load_case_nodes(dirpath)
        node_by_ip = {
            get_device_ip(node): node
            for node in nodes
            if get_device_ip(node) not in ("", "unknown")
        }
        case_tasks = [
            build_device_task(
                case_id=cid,
                dirpath=dirpath,
                node=node,
                node_by_ip=node_by_ip,
                weights=weights,
            )
            for _ip, node in sorted(node_by_ip.items())
        ]
        tasks.extend(case_tasks)
        task_by_id.update({task["task_id"]: task for task in case_tasks})
        case_records.append(
            {"case_id": cid, "dir": dirpath, "device_count": len(case_tasks)}
        )

    print(f"[evidence] cases={len(cases)} devices={len(tasks)} replicas={len(cards)}")
    run_started = time.perf_counter()
    worker_dir = output_root / "_worker_parts"
    worker_dir.mkdir(parents=True, exist_ok=True)
    chunks = _chunk_evenly(tasks, len(cards))
    worker_specs = []
    for index, (card, chunk) in enumerate(zip(cards, chunks), 1):
        if not chunk:
            continue
        worker_specs.append(
            {
                "worker_id": index,
                "npu_card": card,
                "tasks": chunk,
                "part_path": str(worker_dir / f"worker_{index}.jsonl"),
                "model_path": args.model_path,
                "batch_size": args.batch_size,
                "max_num_seqs": args.max_num_seqs,
                "max_model_len": args.max_model_len,
                "max_tokens": args.max_tokens,
                "max_input_tokens": max_input_tokens,
                "temperature": args.temperature,
                "gpu_memory_utilization": args.gpu_memory_utilization,
                "kv_cache_gb": args.kv_cache_gb,
                "num_gpu_blocks_override": args.num_gpu_blocks_override,
            }
        )

    worker_stats: List[Dict[str, Any]] = []
    if worker_specs:
        import multiprocessing as mp

        with ProcessPoolExecutor(
            max_workers=len(worker_specs), mp_context=mp.get_context("spawn")
        ) as executor:
            futures = [executor.submit(_summary_worker, spec) for spec in worker_specs]
            for future in as_completed(futures):
                worker_stats.append(future.result())
    summary_wall_seconds = time.perf_counter() - run_started

    all_outputs: List[Dict[str, Any]] = []
    for stat in sorted(worker_stats, key=lambda item: item["worker_id"]):
        all_outputs.extend(_read_jsonl(Path(stat["part_path"])))
    result_by_task = {row["task_id"]: row for row in all_outputs}
    if len(result_by_task) != len(tasks):
        raise RuntimeError(
            f"summary output count mismatch: expected {len(tasks)}, got {len(result_by_task)}"
        )

    by_case: Dict[str, List[Dict[str, Any]]] = {}
    for row in all_outputs:
        by_case.setdefault(row["case_id"], []).append(row)

    materialize_started = time.perf_counter()
    for case in case_records:
        cid = case["case_id"]
        dirpath = case["dir"]
        nodes = load_case_nodes(dirpath)
        info = load_case_info(dirpath)
        temporal_features, temporal_diagnostics = temporal_feature_details(nodes, info, dirpath)
        rows: List[Dict[str, Any]] = []
        for node in sorted(nodes, key=lambda item: get_device_ip(item)):
            ip = get_device_ip(node)
            if ip in ("", "unknown"):
                continue
            task_id = hashlib.sha1(
                f"{cid}|{ip}|{SUMMARY_PROMPT_VERSION}".encode("utf-8")
            ).hexdigest()
            result = result_by_task[task_id]
            rows.append(
                _build_evidence_row(
                    node, result, weights, temporal_features, task_by_id[task_id]
                )
            )
        case_dir = output_root / "cases" / cid
        _save_json(
            {
                "schema_version": EVIDENCE_TABLE_SCHEMA_VERSION,
                "summary_prompt_version": SUMMARY_PROMPT_VERSION,
                "summary_parser_version": SUMMARY_PARSER_VERSION,
                "case_id": cid,
                "source_dir": dirpath,
                "device_count": len(rows),
                "temporal_diagnostics": temporal_diagnostics,
                "rows": rows,
            },
            case_dir / "evidence_table.json",
        )
        _write_jsonl(
            sorted(by_case.get(cid, []), key=lambda item: item["device_ip"]),
            case_dir / "small_model_outputs.jsonl",
        )
    materialize_seconds = time.perf_counter() - materialize_started
    total_wall_seconds = time.perf_counter() - run_started

    device_count = len(tasks)
    timing = {
        # These two fields are the pre-stored values consumed by the later
        # ablation-time estimator: candidate_count * average_seconds_per_device.
        "total_wall_seconds": summary_wall_seconds,
        "average_seconds_per_device": (
            summary_wall_seconds / device_count if device_count else 0.0
        ),
        "summary_parallel_wall_seconds": summary_wall_seconds,
        "table_materialization_seconds": materialize_seconds,
        "end_to_end_wall_seconds": total_wall_seconds,
        "device_count": device_count,
        "worker_stats": sorted(worker_stats, key=lambda item: item["worker_id"]),
    }
    _save_json(timing, output_root / "timing.json")
    _save_json(
        {
            "schema_version": EVIDENCE_TABLE_SCHEMA_VERSION,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "data_root": data_root,
            "model_path": args.model_path,
            "npu_cards": cards,
            "summary_prompt_version": SUMMARY_PROMPT_VERSION,
            "summary_parser_version": SUMMARY_PARSER_VERSION,
            "case_count": len(case_records),
            "device_count": device_count,
            "cases": case_records,
            "timing_file": str(output_root / "timing.json"),
        },
        output_root / "manifest.json",
    )
    print(
        f"[evidence] done summary_total={summary_wall_seconds:.3f}s "
        f"avg={timing['average_seconds_per_device']:.6f}s/device -> {output_root}"
    )


if __name__ == "__main__":
    main()
