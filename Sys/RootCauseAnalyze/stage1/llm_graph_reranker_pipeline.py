from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Sys.RootCauseAnalyze.propagation.m1 import reconstruct_hypothesis_graph
from Sys.RootCauseAnalyze.propagation.m2 import infer_root_paths
from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig
from Sys.RootCauseAnalyze.propagation.topology_context import load_topology_context
from Sys.RootCauseAnalyze.stage1.llm_graph_reranker import (
    METHOD_VERSION,
    SUPPORTED_VARIANTS,
    VARIANT_PRIOR_EVIDENCE_GRAPH,
    MockLLMBackend,
    PromptBudget,
    VLLMBackend,
    build_prompt_evidence,
    build_prompt_package,
    compact_candidate_graph,
    consensus_ranking,
    finalize_ranking,
    parse_llm_decision,
    prioritize_evidence,
    sanitize_incident_info,
)
from Sys.RootCauseAnalyze.stage1.neural_graph import RawCase, load_raw_cases
from Sys.utils.io_utils import load_json, save_json, write_jsonl


CONSENSUS_METHOD = "llm_prior_evidence_graph_consensus"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result and abs(result) != float("inf") else default


def _normalized_path(value: Any) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(value or ""))))


def _root_result_map(path: str) -> Dict[str, Dict[str, Any]]:
    records = load_json(path, default=None)
    if not isinstance(records, list):
        raise ValueError("root result file must contain a JSON list")
    result: Dict[str, Dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, Mapping) or not raw.get("dir"):
            continue
        key = _normalized_path(raw["dir"])
        if key in result:
            raise ValueError(f"duplicate root result path: {raw['dir']}")
        result[key] = dict(raw)
    return result


