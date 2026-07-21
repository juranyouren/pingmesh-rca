"""Backward-compatible evidence builder import.

New code should import `Sys_v1.RootCauseAnalyze.gate.evidence.build_fused_evidence`.
"""

from Sys_v1.RootCauseAnalyze.gate.evidence import build_fused_evidence

__all__ = ["build_fused_evidence"]
