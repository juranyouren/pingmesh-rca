"""
graph_only.py — 纯图算法消融实验
===============================
仅使用 PageRank（Skill 1），不依赖 LLM / NPU。
向后兼容旧接口，内部委托给 skill_pipeline。
"""

import os
import time

from Sys.RootCauseAnalyze.skill_pipeline import run_skill_pipeline


def run_ablation_experiment(root_path: str, output_dir: str, directed: bool = False):
    """
    遍历数据集，只跑图算法（无向 PageRank 或有向 PageRank）。
    此函数保留向后兼容性，实际逻辑已迁移到 skill_pipeline。
    """
    return run_skill_pipeline(
        data_root=root_path,
        output_dir=output_dir,
        skill_ids=[1],        # ← 只跑 topo
        directed=directed,
        top_k=5,
    )


if __name__ == "__main__":
    import argparse

    try:
        from Sys.config import config
        _data = config.data.nodes_labeled
        _res = config.data.results
    except Exception:
        _data = "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"
        _res = "/home/sbp/lixinyang/pingmesh/data/res"

    p = argparse.ArgumentParser(description="graph_only — 纯图算法消融实验 (不依赖 LLM)")
    p.add_argument("--data-root", "-d", default=_data, help="数据根目录")
    p.add_argument("--output-dir", "-o", default=None,
                   help="结果输出子目录名（相对于 results）")
    p.add_argument("--directed", action="store_true", default=False,
                   help="使用有向 PageRank（默认: 无向）")
    args = p.parse_args()

    variant = "_dir" if args.directed else "_undir"
    timenow = int(time.time())

    if args.output_dir:
        out_dir = os.path.join(_res, args.output_dir)
    else:
        out_dir = os.path.join(_res, f"graph_only{variant}_{timenow}")

    run_ablation_experiment(args.data_root, out_dir, directed=args.directed)
