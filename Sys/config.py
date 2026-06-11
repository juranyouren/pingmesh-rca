"""
Central configuration for pingmesh RCA system.
Import from this module instead of hardcoding paths / parameters.

Usage:
    from Sys.config import config
    model = LLM(model=config.model_path, ...)
    data_root = config.data.nodes_labeled
"""

import os

# ══════════════════════════════════════════════════════════════════════════════
# Base paths
# ══════════════════════════════════════════════════════════════════════════════

# 项目根目录（服务器部署路径 / 本地 Windows 路径）
# 常用: "/home/sbp/lixinyang/pingmesh"
# 本地: r"D:\DESKTOP\aiops\华为DCN&数通\pingmeshPaper"
PROJECT_ROOT = "/home/sbp/lixinyang/pingmesh"


# ══════════════════════════════════════════════════════════════════════════════
# Data paths
# ══════════════════════════════════════════════════════════════════════════════

class DataPaths:
    """数据目录配置"""
    def __init__(self, root=PROJECT_ROOT):
        # 原始华为云故障 JSON（Collector 输入）
        # 常用: "data/pingmesh_labeled", "data/pingmesh_original"
        self.pingmesh_raw = os.path.join(root, "data", "pingmesh_labeled")

        # 预处理后的标注数据（Collector 输出 / 各模块输入）
        # 常用: "data/nodes_labeled", "data/nodes", "data/cnodes_silent_2"
        self.nodes_labeled = os.path.join(root, "data", "nodes_labeled")

        # 推理结果输出
        # 常用: "data/res"
        self.results = os.path.join(root, "data", "res")

        # 告警权重文件
        # 常用: "data/weights/classified_alarms/all_alarms.json"
        #       "data/weights/alarm_weights.json" (learn_from_labels 输出)
        self.alarm_weights = os.path.join(root, "data", "weights", "classified_alarms", "all_alarms.json")


# ══════════════════════════════════════════════════════════════════════════════
# SkillBank paths
# ══════════════════════════════════════════════════════════════════════════════

class SkillPaths:
    """Skill 系统文件路径"""
    def __init__(self, root=PROJECT_ROOT):
        # Skill Python 插件目录
        self.skills_folder = os.path.join(root, "SkillBank", "skills")

        # 技能元数据 JSON（供 LLM 查阅）
        # 常用: "SkillBank/skills.json"
        self.skills_json = os.path.join(root, "SkillBank", "skills.json")

        # Refine 审查清单
        # 常用: "SkillBank/check_list.json"
        self.checklist = os.path.join(root, "SkillBank", "check_list.json")

        # 告警共现经验库（历史错案反思生成）
        # 常用: "SkillBank/alarm_co_occurrence_rules.json"
        self.co_occur_rules = os.path.join(root, "SkillBank", "alarm_co_occurrence_rules.json")


# ══════════════════════════════════════════════════════════════════════════════
# Model configuration
# ══════════════════════════════════════════════════════════════════════════════

class ModelConfig:
    """
    LLM 模型与推理引擎配置。

    常用选项:
      model_path:
        - "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B"  ← 主力 32B
        - "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-14B"  ← 轻量备选
        - "/usr/share/large_language_models/Qwen2.5-32B-Instruct"          ← 消融对比

      npu_cards: "0,1" | "2,3" | "6,7" | "0,1,2,3" (4 卡)
        - 8× Ascend 910B3, 64GB HBM/card
        - 32B 模型需要 2 卡 (tensor_parallel=2)
        - 多进程部署: BiAn 用 [[2,3], [6,7]] 跑 2 实例
        - 全部可用卡: [0,1,2,3,4,5,6,7]，通常用 4 卡跑 2 实例
    """
    def __init__(self):
        # 模型路径
        self.model_path = "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B"

        # NPU 卡号（ASCEND_RT_VISIBLE_DEVICES 环境变量）
        # 常用: "0,1" (单实例) | "2,3" / "6,7" (其他卡)
        self.npu_cards = "0,1"

        # 多实例部署时每实例使用的卡号列表
        # 常用: [[0,1], [2,3]]  ← 2 实例各用 2 卡
        #       [[2,3], [6,7]]  ← BiAn baseline 实测配置
        self.npu_groups = [[0, 1], [2, 3]]

        # vLLM 引擎参数
        self.gpu_memory_utilization = 0.85       # 常用 0.85 / 0.90
        self.max_model_len = 16384               # 常用: 65536//4=16384 (32B), 32768 (BiAn)
        self.trust_remote_code = True

        # 采样参数
        self.temperature = 0.6                   # 常用: 0.3 (BiAn/精确), 0.6 (CaseReviewer/Skilled), 0.7 (发散)
        self.max_tokens = 4096                   # 常用: 2048 (Skilled), 3072 (SkillNRefine), 4096 (CaseReviewer/BiAn)
        self.repetition_penalty = 1.05           # 常用: 1.05 / 1.0
        self.top_p = 0.95                        # 常用: 0.9 / 0.95

        # 批量推理
        self.batch_size = 8                      # 常用: 1 (单条), 8 (CaseReviewer), 16 (BiAn)

        # Token 截断
        self.safe_truncate_tokens = 2000         # BiAn _safe_truncate 用


