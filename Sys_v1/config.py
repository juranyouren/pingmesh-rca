from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AblationSpec:
    """Executable definition of one simple ablation.

    ``candidate_scope`` determines which devices enter the decision stage:

    - ``topology_top_k``: M1 focuses the device set.
    - ``all_devices``: M1 is absent; M2 processes every device.
    """

    name: str
    description: str
    enable_m1: bool
    enable_m2: bool
    enable_m3: bool
    use_topology_score: bool
    use_temporal_score: bool
    candidate_scope: str
    enable_gate: bool


ABLATION_SPECS = {
    "m1": AblationSpec(
        name="m1",
        description="M1 topology ranking is used directly as the final ranking.",
        enable_m1=True,
        enable_m2=False,
        enable_m3=False,
        use_topology_score=True,
        use_temporal_score=False,
        candidate_scope="topology_top_k",
        enable_gate=False,
    ),
    "m1_m3": AblationSpec(
        name="m1_m3",
        description="M1 topology ranking followed by M3 confidence routing and optional LLM review.",
        enable_m1=True,
        enable_m2=False,
        enable_m3=True,
        use_topology_score=True,
        use_temporal_score=False,
        candidate_scope="topology_top_k",
        enable_gate=True,
    ),
    "m2_m3": AblationSpec(
        name="m2_m3",
        description="M2 scans all devices without topology ranking; M3 uses temporal scoring and optional LLM review.",
        enable_m1=False,
        enable_m2=True,
        enable_m3=True,
        use_topology_score=False,
        use_temporal_score=True,
        candidate_scope="all_devices",
        enable_gate=True,
    ),
    "m123": AblationSpec(
        name="m123",
        description="Full M1 + M2 + M3 system with equal-weight topology/temporal fusion.",
        enable_m1=True,
        enable_m2=True,
        enable_m3=True,
        use_topology_score=True,
        use_temporal_score=True,
        candidate_scope="topology_top_k",
        enable_gate=True,
    ),
}


def get_ablation_spec(name: str) -> AblationSpec:
    try:
        return ABLATION_SPECS[name]
    except KeyError as exc:
        choices = ", ".join(ABLATION_SPECS)
        raise ValueError(f"Unknown ablation {name!r}; choose one of: {choices}") from exc
