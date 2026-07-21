from __future__ import annotations

import argparse
import json
import os
import time
from typing import Sequence

from Sys_v1.RootCauseAnalyze.skills.fusion import _combine_scores, rank_devices_by_skills
from Sys_v1.utils.case_utils import find_full_link_file, load_case_info, load_case_nodes, read_gt_ips
from Sys_v1.utils.io_utils import save_json

__all__ = ["_combine_scores", "rank_devices_by_skills", "run_skill_pipeline"]


def run_skill_pipeline(
    data_root: str,
    output_dir: str,
    skill_ids: Sequence[int] = (1, 2),
    directed: bool = True,
    top_k: int = 5,
    weight_path: str | None = None,
) -> str:
    if weight_path:
        resolved_weight_path = weight_path
    else:
        try:
            from Sys_v1.config import config

            resolved_weight_path = config.data.alarm_weights
        except Exception:
            resolved_weight_path = None

    mode_desc = "topo+temporal"
    print(f"Skill Pipeline ({mode_desc}, top_k={top_k})")
    print(f"Scanning: {data_root}")

    start_time = time.time()
    results = []
    case_count = 0

    for dirpath, _dirnames, filenames in os.walk(data_root):
        node_file = find_full_link_file(dirpath, filenames)
        if not (node_file and "info.json" in filenames):
            continue

        try:
            node_list = load_case_nodes(dirpath)
            info = load_case_info(dirpath)
            predicted_ips, details = rank_devices_by_skills(
                node_list,
                info,
                dirpath,
                skill_ids=skill_ids,
                directed=directed,
                weight_dirpath=resolved_weight_path,
                top_k=top_k,
            )

            mock_response = json.dumps(
                {
                    "reasoning": f"Deterministic skill pipeline ({mode_desc}), skill_ids={list(skill_ids)}.",
                    "ip": predicted_ips,
                    "skill_details": details,
                },
                ensure_ascii=False,
                indent=2,
            )
            mock_str = f"```json\n{mock_response}\n```"

            results.append(
                {
                    "dir": dirpath,
                    "prompt": f"SKILL_PIPELINE_{mode_desc.upper()}",
                    "draft_response": mock_str,
                    "response": mock_str,
                    "skill_ips": predicted_ips,
                    "gt_ips": read_gt_ips(dirpath),
                }
            )
            case_count += 1
        except Exception as exc:
            print(f"[Error] {dirpath}: {exc}")

    os.makedirs(output_dir, exist_ok=True)
    res_path = os.path.join(output_dir, "res.json")
    save_json(results, res_path, indent=4)

    elapsed = time.time() - start_time
    print(f"Done: {case_count} cases, {elapsed:.2f}s")
    print(f"Result: {res_path}")
    return res_path


def main() -> None:
    try:
        from Sys_v1.config import config

        data_root = config.data.nodes_labeled
        result_root = config.data.results
        default_skills = config.skill.skill_ids
    except Exception:
        data_root = "/home/sbp/lixinyang/pingmesh/data/node/nodes_max_labeled"
        result_root = "/home/sbp/lixinyang/pingmesh/data/res"
        default_skills = [1, 2]

    parser = argparse.ArgumentParser(description="Run deterministic RCA skill pipeline.")
    parser.add_argument("--data-root", "-d", default=data_root)
    parser.add_argument("--output-dir", "-o", default=None)
    parser.add_argument("--skills", "-s", nargs="*", type=int, default=default_skills)
    parser.add_argument("--directed", action="store_true", default=True)
    parser.add_argument("--top-k", "-k", type=int, default=5)
    parser.add_argument("--weight-file", "-w", default=None)
    args = parser.parse_args()

    variant = "dir" if args.directed else "undir"
    skill_tag = "_".join(str(sid) for sid in args.skills)
    if args.weight_file:
        skill_tag += f"__{os.path.splitext(os.path.basename(args.weight_file))[0]}"
    out_dir = (
        os.path.join(result_root, args.output_dir)
        if args.output_dir
        else os.path.join(result_root, f"skillpipe_{skill_tag}_{variant}_{int(time.time())}")
    )

    run_skill_pipeline(
        args.data_root,
        out_dir,
        skill_ids=args.skills,
        directed=args.directed,
        top_k=args.top_k,
        weight_path=args.weight_file,
    )


if __name__ == "__main__":
    main()
