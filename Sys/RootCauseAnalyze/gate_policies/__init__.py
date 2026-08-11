"""Active configurable gate policy API.

The historical fixed policies live under ``archive/experiments/gate_policy_v1``.
``baseline.py`` remains only so the explicit ``legacy_v1`` ablation can be
reproduced; it is never included in automatic policy selection.
"""

from .configurable import (
    DEFAULT_POLICY_CONFIG,
    NAMED_POLICY_CONFIGS,
    grid_policy_configs,
    load_policy_config,
    named_policy_configs,
    normalize_policy_config,
    resolve_policy_config,
    route_with_policy,
)

__all__ = [
    "DEFAULT_POLICY_CONFIG",
    "NAMED_POLICY_CONFIGS",
    "grid_policy_configs",
    "load_policy_config",
    "named_policy_configs",
    "normalize_policy_config",
    "resolve_policy_config",
    "route_with_policy",
]