def _root_rankings(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    stage1 = record.get("stage1", {})
    candidates = (
        record.get("initial_root_rankings"),
        record.get("base_root_rankings"),
        stage1.get("root_rankings") if isinstance(stage1, Mapping) else None,
    )
    for raw in candidates:
        if not isinstance(raw, list):
            continue
        rankings = [dict(item) for item in raw if isinstance(item, Mapping)]
        if rankings:
            seen: set[str] = set()
            result: List[Dict[str, Any]] = []
            for fallback_rank, item in enumerate(rankings, 1):
                ip = str(item.get("ip", item.get("device_id", "")) or "")
                if not ip or ip in seen:
                    continue
                seen.add(ip)
                result.append({**item, "ip": ip, "rank": fallback_rank})
            return result
    return []


def _empty_root_graph(ip: str, ranking: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "root_hypothesis": {
            "root_devices": [ip],
            "rank": ranking.get("rank"),
            "support_score": ranking.get("combined_score", ranking.get("score", 0.0)),
        },
        "explanation_score": 0.0,
        "propagation_graph": {
            "graph_score": 0.0,
            "target_coverage": 0.0,
            "covered_targets": [],
            "nodes": [{"device_id": ip, "role": "root", "evidence_ids": []}],
            "edges": [],
            "ranked_chains": [],
            "diagnostics": {"uncovered_targets": [], "graph_missing": True},
        },
    }


def prepare_case(
    case: RawCase,
    root_record: Mapping[str, Any],
    *,
    config: PropagationConfig,
    min_evidence_per_candidate: int,
) -> Dict[str, Any]:
    rankings = _root_rankings(root_record)[: config.root_top_k]
    if not rankings:
        raise ValueError(f"root ranking is empty for case: {case.dirpath}")
    topology_context = load_topology_context(
        case.dirpath, node_list=case.nodes, info=case.info
    )
    hypothesis_graph = reconstruct_hypothesis_graph(
        nodes=case.nodes,
        info=case.info,
        topology_context=topology_context,
        config=config,
    )
    inference = infer_root_paths(
        hypothesis_graph=hypothesis_graph,
        initial_root_rankings=rankings,
        config=config,
    )
    roots = {
        str(item.get("root_hypothesis", {}).get("root_devices", [""])[0]): item
        for item in inference.get("root_conditioned_propagation_graphs", [])
        if isinstance(item, Mapping)
        and isinstance(item.get("root_hypothesis"), Mapping)
        and item.get("root_hypothesis", {}).get("root_devices")
    }
    candidate_graphs = []
    for ranking in rankings:
        ip = str(ranking["ip"])
        root_item = roots.get(ip, _empty_root_graph(ip, ranking))
        candidate_graphs.append(
            compact_candidate_graph(
                root_item=root_item,
                initial_ranking=ranking,
                hypothesis_graph=hypothesis_graph,
            )
        )
    evidence = build_prompt_evidence(
        nodes=case.nodes,
        hypothesis_graph=hypothesis_graph,
    )
    evidence = prioritize_evidence(
        evidence,
        candidate_graphs,
        min_per_candidate=min_evidence_per_candidate,
    )
    return {
        "dir": case.dirpath,
        "case_id": os.path.basename(os.path.normpath(case.dirpath)),
        "incident": sanitize_incident_info(case.info),
        "initial_ips": [str(item["ip"]) for item in rankings],
        "initial_rankings": rankings,
        "evidence": evidence,
        "candidates": candidate_graphs,
        "hypothesis_summary": dict(hypothesis_graph.get("summary", {})),
    }


def prepare_cases(
    cases: Sequence[RawCase],
    root_records: Mapping[str, Mapping[str, Any]],
    *,
    config: PropagationConfig,
    min_evidence_per_candidate: int,
) -> List[Dict[str, Any]]:
    prepared = []
    for index, case in enumerate(cases, 1):
        record = root_records.get(_normalized_path(case.dirpath))
        if record is None:
            raise ValueError(f"root result is missing for case: {case.dirpath}")
        prepared.append(
            prepare_case(
                case,
                record,
                config=config,
                min_evidence_per_candidate=min_evidence_per_candidate,
            )
        )
        if index % 20 == 0:
            print(f"LLM graph-reranker preparation: {index}/{len(cases)}")
    return prepared


def _final_ranking_rows(
    initial_rankings: Sequence[Mapping[str, Any]], final_ips: Sequence[str]
) -> List[Dict[str, Any]]:
    by_ip = {
        str(item.get("ip")): dict(item)
        for item in initial_rankings
        if item.get("ip")
    }
    rows = []
    for final_rank, ip in enumerate(final_ips, 1):
        original = by_ip.get(str(ip), {"ip": str(ip)})
        initial_rank = int(original.get("rank", final_rank) or final_rank)
        rows.append(
            {
                **original,
                "ip": str(ip),
                "rank": final_rank,
                "initial_rank": initial_rank,
                "rank_change": (
                    "promote"
                    if final_rank < initial_rank
                    else "demote"
                    if final_rank > initial_rank
                    else "unchanged"
                ),
            }
        )
    return rows


def _result_record(
    case: Mapping[str, Any],
    *,
    method: str,
    final_ips: Sequence[str],
    parsed: Mapping[str, Any],
    fallback_reason: str,
    consensus: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    explanation = str(parsed.get("explanation", "") or "")
    response = json.dumps(
        {"ip": list(final_ips), "explanation": explanation},
        ensure_ascii=False,
    )
    return {
        "dir": case.get("dir"),
        "method": method,
        "ranked_ips": list(final_ips),
        "initial_root_rankings": list(case.get("initial_rankings", [])),
        "final_root_rankings": _final_ranking_rows(
            case.get("initial_rankings", []), final_ips
        ),
        "selected_root": final_ips[0] if final_ips else None,
        "response": response,
        "draft_response": response,
        "llm_reranking": {
            "method_version": METHOD_VERSION,
            "decision": parsed.get("decision", "invalid"),
            "selected_ip": parsed.get("selected_ip", ""),
            "confidence": parsed.get("confidence", "unknown"),
            "valid": bool(parsed.get("valid")),
            "abstained": bool(parsed.get("abstained")),
            "fallback_reason": fallback_reason,
            "decisive_evidence_ids": list(
                parsed.get("supported_evidence_ids", [])
            ),
            "unsupported_evidence_ids": list(
                parsed.get("unsupported_evidence_ids", [])
            ),
            "supported_graph_edges": list(parsed.get("supported_graph_edges", [])),
            "unsupported_graph_edges": list(
                parsed.get("unsupported_graph_edges", [])
            ),
            "explanation": explanation,
            "consensus": dict(consensus or {}),
            "input_tokens": parsed.get("input_tokens"),
        },
        "candidate_graph_ref": {
            "artifact": "../candidate_payloads.json",
            "case_id": case.get("case_id"),
            "selected_root": final_ips[0] if final_ips else None,
        },
    }


def _audit_record(
    case: Mapping[str, Any],
    package: Any,
    response: str,
    parsed: Mapping[str, Any],
    *,
    inference_seconds_per_prompt: float,
) -> Dict[str, Any]:
    return {
        "dir": case.get("dir"),
        "case_id": case.get("case_id"),
        "variant": package.variant,
        "pass_index": package.pass_index,
        "prompt_sha256": hashlib.sha256(package.prompt.encode("utf-8")).hexdigest(),
        "input_tokens": package.token_count,
        "candidate_aliases": package.alias_to_ip,
        "presentation_order": package.presentation_aliases,
        "pruning": package.pruning,
        "raw_response": response,
        "parsed": {
            key: value
            for key, value in parsed.items()
            if key not in {"clean_response", "parsed_json"}
        },
        "parsed_json": parsed.get("parsed_json", {}),
        "inference_seconds_share": inference_seconds_per_prompt,
    }


def run_variant(
    prepared_cases: Sequence[Mapping[str, Any]],
    *,
    variant: str,
    backend: Any,
    budget: PromptBudget,
    batch_size: int,
    save_prompts: bool,
    output_dir: str,
    minimum_budget_steps: Sequence[int] | None = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Any], List[Dict[str, Any]]]:
    minimum_steps = list(minimum_budget_steps or [0] * len(prepared_cases))
    if len(minimum_steps) != len(prepared_cases):
        raise ValueError("minimum_budget_steps must match prepared case count")
    packages = [
        build_prompt_package(
            case,
            variant=variant,
            pass_index=0,
            budget=budget,
            count_tokens=backend.count_tokens,
            minimum_budget_step=minimum_step,
        )
        for case, minimum_step in zip(prepared_cases, minimum_steps)
    ]
    responses, elapsed = backend.generate(
        [package.prompt for package in packages], batch_size=batch_size
    )
    if len(responses) != len(packages):
        raise RuntimeError(
            f"vLLM output count mismatch: expected={len(packages)}, got={len(responses)}"
        )
    share = elapsed / len(packages) if packages else 0.0
    records: List[Dict[str, Any]] = []
    audits: List[Dict[str, Any]] = []
    decisions: List[Dict[str, Any]] = []
    for case, package, response in zip(prepared_cases, packages, responses):
        parsed = parse_llm_decision(response, package)
        parsed["input_tokens"] = package.token_count
        final_ips, fallback_reason = finalize_ranking(case.get("initial_ips", []), parsed)
        records.append(
            _result_record(
                case,
                method=variant,
                final_ips=final_ips,
                parsed=parsed,
                fallback_reason=fallback_reason,
            )
        )
        audits.append(
            _audit_record(
                case,
                package,
                response,
                parsed,
                inference_seconds_per_prompt=share,
            )
        )
        decisions.append(parsed)
    variant_dir = os.path.join(output_dir, variant)
    save_json(records, os.path.join(variant_dir, "res.json"), indent=2)
    save_json(audits, os.path.join(variant_dir, "llm_audit.json"), indent=2)
    if save_prompts:
        write_jsonl(
            os.path.join(variant_dir, "prompts.jsonl"),
            (
                {
                    "dir": case.get("dir"),
                    "pass_index": package.pass_index,
                    "prompt": package.prompt,
                }
                for case, package in zip(prepared_cases, packages)
            ),
        )
    return records, audits, packages, decisions


def run_consensus(
    prepared_cases: Sequence[Mapping[str, Any]],
    *,
    direct_decisions: Sequence[Mapping[str, Any]],
    backend: Any,
    budget: PromptBudget,
    batch_size: int,
    consistency_passes: int,
    save_prompts: bool,
    output_dir: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    decisions_by_case: Dict[int, List[Dict[str, Any]]] = {
        index: [dict(decision)] for index, decision in enumerate(direct_decisions)
    }
    repeat_requests: List[Tuple[int, Any]] = []
    for case_index, (case, direct) in enumerate(
        zip(prepared_cases, direct_decisions)
    ):
        initial_ips = list(case.get("initial_ips", []))
        if (
            consistency_passes <= 1
            or not direct.get("valid")
            or not initial_ips
            or direct.get("selected_ip") == initial_ips[0]
        ):
            continue
        for pass_index in range(1, consistency_passes):
            package = build_prompt_package(
                case,
                variant=VARIANT_PRIOR_EVIDENCE_GRAPH,
                pass_index=pass_index,
                budget=budget,
                count_tokens=backend.count_tokens,
            )
            repeat_requests.append((case_index, package))

    repeat_audits: List[Dict[str, Any]] = []
    if repeat_requests:
        responses, elapsed = backend.generate(
            [package.prompt for _case_index, package in repeat_requests],
            batch_size=batch_size,
        )
        if len(responses) != len(repeat_requests):
            raise RuntimeError("consistency-pass vLLM output count mismatch")
        share = elapsed / len(repeat_requests)
        prompt_rows = []
        for (case_index, package), response in zip(repeat_requests, responses):
            parsed = parse_llm_decision(response, package)
            parsed["input_tokens"] = package.token_count
            decisions_by_case[case_index].append(parsed)
            repeat_audits.append(
                _audit_record(
                    prepared_cases[case_index],
                    package,
                    response,
                    parsed,
                    inference_seconds_per_prompt=share,
                )
            )
            prompt_rows.append(
                {
                    "dir": prepared_cases[case_index].get("dir"),
                    "pass_index": package.pass_index,
                    "prompt": package.prompt,
                }
            )
        if save_prompts:
            write_jsonl(
                os.path.join(output_dir, CONSENSUS_METHOD, "repeat_prompts.jsonl"),
                prompt_rows,
            )

    records: List[Dict[str, Any]] = []
    consensus_audits: List[Dict[str, Any]] = []
    for case_index, case in enumerate(prepared_cases):
        decisions = decisions_by_case[case_index]
        ranking, consensus = consensus_ranking(case.get("initial_ips", []), decisions)
        representative = dict(decisions[0])
        if (
            consensus.get("status") == "fallback_no_consensus"
            and ranking
            and representative.get("selected_ip") != ranking[0]
        ):
            representative["explanation"] = (
                "候选顺序复核未达成一致，保留Stage1首位候选；"
                "各次LLM选择仅保存在审计记录中。"
            )
        records.append(
            _result_record(
                case,
                method=CONSENSUS_METHOD,
                final_ips=ranking,
                parsed=representative,
                fallback_reason=str(consensus.get("status", "")),
                consensus=consensus,
            )
        )
        consensus_audits.append(
            {
                "dir": case.get("dir"),
                "case_id": case.get("case_id"),
                "consistency_passes_requested": consistency_passes,
                "passes_executed": len(decisions),
                "selected_votes": [
                    decision.get("selected_ip", "") for decision in decisions
                ],
                "valid_votes": [
                    bool(decision.get("valid")) for decision in decisions
                ],
                "consensus": consensus,
            }
        )
    consensus_dir = os.path.join(output_dir, CONSENSUS_METHOD)
    save_json(records, os.path.join(consensus_dir, "res.json"), indent=2)
    save_json(
        {"cases": consensus_audits, "repeat_calls": repeat_audits},
        os.path.join(consensus_dir, "llm_audit.json"),
        indent=2,
    )
    return records, consensus_audits


def _parse_cards(value: str) -> List[str]:
    cards = [item.strip() for item in value.split(",") if item.strip()]
    return cards or ["0"]


def _build_backend(args: argparse.Namespace) -> Any:
    if args.mock:
        return MockLLMBackend()
    return VLLMBackend(
        model_path=args.model,
        npu_cards=_parse_cards(args.npu),
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        max_model_len=args.max_model_len,
    )


def run(args: argparse.Namespace) -> str:
    started = time.perf_counter()
    cases = load_raw_cases(args.data_root, require_labels=False)
    root_records = _root_result_map(args.root_results)
    case_paths = {_normalized_path(case.dirpath) for case in cases}
    missing = sorted(case_paths - set(root_records))
    extra = sorted(set(root_records) - case_paths)
    if missing or extra:
        raise ValueError(
            "case/result mismatch: "
            f"cases={len(cases)}, results={len(root_records)}, "
            f"missing={missing[:3]}, extra={extra[:3]}"
        )
    config = PropagationConfig(
        root_top_k=max(1, int(args.top_k)),
        max_candidate_nodes=max(1, int(args.max_candidate_nodes)),
        max_path_depth=max(1, int(args.max_path_depth)),
        edge_probability_method=args.edge_probability_method,
        stage1_weight=1.0,
    )
    safe_input_tokens = min(
        int(args.max_input_tokens),
        int(args.max_model_len) - int(args.max_tokens) - 512,
    )
    if safe_input_tokens < 1000:
        raise ValueError(
            "model context is too small for the requested output reserve: "
            f"max_model_len={args.max_model_len}, max_tokens={args.max_tokens}"
        )
    budget = PromptBudget(
        max_input_tokens=safe_input_tokens,
        max_evidence_records=max(5, int(args.max_evidence_records)),
        min_evidence_per_candidate=max(0, int(args.min_evidence_per_candidate)),
        max_edges_per_graph=max(1, int(args.max_edges_per_graph)),
        max_nodes_per_graph=max(1, int(args.max_nodes_per_graph)),
        max_description_chars=max(0, int(args.max_description_chars)),
        max_chains_per_graph=max(0, int(args.max_chains_per_graph)),
    )
    prepared = prepare_cases(
        cases,
        root_records,
        config=config,
        min_evidence_per_candidate=budget.min_evidence_per_candidate,
    )
    os.makedirs(args.output_dir, exist_ok=True)
    save_json(
        prepared,
        os.path.join(args.output_dir, "candidate_payloads.json"),
        indent=2,
    )

    backend = _build_backend(args)
    variants = list(dict.fromkeys(args.variants))
    anchor_variant = (
        VARIANT_PRIOR_EVIDENCE_GRAPH
        if VARIANT_PRIOR_EVIDENCE_GRAPH in variants
        else "llm_evidence_graph"
        if "llm_evidence_graph" in variants
        else variants[0]
    )
    alignment_steps = [
        int(
            build_prompt_package(
                case,
                variant=anchor_variant,
                pass_index=0,
                budget=budget,
                count_tokens=backend.count_tokens,
            ).pruning.get("budget_step", 0)
        )
        for case in prepared
    ]
    direct_decisions: Dict[str, List[Dict[str, Any]]] = {}
    variant_counts: Dict[str, Any] = {}
    for variant in variants:
        _records, audits, _packages, decisions = run_variant(
            prepared,
            variant=variant,
            backend=backend,
            budget=budget,
            batch_size=args.batch_size,
            save_prompts=args.save_prompts,
            output_dir=args.output_dir,
            minimum_budget_steps=alignment_steps,
        )
        direct_decisions[variant] = decisions
        variant_counts[variant] = {
            "cases": len(decisions),
            "valid_responses": sum(bool(item.get("valid")) for item in decisions),
            "abstentions": sum(bool(item.get("abstained")) for item in decisions),
            "unsupported_evidence_references": sum(
                len(item.get("unsupported_evidence_ids", [])) for item in decisions
            ),
            "unsupported_graph_edge_references": sum(
                len(item.get("unsupported_graph_edges", [])) for item in decisions
            ),
            "mean_input_tokens": (
                sum(int(item.get("input_tokens", 0)) for item in audits) / len(audits)
                if audits
                else 0.0
            ),
        }

    if VARIANT_PRIOR_EVIDENCE_GRAPH in direct_decisions:
        _consensus_records, consensus_audits = run_consensus(
            prepared,
            direct_decisions=direct_decisions[VARIANT_PRIOR_EVIDENCE_GRAPH],
            backend=backend,
            budget=budget,
            batch_size=args.batch_size,
            consistency_passes=max(1, int(args.consistency_passes)),
            save_prompts=args.save_prompts,
            output_dir=args.output_dir,
        )
        variant_counts[CONSENSUS_METHOD] = {
            "cases": len(consensus_audits),
            "promotions": sum(
                bool(item.get("consensus", {}).get("promoted"))
                for item in consensus_audits
            ),
            "fallback_no_consensus": sum(
                item.get("consensus", {}).get("status") == "fallback_no_consensus"
                for item in consensus_audits
            ),
        }

    manifest = {
        "method_version": METHOD_VERSION,
        "evaluation_boundary": (
            "label-free inference; root labels must be joined only by the separate scorer"
        ),
        "data_root": os.path.abspath(args.data_root),
        "root_results": os.path.abspath(args.root_results),
        "case_count": len(prepared),
        "variants": variants,
        "consensus_method": (
            CONSENSUS_METHOD
            if VARIANT_PRIOR_EVIDENCE_GRAPH in variants
            else None
        ),
        "model": getattr(backend, "model_path", "mock"),
        "backend": getattr(backend, "name", type(backend).__name__),
        "model_load_seconds": _safe_float(
            getattr(backend, "model_load_seconds", 0.0)
        ),
        "total_wall_seconds": time.perf_counter() - started,
        "generation": {
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "max_model_len": args.max_model_len,
            "batch_size": args.batch_size,
            "consistency_passes": args.consistency_passes,
        },
        "prompt_budget": budget.__dict__,
        "propagation_config": config.to_dict(),
        "variant_diagnostics": variant_counts,
    }
    manifest_path = os.path.join(args.output_dir, "run_manifest.json")
    save_json(manifest, manifest_path, indent=2)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local Qwen32B Top-K propagation-graph listwise reranker"
    )
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--root-results", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--npu", default="0")
    parser.add_argument("--variants", nargs="+", choices=SUPPORTED_VARIANTS, default=list(SUPPORTED_VARIANTS))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1536)
    parser.add_argument("--max-model-len", type=int, default=16384)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--consistency-passes", type=int, default=3)
    parser.add_argument("--max-input-tokens", type=int, default=12000)
    parser.add_argument("--max-evidence-records", type=int, default=80)
    parser.add_argument("--min-evidence-per-candidate", type=int, default=3)
    parser.add_argument("--max-edges-per-graph", type=int, default=24)
    parser.add_argument("--max-nodes-per-graph", type=int, default=30)
    parser.add_argument("--max-description-chars", type=int, default=160)
    parser.add_argument("--max-chains-per-graph", type=int, default=5)
    parser.add_argument("--max-candidate-nodes", type=int, default=80)
    parser.add_argument("--max-path-depth", type=int, default=8)
    parser.add_argument(
        "--edge-probability-method",
        choices=("deterministic_evidence_v1", "logit_softmax_v1"),
        default="deterministic_evidence_v1",
    )
    parser.add_argument("--save-prompts", action="store_true")
    parser.add_argument("--mock", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
