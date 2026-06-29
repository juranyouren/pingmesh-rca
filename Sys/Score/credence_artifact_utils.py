from __future__ import annotations

import csv
import json
import math
import os
import statistics
from typing import Any, Dict, Iterable, List, Sequence

from Sys.Score.Score_N import ResponseParser


LABEL_ONLY_COLUMNS = [
    "label_available",
    "gt_ips",
    "deterministic_hit_top1",
    "deterministic_hit_top3",
    "deterministic_hit_top5",
    "llm_hit_top1",
    "llm_hit_top3",
    "llm_hit_top5",
    "final_hit_top1",
]

FEATURE_COLUMNS = [
    "raw_confidence_score",
    "combined_margin",
    "combined_top_score",
    "topo_margin",
    "temporal_margin",
    "top1_votes_for_combined",
    "n_skill_ips",
    "diagnosability_score",
    "llm_output_available",
]


def ensure_parent(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: Any) -> None:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row {line_no} is not an object")
            rows.append(row)
    return rows


def write_csv(path: str, fieldnames: Sequence[str], rows: Iterable[Dict[str, Any]]) -> None:
    ensure_parent(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def case_id_from_dir(path: str, fallback: str) -> str:
    name = os.path.basename(os.path.normpath(path or ""))
    return name or fallback


def dedupe(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    out = []
    for value in values:
        if isinstance(value, str) and value and value not in out:
            out.append(value)
    return out


def hit_at(pred_ips: Sequence[str], gt_ips: Sequence[str], k: int) -> bool | None:
    if not gt_ips:
        return None
    top = list(pred_ips[:k])
    return any(ip in top for ip in gt_ips)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_llm_ips(response: str) -> List[str]:
    return ResponseParser().parse(response or "").ips


def raw_confidence_from_gate(gate: Dict[str, Any], skill_ips: Sequence[str], response: str) -> float:
    methods = gate.get("methods", {}) if isinstance(gate, dict) else {}
    combined = methods.get("combined", {}) if isinstance(methods, dict) else {}
    agreement = gate.get("agreement", {}) if isinstance(gate, dict) else {}
    margin = safe_float(combined.get("margin"))
    top_score = safe_float(combined.get("top_score"))
    votes = safe_float(agreement.get("top1_votes_for_combined"))

    margin_component = min(max(margin / 25.0, 0.0), 1.0)
    score_component = min(max(top_score / 100.0, 0.0), 1.0)
    agreement_component = min(max(votes / 3.0, 0.0), 1.0)
    availability_component = 1.0 if skill_ips else 0.0
    llm_component = 1.0 if response else 0.0

    raw = (
        0.40 * margin_component
        + 0.25 * score_component
        + 0.20 * agreement_component
        + 0.10 * availability_component
        + 0.05 * llm_component
    )
    return round(max(0.0, min(1.0, raw)), 6)


def diagnosability_from_row_parts(skill_ips: Sequence[str], gate: Dict[str, Any], response: str) -> float:
    methods = gate.get("methods", {}) if isinstance(gate, dict) else {}
    agreement = gate.get("agreement", {}) if isinstance(gate, dict) else {}
    score = 0.0
    if skill_ips:
        score += 0.30
    if methods.get("combined"):
        score += 0.25
    if methods.get("topo") or methods.get("temporal"):
        score += 0.20
    if safe_float(agreement.get("top1_votes_for_combined")) >= 2:
        score += 0.15
    if response:
        score += 0.10
    return round(max(0.0, min(1.0, score)), 6)


def binomial_cdf(k: int, n: int, p: float) -> float:
    if n <= 0:
        return 1.0
    total = 0.0
    for i in range(k + 1):
        total += math.comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i))
    return total


def clopper_pearson_upper(k: int, n: int, delta: float) -> float:
    if n <= 0:
        return 1.0
    if k >= n:
        return 1.0
    delta = max(min(delta, 0.999999), 1e-12)
    low = k / n
    high = 1.0
    for _ in range(80):
        mid = (low + high) / 2.0
        if binomial_cdf(k, n, mid) > delta:
            low = mid
        else:
            high = mid
    return round(high, 6)


def mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def bootstrap_ci(values: Sequence[float], repeats: int, seed: int) -> Dict[str, Any]:
    import random

    vals = list(values)
    if not vals:
        return {"estimate": None, "ci_low": None, "ci_high": None}
    rng = random.Random(seed)
    estimates = []
    for _ in range(max(1, repeats)):
        sample = [vals[rng.randrange(len(vals))] for _ in vals]
        estimates.append(sum(sample) / len(sample))
    estimates.sort()
    lo = estimates[int(0.025 * (len(estimates) - 1))]
    hi = estimates[int(0.975 * (len(estimates) - 1))]
    return {
        "estimate": round(sum(vals) / len(vals), 6),
        "ci_low": round(lo, 6),
        "ci_high": round(hi, 6),
    }


def brier_score(rows: Sequence[Dict[str, Any]]) -> float | None:
    vals = []
    for row in rows:
        hit = row.get("deterministic_hit_top1")
        if hit is None:
            continue
        c = safe_float(row.get("raw_confidence_score"))
        vals.append((c - (1.0 if hit else 0.0)) ** 2)
    return round(statistics.mean(vals), 6) if vals else None
