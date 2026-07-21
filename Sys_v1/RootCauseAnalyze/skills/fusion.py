from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from Sys_v1.RootCauseAnalyze.skills.temporal_ranker import score_temporal, temporal_details
from Sys_v1.RootCauseAnalyze.skills.topo_ranker import score_topo, topo_details
from Sys_v1.utils.case_utils import get_device_ip
from Sys_v1.utils.ranking_utils import combine_scores, sorted_score_items


SKILL_SCORER = {
    1: score_topo,
    2: score_temporal,
}


def _combine_scores(skill_id_to_scores: Dict[int, Dict[str, float]], node_ips: Sequence[str]) -> List[str]:
    if not skill_id_to_scores:
        return list(node_ips[:5]) if node_ips else []
    return [ip for ip, _score in sorted_score_items(combine_scores(skill_id_to_scores, node_ips))]


def _combined_score_items(
    skill_id_to_scores: Dict[int, Dict[str, float]],
    node_ips: Sequence[str],
    top_k: int,
) -> List[Tuple[str, float]]:
    return sorted_score_items(combine_scores(skill_id_to_scores, node_ips), top_k)


def rank_devices_by_skills(
    node_list: List[Dict[str, Any]],
    info: Dict[str, Any],
    dirpath: str = "",
    skill_ids: Sequence[int] = (1, 2),
    directed: bool = True,
    weight_dirpath: str | None = None,
    top_k: int = 5,
) -> Tuple[List[str], Dict[str, Any]]:
    skill_id_to_scores: Dict[int, Dict[str, float]] = {}
    skill_details: Dict[str, Any] = {}
    all_ips = sorted({get_device_ip(node) for node in node_list if get_device_ip(node) != "unknown"})

    normalized_skill_ids = [int(sid) for sid in skill_ids]
    for sid in normalized_skill_ids:
        try:
            if sid == 1:
                scores = score_topo(node_list, info, weight_path=weight_dirpath, directed=directed)
            elif sid == 2:
                scores = score_temporal(node_list, info, dirpath=dirpath)
            else:
                scores = {}
        except Exception:
            scores = {}
        if scores:
            skill_id_to_scores[sid] = scores
        if sid == 1:
            skill_details["1"] = topo_details(
                node_list, info, scores, weight_path=weight_dirpath, directed=directed, top_k=top_k
            )
        elif sid == 2:
            skill_details["2"] = temporal_details(node_list, info, dirpath, scores, top_k=top_k)

    if 1 in normalized_skill_ids and "1" not in skill_details:
        skill_details["1"] = topo_details(node_list, info, {}, weight_path=weight_dirpath, directed=directed, top_k=top_k)
    if 2 in normalized_skill_ids and "2" not in skill_details:
        skill_details["2"] = temporal_details(node_list, info, dirpath, {}, top_k=top_k)

    ranked = _combine_scores(skill_id_to_scores, all_ips)
    combined_topk = [
        {"rank": rank, "ip": ip, "combined_score": round(score, 6)}
        for rank, (ip, score) in enumerate(_combined_score_items(skill_id_to_scores, all_ips, top_k), 1)
    ]
    skill_details["combined"] = {
        "top3": combined_topk[:3],
        "topk": combined_topk,
        "rankings": combined_topk,
    }
    return ranked[:top_k], skill_details
