from __future__ import annotations

from typing import Any, Dict, List

from Sys.RootCauseAnalyze.skills.temporal_ranker import SKILL_META as TEMPORAL_META
from Sys.RootCauseAnalyze.skills.temporal_ranker import score_temporal
from Sys.RootCauseAnalyze.skills.topo_ranker import SKILL_META as TOPO_META
from Sys.RootCauseAnalyze.skills.topo_ranker import score_topo
from Sys.utils.case_utils import load_case_info, load_case_nodes


class BuiltinSkillProvider:
    """Small compatibility provider for the built-in deterministic skills."""

    def __init__(self) -> None:
        self.skill_map = {
            "topology_pagerank_rank": score_topo,
            "temporal_score_devices": score_temporal,
        }
        self.skill_configs = [dict(TOPO_META), dict(TEMPORAL_META)]

    def get_skill_conf(self) -> List[Dict[str, Any]]:
        return [dict(skill) for skill in self.skill_configs]

    def get_node_list(self, dirpath: str) -> List[Dict[str, Any]]:
        return load_case_nodes(dirpath)

    def get_alarminfo(self, dirpath: str) -> Dict[str, Any]:
        return load_case_info(dirpath)
