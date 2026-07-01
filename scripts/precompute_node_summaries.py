#!/usr/bin/env python3
"""Precompute node summaries for Pingmesh RCA cases.

Run this ONCE before the main inference run, on a dedicated NPU card.
The main SkilledAnalyzer then reads the cache via --summary-cache-dir
and never initialises a summary vLLM model.

Usage:
    export ASCEND_RT_VISIBLE_DEVICES=0
    export VLLM_WORKER_MULTIPROC_METHOD=spawn
    export OMP_NUM_THREADS=1
    python scripts/precompute_node_summaries.py \
        --data-root /path/to/cases \
        --out-cache /path/to/cache_dir \
        --model-path /path/to/Qwen2.5-0.5B \
        --npu-cards 0 --top-k 10
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
from Sys.RootCauseAnalyze.gate.node_summarizer import (
    VllmNodeSummarizer,
    summarize_nodes_with,
)
from Sys.utils.case_utils import find_full_link_file
from Sys.utils.io_utils import load_json, save_json


def case_cache_key(dirpath: str) -> str:
    return hashlib.sha1(os.path.abspath(dirpath).encode("utf-8")).hexdigest()


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
        description="Precompute node summaries for Pingmesh RCA cases."
    )
    parser.add_argument(
        "--data-root", "-d",
        default=config.data.nodes_labeled,
        help="case 数据根目录",
    )
    parser.add_argument(
        "--failures-from",
        default=None,
        help="只预处理指定 failures JSON 中的 case",
    )
    parser.add_argument(
        "--out-cache",
        required=True,
        help="summary cache 输出目录",
    )
    parser.add_argument(
        "--model-path",
        default=os.environ.get(
            "PINGMESH_SUMMARY_MODEL_PATH",
            "/usr/share/large_language_models/Qwen2.5-0.5B",
        ),
        help="summary 小模型路径",
    )
    parser.add_argument(
        "--npu-cards",
        default=os.environ.get("PINGMESH_SUMMARY_NPU_CARDS", "0"),
        help="summary 小模型使用的 NPU，例如 0",
    )
    parser.add_argument(
        "--top-k", "-k",
        type=int,
        default=config.temporal.top_k,
        help="候选节点数量",
    )
    parser.add_argument(
        "--summary-max-tokens",
        type=int,
        default=int(os.environ.get("PINGMESH_SUMMARY_MAX_TOKENS", "1024")),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已有 summary cache",
    )

    args = parser.parse_args()

    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = args.npu_cards
    os.environ["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"
    os.environ.setdefault("OMP_NUM_THREADS", "1")

    out_cache = Path(args.out_cache)
    out_cache.mkdir(parents=True, exist_ok=True)

    if args.failures_from:
        dirpaths = get_dirpaths_from_fcases(args.failures_from)
    else:
        dirpaths = discover_cases(args.data_root)

    print(f"[precompute] cases={len(dirpaths)}")
    print(f"[precompute] model={args.model_path}")
    print(f"[precompute] ASCEND_RT_VISIBLE_DEVICES={args.npu_cards}")
    print(f"[precompute] out_cache={out_cache}")

    executor = BuiltinSkillProvider()

    manifest = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model_path": args.model_path,
        "npu_cards": args.npu_cards,
        "top_k": args.top_k,
        "total": len(dirpaths),
        "items": [],
    }

    with VllmNodeSummarizer(
        model_path=args.model_path,
        npu_cards=args.npu_cards,
        max_tokens=args.summary_max_tokens,
    ) as summarizer:
        for dirpath in dirpaths:
            key = case_cache_key(dirpath)
            out_path = out_cache / f"{key}.json"

            if out_path.exists() and not args.overwrite:
                manifest["items"].append({
                    "dir": dirpath,
                    "cache": str(out_path),
                    "status": "skipped_exists",
                })
                print(f"  skip {dirpath} (cached)")
                continue

            try:
                skill_ret, info_data, detail_compact, detail_raw, skill_ips = build_fused_evidence(
                    node_list=executor.get_node_list(dirpath),
                    info=executor.get_alarminfo(dirpath),
                    dirpath=dirpath,
                    skill_map=executor.skill_map,
                    weight_dirpath=config.data.alarm_weights,
                    top_k=args.top_k,
                )

                summary = summarize_nodes_with(
                    detail_compact,
                    summarize_batch=summarizer.summarize_batch,
                )

                record = {
                    "dir": dirpath,
                    "cache_key": key,
                    "top_k": args.top_k,
                    "skill_ips": skill_ips,
                    "summary": summary,
                    "raw_chars": len(detail_compact),
                    "summary_chars": len(summary),
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                save_json(record, str(out_path))
                manifest["items"].append({
                    "dir": dirpath, "cache": str(out_path), "status": "ok",
                })
                print(f"  ok  {dirpath}  ({record['raw_chars']}→{record['summary_chars']} chars)")

            except Exception as e:
                err_path = out_cache / f"{key}.error.json"
                save_json({
                    "dir": dirpath, "cache_key": key,
                    "error": repr(e),
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }, str(err_path))
                manifest["items"].append({
                    "dir": dirpath, "cache": str(err_path), "status": "error",
                    "error": repr(e),
                })
                print(f"  ERR {dirpath}: {e}")

    save_json(manifest, str(out_cache / "manifest.json"))
    ok_n = sum(1 for i in manifest["items"] if i["status"] == "ok")
    skip_n = sum(1 for i in manifest["items"] if i["status"] == "skipped_exists")
    err_n = sum(1 for i in manifest["items"] if i["status"] == "error")
    print(f"[precompute] done. ok={ok_n} skipped={skip_n} errors={err_n}")
    print(f"[precompute] manifest={out_cache / 'manifest.json'}")


if __name__ == "__main__":
    main()
