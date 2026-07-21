from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Tuple


def sorted_score_items(scores: Dict[str, float], top_k: int | None = None) -> List[Tuple[str, float]]:
    items = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return items[:top_k] if top_k is not None else items


def combine_scores(skill_id_to_scores: Dict[int, Dict[str, float]], node_ips: Sequence[str]) -> Dict[str, float]:
    if not skill_id_to_scores:
        return {}
    combined: Dict[str, float] = {}
    for ip in node_ips:
        vals = [scores.get(ip, 0.0) for scores in skill_id_to_scores.values()]
        combined[ip] = sum(vals) / len(vals)
    return combined


def dedupe_ips(values: Iterable[object]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        ip = str(value) if value is not None else ""
        if ip and ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out
