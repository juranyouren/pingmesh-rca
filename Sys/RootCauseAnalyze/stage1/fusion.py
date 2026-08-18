from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from Sys.RootCauseAnalyze.stage1.alarm_topology_ranker import score_topo, topo_details
from Sys.RootCauseAnalyze.stage1.temporal_ranker import score_temporal, temporal_details
from Sys.utils.case_utils import get_device_ip
from Sys.utils.ranking_utils import combine_scores, sorted_score_items


BASELINE_RANKERS = {
    1: score_topo,
    2: score_temporal,
}


def _combine_scores(ranker_scores: Dict[int, Dict[str, float]], node_ips: Sequence[str]) -> List[str]:
    if not ranker_scores:
        return list(node_ips[:5]) if node_ips else []
    return [ip for ip, _score in sorted_score_items(combine_scores(ranker_scores, node_ips))]


def _combined_score_items(
    ranker_scores: Dict[int, Dict[str, float]],
    node_ips: Sequence[str],
    top_k: int,
) -> List[Tuple[str, float]]:
    return sorted_score_items(combine_scores(ranker_scores, node_ips), top_k)


def rank_root_causes(
    node_list: List[Dict[str, Any]],
    info: Dict[str, Any],
    dirpath: str = "",
    ranker_ids: Sequence[int] = (1, 2),
    directed: bool = True,
    weight_dirpath: str | None = None,
    top_k: int = 5,
) -> Tuple[List[str], Dict[str, Any]]:
    """Run the deterministic Stage 1 baseline.

    Numeric ranker IDs are retained as stable serialized identifiers:
    ``"1"`` is topology and ``"2"`` is temporal.
    """
    ranker_scores: Dict[int, Dict[str, float]] = {}
    ranking_details: Dict[str, Any] = {}
    all_ips = sorted({get_device_ip(node) for node in node_list if get_device_ip(node) != "unknown"})

    normalized_ranker_ids = [int(ranker_id) for ranker_id in ranker_ids]
    for ranker_id in normalized_ranker_ids:
        try:
            if ranker_id == 1:
                scores = score_topo(node_list, info, weight_path=weight_dirpath, directed=directed)
            elif ranker_id == 2:
                scores = score_temporal(node_list, info, dirpath=dirpath)
            else:
                scores = {}
        except Exception:
            scores = {}
        if scores:
            ranker_scores[ranker_id] = scores
        if ranker_id == 1:
            ranking_details["1"] = topo_details(
                node_list, info, scores, weight_path=weight_dirpath, directed=directed, top_k=top_k
            )
        elif ranker_id == 2:
            ranking_details["2"] = temporal_details(node_list, info, dirpath, scores, top_k=top_k)

    if 1 in normalized_ranker_ids and "1" not in ranking_details:
        ranking_details["1"] = topo_details(
            node_list, info, {}, weight_path=weight_dirpath, directed=directed, top_k=top_k
        )
    if 2 in normalized_ranker_ids and "2" not in ranking_details:
        ranking_details["2"] = temporal_details(node_list, info, dirpath, {}, top_k=top_k)

    ranked = _combine_scores(ranker_scores, all_ips)
    combined_topk = [
        {"rank": rank, "ip": ip, "combined_score": round(score, 6)}
        for rank, (ip, score) in enumerate(_combined_score_items(ranker_scores, all_ips, top_k), 1)
    ]
    ranking_details["combined"] = {
        "top3": combined_topk[:3],
        "topk": combined_topk,
        "rankings": combined_topk,
    }
    return ranked[:top_k], ranking_details
