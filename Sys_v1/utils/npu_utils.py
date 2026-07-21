"""
Ascend NPU memory inspection and wait utilities.

Used by SkilledAnalyzer to avoid vLLM OOM when previous processes
still hold NPU memory.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _run_npu_smi(args: List[str], timeout: float = 10) -> str:
    """Run npu-smi and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            ["npu-smi", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout or ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("npu-smi command failed: %s", exc)
        return ""


# ── memory ────────────────────────────────────────────────────────────

# npu-smi on 910B3 outputs two "Usage" columns per NPU block:
#   Memory-Usage(MB) = 0 / 0        ← device memory (often zero)
#   HBM-Usage(MB)    = 3381 / 65536 ← the real HBM we care about
# The unit (MB/GB) appears in the column header, not after each number.
# Try HBM-Usage first; fall back to Memory-Usage for older hardware.

_HBM_LINE = re.compile(
    r"NPU\s*(?:ID|#)?\s*[：:]\s*(\d+)\s*.*?"
    r"HBM-Usage.*?"
    r"(\d+)\s*/\s*(\d+)",
    re.IGNORECASE | re.DOTALL,
)

_MEM_LINE = re.compile(
    r"NPU\s*(?:ID|#)?\s*[：:]\s*(\d+)\s*.*?"
    r"Memory-Usage.*?"
    r"(\d+)\s*/\s*(\d+)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_npu_smi_memory(out: str, card_ids: Optional[List[int]] = None) -> Dict[int, Dict[str, int]]:
    """Try HBM-Usage first; if none found, fall back to Memory-Usage."""
    info: Dict[int, Dict[str, int]] = {}
    for regex in (_HBM_LINE, _MEM_LINE):
        for match in regex.finditer(out):
            cid = int(match.group(1))
            if card_ids is not None and cid not in card_ids:
                continue
            if cid in info:
                continue  # already captured via HBM
            used = int(match.group(2))
            total = int(match.group(3))
            info[cid] = {"total": total, "used": used, "free": total - used}
        if info:
            break
    return info


def get_npu_memory_info(card_ids: Optional[List[int]] = None) -> Dict[int, Dict[str, int]]:
    """Return {card_id: {"total": MiB, "used": MiB, "free": MiB}} for each card.

    Parses ``npu-smi info -t memory`` (preferring HBM-Usage), falls back to
    ``npu-smi info -m``.
    """
    out = _run_npu_smi(["info", "-t", "memory"])
    if not out:
        out = _run_npu_smi(["info", "-m"])
    if not out:
        return {}

    return _parse_npu_smi_memory(out, card_ids)


def get_npu_free_memory(card_ids: List[int]) -> Dict[int, int]:
    """Return {card_id: free_MiB} for the specified cards."""
    info = get_npu_memory_info(card_ids)
    return {cid: v["free"] for cid, v in info.items()}


# ── processes ─────────────────────────────────────────────────────────

_PROC_CARD = re.compile(r"NPU\s*(?:ID|#)?\s*[：:]\s*(\d+)", re.IGNORECASE)
_PROC_PID = re.compile(r"(?:Process|进程).*?(\d+)", re.IGNORECASE)
_PROC_MEM = re.compile(r"(\d+)\s*(?:MB|GiB|GB|MiB)", re.IGNORECASE)


def list_npu_processes(card_ids: Optional[List[int]] = None) -> List[Dict[str, object]]:
    """List processes currently using NPU cards.

    Returns list of {"card": int, "pid": int, "memory_mib": int} dicts.
    """
    out = _run_npu_smi(["info", "-t", "process"])
    if not out:
        return []

    # Split into per-NPU blocks separated by blank lines.
    blocks = re.split(r"\n\s*\n", out)

    processes: List[Dict[str, object]] = []
    for block in blocks:
        if not block.strip():
            continue
        # Card ID
        cm = _PROC_CARD.search(block)
        if not cm:
            continue
        cid = int(cm.group(1))
        if card_ids is not None and cid not in card_ids:
            continue
        # Process ID — look for "Process" keyword followed by digits
        pm = _PROC_PID.search(block)
        if not pm:
            continue
        pid = int(pm.group(1))
        # Memory
        mem_matches = _PROC_MEM.findall(block)
        mem = int(mem_matches[0]) if mem_matches else 0
        processes.append({"card": cid, "pid": pid, "memory_mib": mem})
    return processes


# ── wait / poll ───────────────────────────────────────────────────────


def wait_npu_memory(
    card_ids: List[int],
    *,
    required_free_ratio: float = 0.25,
    timeout: float = 1800.0,
    poll_interval: float = 15.0,
) -> bool:
    """Block until every card in *card_ids* has ≥ *required_free_ratio* of total memory free.

    Returns ``True`` when the condition is met, ``False`` on timeout.

    Parameters
    ----------
    card_ids:
        NPU card IDs to check.
    required_free_ratio:
        Fraction of total memory that must be free (default 0.25 = 25 %).
    timeout:
        Maximum total wait time in seconds (default 1800 = 30 min).
    poll_interval:
        Seconds between polls (default 15).
    """
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        info = get_npu_memory_info(card_ids)
        if not info:
            logger.info(
                "npu-smi returned no data for cards %s; waiting %s s ...",
                card_ids, poll_interval,
            )
            time.sleep(poll_interval)
            continue

        blocked = []
        for cid in card_ids:
            mem = info.get(cid, {})
            total = mem.get("total", 1)
            free = mem.get("free", 0)
            if free / total < required_free_ratio:
                blocked.append(f"NPU {cid}: {free}/{total} MiB free")

        if not blocked:
            logger.info("NPU cards %s have sufficient free memory.", card_ids)
            return True

        # Report blockers
        procs = list_npu_processes(card_ids)
        proc_desc = ", ".join(
            f"NPU{p['card']}:pid={p['pid']}({p['memory_mib']}MiB)"
            for p in procs
        ) if procs else "no processes reported"
        logger.info(
            "NPU memory insufficient (need ≥%.0f%% free). Blocked: %s. "
            "Current occupants: %s. Waiting %s s ...",
            required_free_ratio * 100,
            "; ".join(blocked),
            proc_desc,
            poll_interval,
        )
        time.sleep(poll_interval)

    logger.warning("Timed out after %.0f s waiting for NPU memory on cards %s.", timeout, card_ids)
    return False
