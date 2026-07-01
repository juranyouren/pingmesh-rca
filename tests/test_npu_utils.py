"""Tests for Sys.utils.npu_utils — uses mocked subprocess output."""

from __future__ import annotations

import unittest
from unittest.mock import patch

# Ensure project root is on sys.path for local test runs.
_PROJECT_ROOT = __import__("os").path.abspath(
    __import__("os").path.join(__import__("os").path.dirname(__file__), "..")
)
import sys as _sys

if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

from Sys.utils.npu_utils import (
    _HBM_LINE,
    _MEM_LINE,
    _parse_npu_smi_memory,
    _run_npu_smi,
    get_npu_memory_info,
    get_npu_free_memory,
    list_npu_processes,
    wait_npu_memory,
)

# ── sample npu-smi output snippets ────────────────────────────────────

# 910B3 format: Memory-Usage = 0/0, HBM-Usage has real data
_NPU_SMI_HBM = """
NPU ID                         : 0
Chip ID                        : 0
Memory-Usage(MB)               : 0 / 0
HBM-Usage(MB)                  : 18432 / 32768

NPU ID                         : 1
Chip ID                        : 0
Memory-Usage(MB)               : 0 / 0
HBM-Usage(MB)                  : 5120 / 32768

NPU ID                         : 2
Chip ID                        : 0
Memory-Usage(MB)               : 0 / 0
HBM-Usage(MB)                  : 24576 / 32768
"""

# Old format: Memory Usage(Capacity)
_NPU_SMI_MEMORY = """
NPU ID                         : 0
Chip ID                        : 0
Memory Usage(Capacity)         : 18432 MB / 32768 MB
"""

_NPU_SMI_PROCESS = """
NPU ID                         : 0
Process ID                     : 12345
Process Name                   : python3
Memory(MB)                     : 8192

NPU ID                         : 1
Process ID                     : 12346
Process Name                   : python3
Memory(MB)                     : 4096
"""


def _mock_run_ok(stdout):
    """Return a patcher for subprocess.run that returns *stdout*."""
    return patch("Sys.utils.npu_utils.subprocess.run", return_value=_FakeResult(stdout))


class _FakeResult:
    def __init__(self, stdout):
        self.stdout = stdout
        self.stderr = ""


class GetNpuMemoryInfoTest(unittest.TestCase):
    def test_parses_hbm_output(self):
        """910B3 format: HBM-Usage has real data, Memory-Usage is 0/0."""
        with _mock_run_ok(_NPU_SMI_HBM):
            info = get_npu_memory_info()

        self.assertIn(0, info)
        self.assertEqual(info[0]["total"], 32768)
        self.assertEqual(info[0]["used"], 18432)
        self.assertEqual(info[0]["free"], 32768 - 18432)

        self.assertIn(1, info)
        self.assertEqual(info[1]["used"], 5120)

    def test_filters_by_card_ids(self):
        with _mock_run_ok(_NPU_SMI_HBM):
            info = get_npu_memory_info(card_ids=[0])

        self.assertIn(0, info)
        self.assertNotIn(1, info)
        self.assertNotIn(2, info)

    def test_handles_npu_smi_unavailable(self):
        with patch("Sys.utils.npu_utils.subprocess.run", side_effect=FileNotFoundError):
            info = get_npu_memory_info()
        self.assertEqual(info, {})


class GetNpuFreeMemoryTest(unittest.TestCase):
    def test_returns_free_per_card(self):
        with _mock_run_ok(_NPU_SMI_HBM):
            free = get_npu_free_memory([0, 1])

        self.assertEqual(free[0], 32768 - 18432)
        self.assertEqual(free[1], 32768 - 5120)


class ListNpuProcessesTest(unittest.TestCase):
    def test_parses_process_output(self):
        with _mock_run_ok(_NPU_SMI_PROCESS):
            procs = list_npu_processes()

        self.assertEqual(len(procs), 2)
        self.assertEqual(procs[0]["card"], 0)
        self.assertEqual(procs[0]["pid"], 12345)
        self.assertEqual(procs[1]["card"], 1)
        self.assertEqual(procs[1]["pid"], 12346)

    def test_filters_by_card_ids(self):
        with _mock_run_ok(_NPU_SMI_PROCESS):
            procs = list_npu_processes(card_ids=[0])

        self.assertEqual(len(procs), 1)
        self.assertEqual(procs[0]["card"], 0)

    def test_handles_npu_smi_unavailable(self):
        with patch("Sys.utils.npu_utils.subprocess.run", side_effect=FileNotFoundError):
            procs = list_npu_processes()
        self.assertEqual(procs, [])