# ══════════════════════════════════════════════════════════════════════════════
# PageRank / Graph algorithm parameters
# ══════════════════════════════════════════════════════════════════════════════

class PageRankConfig:
    """图算法参数"""
    def __init__(self):
        self.alpha = 0.85                        # RWR 重启概率（常用 0.85）
        self.default_personalization = 0.1       # 未知节点的默认 personalization 值

        # 内置高优告警权重（兜底，真正权重从 all_alarms.json 加载）
        self.fallback_weights = {
            "stachg_todwn": 100,
            "trunkdown": 100,
            "vlan接口down(dcn)": 100,
        }

        # Personalization 计算
        self.endpoint_bonus = 0.5                # source/sink IP 额外加成分
        self.cross_multiplier = 0.5              # cross count 乘数系数
        self.log_only_score = 0.5                # 仅有日志无事伴的基础分
        self.alarm_no_weight_score = 2.0         # 有告警但未命中权重表时的单条底分

        # 模式
        self.directed = True                     # True=有向 PageRank, False=无向


# ══════════════════════════════════════════════════════════════════════════════
# Temporal scoring parameters
# ══════════════════════════════════════════════════════════════════════════════

class TemporalConfig:
    """时序嫌疑度评分参数"""
    def __init__(self):
        self.window_ms = 300000                  # Burst 检测窗口 (ms)，默认 5 分钟
        self.density_cap = 20.0                  # 密度上限 (alarms/min)，超过截断
        self.weight_burst = 0.40                 # Burst Score 权重
        self.weight_early = 0.35                 # Early Bird 权重
        self.weight_density = 0.25               # Temporal Density 权重
        self.top_k = 10                          # 输出 Top-K 设备


# ══════════════════════════════════════════════════════════════════════════════
# Skill selection
# ══════════════════════════════════════════════════════════════════════════════

class SkillConfig:
    """
    启用的 Skill 列表。

    当前可用:
      [1] topology_pagerank_rank     — 拓扑 PageRank + 告警权重 + Top-K 数据提取
      [2] co_occurrence_alarm_check  — 告警权重 + 共现规则匹配
      [3] temporal_score_devices     — 时序 Burst/EarlyBird/Density 评分

    常用组合:
      - [1]            ← 仅拓扑（消融实验）
      - [1, 2]         ← 拓扑 + 共现规则
      - [1, 3]         ← 拓扑 + 时序
      - [1, 2, 3]      ← 全量（推荐）
      - [3]            ← 仅时序（消融实验）
    """
    def __init__(self):
        self.skill_ids = [1, 2, 3]              # 默认启用全部 3 个 Skill
        self.short_mode = 0                     # 1=不传入原始节点数据（省 Token）


# ══════════════════════════════════════════════════════════════════════════════
# Unified config object
# ══════════════════════════════════════════════════════════════════════════════

class Config:
    """将所有配置聚合为一个对象，方便 import 后使用"""
    def __init__(self):
        self.data = DataPaths()
        self.skills = SkillPaths()
        self.model = ModelConfig()
        self.pagerank = PageRankConfig()
        self.temporal = TemporalConfig()
        self.skill = SkillConfig()

    def resolve(self, path_str: str) -> str:
        """将 {PROJECT_ROOT} 占位符替换为实际路径"""
        return path_str.replace("{PROJECT_ROOT}", PROJECT_ROOT)


# 全局单例
config = Config()
