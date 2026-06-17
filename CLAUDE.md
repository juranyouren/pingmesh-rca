# CLAUDE.md

## 项目定位
面向大规模数据中心网络的拓扑关联事件根因定位（RCA）系统。论文方案：**Pingmesh 触发 → 个性化 PageRank 拓扑剪枝 → LLM 语义推理复核**，基于华为云 146 例真实故障案例验证。

## 关键约束
- **纯内网环境**：无法调用任何外部 LLM API（GPT-4 / Claude / Gemini 等不可用），所有模型必须本地部署
- **数据合规**：华为云内部故障数据，无法公开发布
- **硬件**：华为鲲鹏 920 (256 核) + 2TB 内存 + 8× Ascend 910B3 NPU（64GB HBM/卡）

## 仓库结构

| 目录/文件 | 用途 |
|-----------|------|
| `Sys/config.py` | 集中配置：路径、模型、NPU、PageRank、时序、Skill 选择 |
| `Sys/Collect/Collector.py` | 数据采集：解析原始故障 JSON，提取拓扑节点、告警、日志、路径交汇度 |
| `Sys/Modify/Modifier.py` | 拓扑剪枝：基于交汇度 + 告警权重的 Jaccard 评分与 PageRank（method 0~4） |
| `Sys/RootCauseAnalyze/SkilledAnalyzer.py` | Skill 触发的 LLM RCA 分析器 |
| `Sys/RootCauseAnalyze/SkillNRefineAnalyzer.py` | Skill + Refine 双阶段分析器 |
| `Sys/RootCauseAnalyze/evidence_fusion.py` | 证据融合层：三个 Skill 输出 → 候选设备综合证据表 + Top-K 详情 |
| `Sys/RootCauseAnalyze/skill_pipeline.py` | 纯算法流水线：任意 Skill 组合评分融合（不依赖 LLM/NPU），端到端评测 |
| `Sys/RootCauseAnalyze/llm_alarm_scorer.py` | LLM 告警打分：对缺失告警去重后用 LLM 语义打分 1-100，补全权重表 |
| `Sys/Score/Score_N.py` | 评分模块（Top-1~5），支持 skill/llm/refined 分层评测 |
| `Sys/AlarmWeightBuilder.py` | 全局告警权重构建器：`build()` 初始化 / `learn_from_labels()` 基于 P(root\|alarm) 学习 |
| `SkillBank/SkillExecutor.py` | 动态 Python Skill 插件系统：LLM 反思 → 自动生成插件 → 热加载 |
| `SkillBank/skills/topo.py` | **Skill 1** — `topology_pagerank_rank`：无向/有向 PageRank + Top-K 数据提取 |
| `SkillBank/skills/co_occur.py` | **Skill 2** — `co_occurrence_alarm_check`：告警权重 + 共现规则匹配 |
| `SkillBank/skills/temporal_score.py` | **Skill 3** — `temporal_score_devices`：Burst + Early Bird + Density |
| `Sys/CaseReviewer/CaseReviewer.py` | LLM 推理引擎，含三阶段 Co-occurrence 规则挖掘闭环 |
| `graph_only.py` | 消融实验：无向/有向 PageRank（内部委托给 skill_pipeline） |
| `scripts/` | Bash 推理/消融脚本 |
| `Baseline/` | 基线方法：TraceRCA、NetEventCause、BiAn（待补 FP-Growth / DBSCAN） |
| `data/` | 标注数据（nodes_labeled, pingmesh_labeled） |
| `docs/progress_report.md` | 进展汇报（论文演进、消融结果、方案详解） |

## 技术栈
- **LLM 推理**: DeepSeek-R1-Distill-Qwen-32B (vLLM 0.7.3 + Ascend 910B3 NPU)
- **核心依赖**: PyTorch 2.5.1, LangChain 0.3.12, NumPy, pandas, networkx
- **本地可部署 LLM**: DeepSeek-Distill 系列、Qwen2.5 系列

## 实验数据与结果

### 数据
- **毕设阶段**：104 例非人工标注（已弃用）
- **当前阶段**：146 例人工标注（生产环境 Pingmesh 拨测 + 拓扑 + label.json）

### 毕设最终态（104 例旧数据，仅作参考）

| 场景 | Top-1 | Top-3 | 单 case 耗时 |
|------|-------|-------|--------------|
| 常规场景 | 60.00% | 92.22% | 9.99s |
| 告警风暴 | 35.71% | 78.57% | 9.99s |

### 当前最优结果（146 例人工标注）

详见 `docs/progress_report.md`。纯算法天花板：**Skill [1,3] topo+temporal，87.41% Top-1**（待 LLM 重排结果）。

## 数据管道

### 文件读取约定（当前版本）

| 模块 | 节点数据来源 |
|------|-------------|
| LLM Analyzers（`generate_prompts`） | `*pingmesh*全链路.json`（全量节点） |
| Skill Pipeline / graph_only | `*pingmesh*全链路.json`（全量节点） |
| Skill Executor（`get_node_list`） | `*pingmesh*全链路.json`（全量节点） |
| AlarmWeightBuilder | `*pingmesh*全链路.json` 或 `nodes.json` |
| Scorer | 读 `res.json` 的 `dir` 字段 + `label.json` |

