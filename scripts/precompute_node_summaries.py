#!/usr/bin/env python3
"""Precompute per-device node summaries for Pingmesh RCA cases.

Deploys one small vLLM instance per NPU card (--npu-cards 4,5,6,7 → 4 instances).
Each device is summarised independently (tiny prompt, no token overflow).
Devices within a case are distributed across cards for parallelism.

Run this ONCE before main inference:
    python scripts/precompute_node_summaries.py \
        --data-root /path/to/cases \
        --out-cache /path/to/cache_dir \
        --npu-cards 4,5,6,7 \
        --model-path /path/to/Qwen2.5-1.5B \
        --top-k 10
"""

import os

os.environ.setdefault("VLLM_WORKER_MULTIPROC_METHOD", "spawn")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import sys
import json
import time
import argparse
import hashlib
from pathlib import Path
from typing import List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from Sys.config import config
from Sys.RootCauseAnalyze.skills.provider import BuiltinSkillProvider
from Sys.RootCauseAnalyze.gate.evidence import build_fused_evidence
from Sys.RootCauseAnalyze.gate.evidence import EVIDENCE_ORGANIZATION_VERSION
from Sys.RootCauseAnalyze.gate.node_summarizer import MultiCardSummarizer
from Sys.utils.case_utils import find_full_link_file
from Sys.utils.io_utils import load_json, save_json


def gib_to_bytes(value: float) -> int:
    """Convert a positive GiB value to the vLLM cache-size argument."""
    if value <= 0:
        raise ValueError("KV cache size must be positive")
    return int(value * 1024**3)


def case_cache_key(dirpath: str, top_k: int) -> str:
    material = f"{EVIDENCE_ORGANIZATION_VERSION}|top_k={top_k}|{os.path.abspath(dirpath)}"
    return hashlib.sha1(material.encode("utf-8")).hexdigest()


def discover_cases(data_root: str) -> List[str]:
    cases: List[str] = []
    for dirpath, _, filenames in os.walk(data_root):
        if "info.json" in filenames and find_full_link_file(dirpath, filenames):
            cases.append(dirpath)
    return sorted(cases)


def get_dirpaths_from_fcases(fcase_path: str) -> List[str]:
    fcases = load_json(fcase_path)
    return [case.get("name") for case in fcases if case.get("name")]


