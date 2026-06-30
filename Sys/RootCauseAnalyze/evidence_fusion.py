"""Backward-compatible evidence builder import.

New code should import `Sys.RootCauseAnalyze.gate.evidence.build_fused_evidence`.
"""

from Sys.RootCauseAnalyze.gate.evidence import build_fused_evidence

__all__ = ["build_fused_evidence"]
