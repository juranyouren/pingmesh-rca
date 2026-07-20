from __future__ import annotations

from typing import Any, Mapping, Sequence


GATE_POLICY_VERSION = "sys-v1-simple-confidence-v1"


def _positive_source(scores: Mapping[str, float]) -> bool:
    return bool(scores) and max((float(value) for value in scores.values()), default=0.0) > 0.0


def assess_confidence(
    ranking: Sequence[Mapping[str, Any]],
    source_scores: Mapping[str, Mapping[str, float]],
    *,
    single_source_accept_margin: float = 0.15,
    multi_source_accept_margin: float = 0.08,
) -> dict[str, Any]:
    """Route a ranking without labels using score margin and source agreement."""

    active_sources = {
        name: scores for name, scores in source_scores.items() if _positive_source(scores)
    }
    if not ranking or not active_sources:
        return {
            "enabled": True,
            "policy_version": GATE_POLICY_VERSION,
            "decision_state": "insufficient",
            "action": "operator_review",
            "reason": "no_usable_ranking_evidence",
            "score_margin": 0.0,
            "active_sources": list(active_sources),
            "source_top1": {},
        }

    top1_score = float(ranking[0].get("combined_score", 0.0) or 0.0)
    top2_score = float(ranking[1].get("combined_score", 0.0) or 0.0) if len(ranking) > 1 else 0.0
    margin = max(0.0, top1_score - top2_score)
    source_top1 = {
        name: min(scores.items(), key=lambda item: (-float(item[1]), item[0]))[0]
        for name, scores in active_sources.items()
    }
    if len(active_sources) == 1:
        if margin >= single_source_accept_margin:
            state, action, reason = "reliable", "accept", "single_source_large_margin"
        else:
            state, action, reason = "conflicting", "llm_review", "single_source_low_margin"
    else:
        agreement = len(set(source_top1.values())) == 1
        if agreement and margin >= multi_source_accept_margin:
            state, action, reason = "reliable", "accept", "multi_source_agreement_with_margin"
        elif not agreement:
            state, action, reason = "conflicting", "llm_review", "score_source_top1_conflict"
        else:
            state, action, reason = "conflicting", "llm_review", "multi_source_low_margin"

    return {
        "enabled": True,
        "policy_version": GATE_POLICY_VERSION,
        "decision_state": state,
        "action": action,
        "reason": reason,
        "score_margin": round(margin, 6),
        "active_sources": list(active_sources),
        "source_top1": source_top1,
        "thresholds": {
            "single_source_accept_margin": single_source_accept_margin,
            "multi_source_accept_margin": multi_source_accept_margin,
        },
    }


def disabled_gate(ranking: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "enabled": False,
        "policy_version": GATE_POLICY_VERSION,
        "decision_state": "not_evaluated",
        "action": "accept",
        "reason": "m3_disabled",
        "score_margin": (
            round(
                float(ranking[0].get("combined_score", 0.0) or 0.0)
                - float(ranking[1].get("combined_score", 0.0) or 0.0),
                6,
            )
            if len(ranking) > 1
            else 0.0
        ),
    }
