"""Canonical I/O and utility helpers — single source of truth for the project.

All modules should import from here; ``Sys_v1.Score.score_utils`` is a
backward-compatible shim that re-exports from this module.
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, Iterable, List, Sequence


def ensure_parent(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def load_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(data: Any, path: str, *, indent: int = 2) -> None:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def write_json(path: str, data: Any, *, indent: int = 2) -> None:
    """Mirrors ``save_json`` but accepts ``(path, data)`` for callers that
    prefer that order."""
    save_json(data, path, indent=indent)


def write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: str, rows: Iterable[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ── case / scoring helpers ───────────────────────────────────────────


def case_id_from_dir(path: str, fallback: str) -> str:
    name = os.path.basename(os.path.normpath(path or ""))
    return name or fallback


def dedupe(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for value in values:
        if isinstance(value, str) and value and value not in out:
            out.append(value)
    return out


def hit_at(pred_ips: Sequence[str], gt_ips: Sequence[str], k: int) -> bool | None:
    if not gt_ips:
        return None
    return any(ip in set(pred_ips[:k]) for ip in gt_ips)
