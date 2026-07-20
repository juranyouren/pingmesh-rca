"""Sys_v1: isolated three-module Pingmesh RCA prototype.

All implementation changes for the refactored system live under this package.
The historical ``Sys`` package is imported only for stable, read-only data and
temporal-feature helpers.
"""

from .config import ABLATION_SPECS, AblationSpec, get_ablation_spec

__all__ = ["ABLATION_SPECS", "AblationSpec", "get_ablation_spec"]