> 毕设阶段 LLM 路径读的是 Modifier 剪枝后的 `nodes.json`（K=10），根因 IP 经常被剪掉（82/104）。**已修复**：所有路径统一读全链路文件。

### 告警字段约定（全仓库统一）
```python
name = event if isinstance(event, str) else event.get("alarm_name", event.get("name", ""))
# alarm_name > name > 空字符串
```

## 已实现模块

### SkillBank：三个 Skill

| ID | 文件 | Executor | 用途 |
|----|------|----------|------|
| 1 | `topo.py` | `topology_pagerank_rank` | 无向/有向 PageRank + Top-K 数据提取 |
| 2 | `co_occur.py` | `co_occurrence_alarm_check` | 告警权重 + 共现规则匹配 |
| 3 | `temporal_score.py` | `temporal_score_devices` | 时序 Burst/EarlyBird/Density |

（清理历史：删除 `weight_cal.py` 和 `topo_nodes.py`，5 个 → 3 个）

### Skill 1：PageRank

无向/有向 PageRank，personalization 向量由告警权重 + cross 交汇度 + source/sink 邻近度初始化。有向版本反转 linked_from/linked_to 方向（将层次标签视为有向边），**但 Spine-Leaf 物理层双向对等，dir/undir 差异不显著**（87.41% vs 83.22%，可能为随机波动）。

### Skill 2：告警共现规则

从历史错案中挖掘告警组合规则，作为专家指令注入。在纯算法消融中贡献微弱（单独 Top-1 ≈ 1-8%），等权融合中每个加它的组合都掉分。

### Skill 3：时序嫌疑度

| 特征 | 公式 | 权重 |
|------|------|------|
| Burst Score | `count(abs(t - ref_time) ≤ 5min) / total` | 0.40 |
| Early Bird | `1 / rank(first_alarm_among_all_devices)` | 0.35 |
| Temporal Density | `alarm_count / active_span_min` (cap 20/min) | 0.25 |

**是最强单信号**（76.22% 单独 Top-1）。参考时间 fallback：`ref_time_ms` → `info["alarm_time"]` → `*_info.json`。时间戳 fallback：node alarms/logs → label.json。

### 证据融合层（`evidence_fusion.py`）

在 Skill 输出与 LLM 输入之间压缩。直接调用 `skill_pipeline` 的评分函数（与消融实验一致），输出三段：
- 证据表（综合分排名 + 各维度原始分 + 关键告警）
- Info 概况（只取关键字段）
- 候选设备详情（告警名去重 + 拓扑连接）

压缩效果：常规 −75%，风暴 −93%，大小与告警量解耦。

### Skill Pipeline（`skill_pipeline.py`）

不依赖 LLM/NPU，任意 Skill 组合归一化等权平均，输出 `res.json` 可直接评测。

### LLM 前置告警打分（`llm_alarm_scorer.py`）

扫描全数据集去重 → LLM 按网络运维严重程度打出 1-100 分 → 补全权重表。

### 集中配置（`config.py`）

`DataPaths` / `SkillPaths` / `ModelConfig` / `PageRankConfig` / `TemporalConfig` / `SkillConfig` 六组配置。已迁移：`SkilledAnalyzer.py`, `Score_N.py`。

### 推理脚本

| 脚本 | 依赖 | 用途 |
|------|------|------|
| `run_inference.sh` | NPU | 单次推理 + 评分（默认 skills=[1,3] k=5） |
| `run_full_ablation.sh` | 无 | 22 组纯算法消融 (11 Skill × 2 权重) |
| `run_llm_alarm_scoring.sh` | NPU | LLM 告警去重打分 → 新权重 → 评测 |

## 消融结论（146 例人工标注）

| 组合 | Top-1 | 发现 |
|------|-------|------|
| `[1,3]` topo+temporal | **87.41%** | 纯算法天花板 |
| `[3]` temporal only | 76.22% | 时序是最强单信号 |
| `[1]` topo only | 14-17% | 人工标注上 PageRank 单独很弱 |
| `[2]` co_occur only | 1-8% | 告警权重单独几乎无用 |

核心结论：时序 + 拓扑协同（temporal 提供主信号，topo 补上 ~13 个 case → +11pp），co_occur 等权融合拖后腿。

## 当前方案（v2.0）vs 毕设方案（v1.0）

| 维度 | v1.0 | v2.0 |
|------|------|------|
| 数据 | 104 例非人工标注 | 146 例人工标注 |
| 拓扑 | 无向 PR, 剪枝到 K=10 | 全链路 PageRank |
| 时序 | 无 | Skill 3 |
| LLM 角色 | "推理定位" | "重排审核" |
| Prompt | 三 Skill 拼接，经常截断 | 证据融合层，紧凑表 |
| 评测 | 单一指标 | skill / llm / refined 分层 |

## 注意事项

- **LLM 重排效果待确认**：87% 纯算法基线很高，LLM 能否在此基础上加分，取决于候选设备上是否有足够的告警语义信息供 LLM 判断。脱敏数据中大量设备告警为空，LLM 可能没有有效信号可操作。
- **有向 PageRank**：Spine-Leaf 拓扑中 linked_from/linked_to 是层次标签，不编码因果方向。消融中 dir/undir 差异不显著，论文应诚实呈现。
- **co_occur**：当前在等权融合中拖后腿。如需用上，需改为 LLM 驱动而非纯规则匹配。
