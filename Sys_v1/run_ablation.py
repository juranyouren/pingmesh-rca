from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from .config import ABLATION_SPECS
from .llm import LocalVllmReviewer
from .pipeline import PipelineSettings, run_variant


REPO_ROOT = Path(__file__).resolve().parents[1]


def _default_data_root() -> str:
    env = os.environ.get("PINGMESH_DATA")
    if env:
        return env
    local = REPO_ROOT / "data" / "node" / "nodes_labeled"
    return str(local)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run isolated Sys_v1 RCA ablations.")
    parser.add_argument(
        "--variant",
        choices=[*ABLATION_SPECS, "all"],
        default="all",
        help="Ablation to run; 'all' runs the four simple variants.",
    )
    parser.add_argument("--data-root", "-d", default=_default_data_root())
    parser.add_argument(
        "--output-dir",
        "-o",
        default=str(REPO_ROOT / "data" / "res" / "sys_v1" / str(int(time.time()))),
    )
    parser.add_argument("--top-k", "-k", type=int, default=10)
    parser.add_argument("--single-source-margin", type=float, default=0.15)
    parser.add_argument("--multi-source-margin", type=float, default=0.08)
    parser.add_argument("--semantic-cache-dir", default=None)
    parser.add_argument("--max-events-per-device", type=int, default=30)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--save-prompts", action="store_true")
    parser.add_argument("--llm-backend", choices=["none", "vllm"], default="none")
    parser.add_argument("--model-path", default=os.environ.get("PINGMESH_MODEL_PATH", ""))
    parser.add_argument("--npu-cards", default=os.environ.get("PINGMESH_NPU_CARDS", "0,1"))
    parser.add_argument("--llm-batch-size", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--max-model-len", type=int, default=16384)
    args = parser.parse_args()

    if args.top_k <= 0:
        parser.error("--top-k must be positive")
    if args.llm_backend == "vllm" and not args.model_path:
        parser.error("--model-path or PINGMESH_MODEL_PATH is required for vllm")

    settings = PipelineSettings(
        top_k=args.top_k,
        single_source_accept_margin=args.single_source_margin,
        multi_source_accept_margin=args.multi_source_margin,
        semantic_cache_dir=args.semantic_cache_dir,
        max_events_per_device=args.max_events_per_device,
        save_prompts=args.save_prompts,
        llm_batch_size=args.llm_batch_size,
    )
    reviewer = None
    if args.llm_backend == "vllm":
        reviewer = LocalVllmReviewer(
            model_path=args.model_path,
            npu_cards=args.npu_cards,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            max_model_len=args.max_model_len,
        )

    variants = list(ABLATION_SPECS) if args.variant == "all" else [args.variant]
    for variant in variants:
        variant_dir = os.path.join(args.output_dir, variant)
        print(f"[Sys_v1] running {variant} -> {variant_dir}", flush=True)
        result_path = run_variant(
            data_root=args.data_root,
            output_dir=variant_dir,
            variant=variant,
            settings=settings,
            llm_backend=args.llm_backend,
            reviewer=reviewer,
            max_cases=args.max_cases,
        )
        print(f"[Sys_v1] result: {result_path}", flush=True)

    print(
        "Evaluate with: python -m Sys_v1.evaluate "
        f"--results-root \"{args.output_dir}\"",
        flush=True,
    )


if __name__ == "__main__":
    main()