def main():
    parser = argparse.ArgumentParser(
        description="Precompute per-device node summaries for Pingmesh RCA cases."
    )
    parser.add_argument("--data-root", "-d", default=config.data.nodes_labeled)
    parser.add_argument("--failures-from", default=None)
    parser.add_argument("--out-cache", required=True, help="summary cache 输出目录")
    parser.add_argument(
        "--model-path",
        default=os.environ.get(
            "PINGMESH_SUMMARY_MODEL_PATH",
            "/usr/share/large_language_models/Qwen2.5-0.5B",
        ),
    )
    parser.add_argument(
        "--npu-cards",
        default=os.environ.get("PINGMESH_SUMMARY_NPU_CARDS", "0"),
        help="summary 模型使用的 NPU 卡，逗号分隔，每卡一个实例 (如 4,5,6,7)",
    )
    parser.add_argument("--top-k", "-k", type=int, default=config.temporal.top_k)
    parser.add_argument(
        "--max-model-len", type=int,
        default=int(os.environ.get("PINGMESH_SUMMARY_MAX_MODEL_LEN", "4096")),
    )
    parser.add_argument(
        "--summary-max-tokens", type=int,
        default=int(os.environ.get("PINGMESH_SUMMARY_MAX_TOKENS", "512")),
    )
    parser.add_argument(
        "--kv-cache-gb", type=float,
        default=float(os.environ.get("PINGMESH_SUMMARY_KV_CACHE_GB", "4")),
        help="per-NPU KV cache cap in GiB; prevents vLLM-Ascend cache over-allocation",
    )
    parser.add_argument(
        "--num-gpu-blocks-override", type=int,
        default=int(os.environ.get("PINGMESH_SUMMARY_NUM_GPU_BLOCKS", "256")),
        help="fallback KV-block cap for older vLLM without byte-level cache caps",
    )
    parser.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()

    out_cache = Path(args.out_cache)
    out_cache.mkdir(parents=True, exist_ok=True)

    if args.failures_from:
        dirpaths = get_dirpaths_from_fcases(args.failures_from)
    else:
        dirpaths = discover_cases(args.data_root)

    print(f"[precompute] cases={len(dirpaths)}")
    print(f"[precompute] model={args.model_path}")
    print(f"[precompute] npu_cards={args.npu_cards}")
    print(f"[precompute] max_model_len={args.max_model_len}")
    print(f"[precompute] kv_cache_gb={args.kv_cache_gb}")
    print(f"[precompute] num_gpu_blocks_override={args.num_gpu_blocks_override}")
    print(f"[precompute] out_cache={out_cache}")

    executor = BuiltinSkillProvider()

    manifest = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model_path": args.model_path,
        "npu_cards": args.npu_cards,
        "top_k": args.top_k,
        "kv_cache_gb": args.kv_cache_gb,
        "num_gpu_blocks_override": args.num_gpu_blocks_override,
        "evidence_organization_version": EVIDENCE_ORGANIZATION_VERSION,
        "total": len(dirpaths),
        "items": [],
    }

    with MultiCardSummarizer(
        model_path=args.model_path,
        npu_cards=args.npu_cards,
        max_tokens=args.summary_max_tokens,
        max_model_len=args.max_model_len,
        kv_cache_memory_bytes=gib_to_bytes(args.kv_cache_gb),
        num_gpu_blocks_override=args.num_gpu_blocks_override,
    ) as summarizer:
        for dirpath in dirpaths:
            key = case_cache_key(dirpath, args.top_k)
            out_path = out_cache / f"{key}.json"

            if out_path.exists() and not args.overwrite:
                manifest["items"].append({
                    "dir": dirpath, "cache": str(out_path), "status": "skipped_exists",
                })
                print(f"  skip {os.path.basename(dirpath)} (cached)")
                continue

            try:
                _sr, _info, detail_compact, _raw, skill_ips = build_fused_evidence(
                    node_list=executor.get_node_list(dirpath),
                    info=executor.get_alarminfo(dirpath),
                    dirpath=dirpath,
                    skill_map=executor.skill_map,
                    weight_dirpath=config.data.alarm_weights,
                    top_k=args.top_k,
                )

                summary = summarizer.summarize_devices(detail_compact)

                record = {
                    "dir": dirpath, "cache_key": key, "top_k": args.top_k,
                    "evidence_organization_version": EVIDENCE_ORGANIZATION_VERSION,
                    "skill_ips": skill_ips, "summary": summary,
                    "raw_chars": len(detail_compact), "summary_chars": len(summary),
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                save_json(record, str(out_path))
                manifest["items"].append({
                    "dir": dirpath, "cache": str(out_path), "status": "ok",
                })
                print(
                    f"  ok  {os.path.basename(dirpath)}  "
                    f"({record['raw_chars']}→{record['summary_chars']} chars)"
                )

            except Exception as e:
                err_path = out_cache / f"{key}.error.json"
                save_json({
                    "dir": dirpath, "cache_key": key,
                    "error": repr(e),
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }, str(err_path))
                manifest["items"].append({
                    "dir": dirpath, "cache": str(err_path),
                    "status": "error", "error": repr(e),
                })
                print(f"  ERR {os.path.basename(dirpath)}: {e}")

    save_json(manifest, str(out_cache / "manifest.json"))
    ok_n = sum(1 for i in manifest["items"] if i["status"] == "ok")
    skip_n = sum(1 for i in manifest["items"] if i["status"] == "skipped_exists")
    err_n = sum(1 for i in manifest["items"] if i["status"] == "error")
    print(f"[precompute] done. ok={ok_n} skipped={skip_n} errors={err_n}")


if __name__ == "__main__":
    main()
