from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Tuple


def truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def unique_ips(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    for value in values:
        if isinstance(value, str) and value and value not in out:
            out.append(value)
    return out


def score_key_for(method: str) -> str:
    if method == "topo":
        return "pr_score"
    if method == "temporal":
        return "score"
    return "combined_score"


def normalize_entries(rankings: Any, score_key: str) -> List[Dict[str, Any]]:
    if not isinstance(rankings, list):
        return []
    entries: List[Dict[str, Any]] = []
    for item in rankings:
        if not isinstance(item, dict):
            continue
        ip = item.get("ip")
        if not isinstance(ip, str) or not ip:
            continue
        copied = dict(item)
        copied["score"] = as_float(item.get(score_key, item.get("score", 0.0)))
        entries.append(copied)
    return sorted(entries, key=lambda row: (-row["score"], row["ip"]))


def ips_from_entries(entries: Sequence[Dict[str, Any]], limit: int | None = None) -> List[str]:
    selected = entries[:limit] if limit is not None else entries
    return unique_ips(row.get("ip") for row in selected)


def top1_largest_local_gap(entries: Sequence[Dict[str, Any]]) -> bool:
    if len(entries) < 2:
        return False
    scores = [as_float(row.get("score")) for row in entries]
    gaps = [scores[i] - scores[i + 1] for i in range(len(scores) - 1)]
    if not gaps or gaps[0] <= 0:
        return False
    if len(gaps) == 1:
        return True
    return gaps[0] > max(gaps[1:])


def top3_overlap(left_ips: Sequence[str], right_ips: Sequence[str]) -> Tuple[int, List[str]]:
    left = list(left_ips[:3])
    right = list(right_ips[:3])
    overlap = [ip for ip in left if ip in set(right)]
    return len(overlap), overlap


def tree_result(
    *,
    state: str,
    passed: Sequence[str],
    failed: Sequence[str],
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "state": state,
        "passed": list(passed),
        "failed": list(failed),
        "evidence": evidence,
    }
