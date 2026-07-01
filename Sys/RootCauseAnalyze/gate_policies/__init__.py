"""Gate policy registry — auto-discovers route functions.

To add a new policy, drop a ``.py`` file in this directory that defines:

    POLICY_NAME: str          — short key used on the CLI (e.g. ``"my_policy"``)
    POLICY_LABEL: str | None  — human-readable label for reports (optional)

    def route(*, combined_ips, topo_ips, temporal_ips,
              topo_tree, temporal_tree) -> dict:
        ...

The function must accept the same keyword arguments as
``trust_trees.router.route_with_trust_trees`` and return a dict with keys
``decision``, ``route``, ``reason``, ``recommended_ips``, etc.
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Callable, Dict, List

RouteFn = Callable[..., Dict[str, Any]]


def _policy_module_names() -> List[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    names: List[str] = []
    for fn in sorted(os.listdir(here)):
        if fn.startswith("_") or not fn.endswith(".py"):
            continue
        mod = fn[:-3]
        if mod not in names:
            names.append(mod)
    return names


def list_policies() -> Dict[str, RouteFn]:
    """Return ``{policy_name: route_fn}`` for every policy in this directory."""
    registry: Dict[str, RouteFn] = {}
    for mod_name in _policy_module_names():
        mod = importlib.import_module(f".{mod_name}", __package__)
        name = getattr(mod, "POLICY_NAME", mod_name)
        fn = getattr(mod, "route", None)
        if callable(fn):
            registry[name] = fn
    return registry


def get_policy(name: str) -> RouteFn:
    """Look up a single policy by name (raises KeyError if not found)."""
    registry = list_policies()
    if name not in registry:
        raise KeyError(f"unknown policy {name!r}; available: {sorted(registry)}")
    return registry[name]
