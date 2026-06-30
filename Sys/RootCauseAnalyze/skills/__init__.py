"""Built-in deterministic RCA skills."""

from .fusion import rank_devices_by_skills
from .provider import BuiltinSkillProvider

__all__ = ["BuiltinSkillProvider", "rank_devices_by_skills"]
