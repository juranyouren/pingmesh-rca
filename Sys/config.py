"""
Central configuration for pingmesh RCA system.
ALL values read from environment variables (set by scripts/common.sh).
Edit common.sh to change defaults; export to override per-session.

Usage:
    from Sys.config import config
    model = LLM(model=config.model.model_path, ...)
    data_root = config.data.nodes_labeled
"""

import os

# ══════════════════════════════════════════════════════════════════
# Base paths (all from env)
# ══════════════════════════════════════════════════════════════════

_ROOT = os.environ.get("PINGMESH_PROJECT_ROOT", "/home/sbp/lixinyang/pingmesh")


class DataPaths:
    def __init__(self, root=_ROOT):
        self.pingmesh_raw = os.path.join(root, "data", "raw", "pingmesh_v1")
        self.nodes_labeled = os.environ.get("PINGMESH_DATA", os.path.join(root, "data", "node", "nodes_max_labeled"))
        self.results       = os.environ.get("PINGMESH_RESULTS", os.path.join(root, "data", "res"))
        self.alarm_weights = os.environ.get("PINGMESH_WEIGHTS_MANUAL", os.path.join(root, "data", "weights", "classified_alarms", "all_alarms.json"))


class SkillPaths:
    def __init__(self, root=_ROOT):
        self.skills_folder = os.path.join(root, "Sys", "RootCauseAnalyze", "skills")
        self.skills_json   = os.path.join(root, "Sys", "RootCauseAnalyze", "skills", "builtin_skills.json")
        self.checklist     = os.path.join(root, "Sys", "RootCauseAnalyze", "gate", "check_list.json")


# ══════════════════════════════════════════════════════════════════
# Model (all from env)
# ══════════════════════════════════════════════════════════════════

class ModelConfig:
    def __init__(self):
        self.model_path   = os.environ.get("PINGMESH_MODEL_PATH", "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B")
        self.npu_cards    = os.environ.get("PINGMESH_NPU_CARDS", "0,1,2,3,4,5,6,7")
        self.npu_groups   = [[0, 1], [2, 3], [4, 5], [6, 7]]
        self.gpu_memory_utilization = 0.85
        self.max_model_len   = int(os.environ.get("PINGMESH_MAX_MODEL_LEN", "16384"))
        self.trust_remote_code = True
        self.temperature      = float(os.environ.get("PINGMESH_TEMPERATURE", "0.6"))
        self.max_tokens       = int(os.environ.get("PINGMESH_MAX_TOKENS", "4096"))
        self.repetition_penalty = 1.05
        self.top_p            = 0.95
        self.batch_size       = int(os.environ.get("PINGMESH_BATCH_SIZE", "8"))
        self.safe_truncate_tokens = 2000


# ══════════════════════════════════════════════════════════════════
# Algorithm parameters
# ══════════════════════════════════════════════════════════════════

class PageRankConfig:
    def __init__(self):
        self.alpha = 0.85
        self.default_personalization = 0.1
        self.fallback_weights = {"stachg_todwn": 100, "trunkdown": 100, "vlan接口down(dcn)": 100}
        self.endpoint_bonus = 0.5
        self.cross_multiplier = 0.5
        self.log_only_score = 0.5
        self.alarm_no_weight_score = 2.0
        self.directed = True


class TemporalConfig:
    def __init__(self):
        self.window_ms = 300000
        self.density_cap = 20.0
        self.weight_burst = 0.40
        self.weight_early = 0.35
        self.weight_density = 0.25
        self.top_k = int(os.environ.get("PINGMESH_TOP_K", "10"))


class SkillConfig:
    def __init__(self):
        env_skills = os.environ.get("PINGMESH_SKILLS", "")
        self.skill_ids = [int(x) for x in env_skills.split()] if env_skills else [1, 2]
        self.short_mode = 0


# ══════════════════════════════════════════════════════════════════
# Unified config object
# ══════════════════════════════════════════════════════════════════

class Config:
    def __init__(self):
        self.data = DataPaths()
        self.skills = SkillPaths()
        self.model = ModelConfig()
        self.pagerank = PageRankConfig()
        self.temporal = TemporalConfig()
        self.skill = SkillConfig()

config = Config()