class WaitNpuMemoryTest(unittest.TestCase):
    def test_returns_immediately_when_memory_sufficient(self):
        # All cards have plenty of free memory
        ample_memory = """
NPU ID                         : 0
Memory Usage(Capacity)         : 2048 MB / 32768 MB
NPU ID                         : 1
Memory Usage(Capacity)         : 2048 MB / 32768 MB
"""
        # For this test we mock npu-smi to always return ample memory.
        with patch("Sys.utils.npu_utils.get_npu_memory_info", return_value={
            0: {"total": 32768, "used": 2048, "free": 30720},
            1: {"total": 32768, "used": 2048, "free": 30720},
        }):
            ok = wait_npu_memory([0, 1], required_free_ratio=0.25, timeout=1.0, poll_interval=0.01)
        self.assertTrue(ok)

    def test_times_out_when_memory_insufficient(self):
        # Cards are full
        full_memory = {
            0: {"total": 32768, "used": 32768, "free": 0},
        }
        with patch("Sys.utils.npu_utils.get_npu_memory_info", return_value=full_memory):
            with patch("Sys.utils.npu_utils.list_npu_processes", return_value=[]):
                ok = wait_npu_memory([0], required_free_ratio=0.25, timeout=0.1, poll_interval=0.05)
        self.assertFalse(ok)

    def test_retries_until_memory_frees(self):
        """First poll shows full memory, subsequent polls show free memory."""
        call_count = [0]

        def memory_evolving(card_ids):
            call_count[0] += 1
            if call_count[0] < 3:
                return {0: {"total": 32768, "used": 30000, "free": 2768}}
            return {0: {"total": 32768, "used": 2000, "free": 30768}}

        with patch("Sys.utils.npu_utils.get_npu_memory_info", side_effect=memory_evolving):
            with patch("Sys.utils.npu_utils.list_npu_processes", return_value=[]):
                ok = wait_npu_memory([0], required_free_ratio=0.25, timeout=5.0, poll_interval=0.02)
        self.assertTrue(ok)
        self.assertGreaterEqual(call_count[0], 3)


class MemLineRegexTest(unittest.TestCase):
    """Test that _HBM_LINE and _MEM_LINE can parse different formats."""

    def test_parses_hbm_format(self):
        """910B3: HBM-Usage(MB) = 3381 / 65536"""
        line = "NPU ID                         : 0\nHBM-Usage(MB)                  : 3381 / 65536"
        matches = _HBM_LINE.findall(line)
        self.assertEqual(len(matches), 1)
        # (card_id, used, total)
        self.assertEqual(matches[0], ("0", "3381", "65536"))

    def test_parses_memory_usage_format(self):
        line = "NPU ID                         : 0\nMemory-Usage(MB)               : 18432 / 32768"
        matches = _MEM_LINE.findall(line)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0], ("0", "18432", "32768"))

    def test_hbm_preferred_over_memory(self):
        """On 910B3 both columns exist; HBM should win."""
        out = "NPU ID: 0\nMemory-Usage(MB) = 0 / 0\nHBM-Usage(MB) = 3381 / 65536"
        info = _parse_npu_smi_memory(out)
        self.assertIn(0, info)
        self.assertEqual(info[0]["total"], 65536)
        self.assertEqual(info[0]["used"], 3381)
        self.assertEqual(info[0]["free"], 65536 - 3381)

    def test_falls_back_to_memory_when_no_hbm(self):
        out = "NPU ID: 0\nMemory-Usage(MB) = 5000 / 32000"
        info = _parse_npu_smi_memory(out)
        self.assertIn(0, info)
        self.assertEqual(info[0]["total"], 32000)
        self.assertEqual(info[0]["used"], 5000)


if __name__ == "__main__":
    unittest.main()
