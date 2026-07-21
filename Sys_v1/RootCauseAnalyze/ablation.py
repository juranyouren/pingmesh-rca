from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class AblationSpec:
    name: str
    skill_ids: Tuple[int, ...]
    candidate_strategy: str
    enable_m2: bool
    enable_m3: bool
    enable_gate: bool
    enable_llm: bool


ABLATION_SPECS = {
    "m1": AblationSpec(
        name="m1",
        skill_ids=(1,),
        candidate_strategy="topology_top_k",
        enable_m2=False,
        enable_m3=False,
        enable_gate=False,
        enable_llm=False,
    ),
    "m1_m3": AblationSpec(
        name="m1_m3",
        skill_ids=(1,),
        candidate_strategy="topology_top_k",
        enable_m2=False,
        enable_m3=True,
        enable_gate=True,
        enable_llm=True,
    ),
    "m2_m3": AblationSpec(
        name="m2_m3",
        skill_ids=(2,),
        candidate_strategy="all_devices",
        enable_m2=True,
        enable_m3=True,
        enable_gate=True,
        enable_llm=True,
    ),
    "m123": AblationSpec(
        name="m123",
        skill_ids=(1, 2),
        candidate_strategy="topology_top_k",
        enable_m2=True,
        enable_m3=True,
        enable_gate=True,
        enable_llm=True,
    ),
}


def get_ablation_spec(name: str) -> AblationSpec:
    try:
        return ABLATION_SPECS[name]
    except KeyError as exc:
        choices = ", ".join(ABLATION_SPECS)
        raise ValueError(f"Unknown ablation {name!r}; choose one of: {choices}") from exc
