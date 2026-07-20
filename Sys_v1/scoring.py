from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence, Tuple

from Sys.RootCauseAnalyze.skills.temporal_ranker import temporal_feature_details
from Sys.utils.case_utils import get_device_ip


def score_temporal(
    node_list: Sequence[Dict[str, Any]],
    info: Mapping[str, Any],
    *,
    dirpath: str,
) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]], Dict[str, Any]]:
    """Compute the existing deterministic temporal features without labels."""

    features, diagnostics = temporal_feature_details(list(node_list), dict(info), dirpath)
    raw_scores = {
        ip: float(values.get("raw_temporal_score", 0.0) or 0.0)
        for ip, values in features.items()
    }
    max_score = max(raw_scores.values(), default=0.0)
    scores = {
        ip: (score / max_score if max_score > 0 else 0.0)
        for ip, score in raw_scores.items()
    }
    return scores, features, diagnostics


def device_ips(node_list: Sequence[Dict[str, Any]]) -> list[str]:
    return sorted(
        {
            ip
            for node in node_list
            if (ip := get_device_ip(node)) and ip != "unknown"
        }
    )


def mean_enabled_scores(
    source_scores: Mapping[str, Mapping[str, float]],
    candidate_ips: Sequence[str],
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Average every score source explicitly enabled by the ablation.

    This implements the first Sys_v1 fusion rule. Full M123 averages topology
    and temporal scores. A component ablation averages only sources that the
    ablation actually enables, so M1+M3 becomes topology-only and M2+M3 becomes
    temporal-only rather than secretly reintroducing an ablated module. An
    enabled all-zero source remains in the arithmetic mean and is separately
    recorded as a zero-signal source for Gate diagnostics.
    """

    enabled = {
        name: dict(scores)
        for name, scores in source_scores.items()
        if scores
    }
    unavailable = [name for name in source_scores if name not in enabled]
    zero_signal = [
        name
        for name, scores in enabled.items()
        if max((float(value) for value in scores.values()), default=0.0) <= 0.0
    ]
    if not enabled:
        return {}, {
            "method": "strict_mean_of_enabled_sources_v1",
            "sources_used": [],
            "sources_unavailable": unavailable,
            "zero_signal_sources": [],
            "weights": {},
        }

    weight = 1.0 / len(enabled)
    combined = {
        ip: sum(float(scores.get(ip, 0.0) or 0.0) for scores in enabled.values()) * weight
        for ip in candidate_ips
    }
    return combined, {
        "method": "strict_mean_of_enabled_sources_v1",
        "sources_used": list(enabled),
        "sources_unavailable": unavailable,
        "zero_signal_sources": zero_signal,
        "weights": {name: weight for name in enabled},
    }


def ranking_rows(
    combined_scores: Mapping[str, float],
    source_scores: Mapping[str, Mapping[str, float]],
    *,
    limit: int | None = None,
) -> list[Dict[str, Any]]:
    items = sorted(combined_scores.items(), key=lambda item: (-item[1], item[0]))
    if limit is not None:
        items = items[:limit]
    rows = []
    for rank, (ip, score) in enumerate(items, 1):
        rows.append(
            {
                "rank": rank,
                "ip": ip,
                "combined_score": round(float(score), 6),
                "source_scores": {
                    name: round(float(values.get(ip, 0.0) or 0.0), 6)
                    for name, values in source_scores.items()
                },
            }
        )
    return rows
