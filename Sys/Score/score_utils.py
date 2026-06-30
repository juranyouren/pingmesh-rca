from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Sequence


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
    return any(ip in set(pred_ips[:k]) for ip in gt_ips)
