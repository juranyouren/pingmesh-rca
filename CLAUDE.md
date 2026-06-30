# CLAUDE.md

## 项目定位
面向大规模数据中心网络的根因定位（RCA）系统。方案：**Pingmesh 触发 → Skill Pipeline（topo+temporal 并行评分融合）→ 证据融合层 → LLM 重排审核**，基于华为云 159 例人工标注故障案例验证。

## 关键约束
- **纯内网环境**：无法调用外部 LLM API，所有模型必须本地部署
- **数据合规**：华为云内部故障数据，无法公开发布
- **硬件**：华为鲲鹏 920 (256 核) + 2TB 内存 + 8× Ascend 910B3 NPU（64GB HBM/卡）

## 分支策略

| 分支 | 用途 |
|------|------|
| `main` | 主分支 — 公司数据集 (nodes_labeled / nodes / nodes_extend) 上的方法改进 |
| `nika` | NIKA 公开数据集适配 — 可公开发表的结果 |

NIKA 分支初始代码与 main 一致，后续各自独立演进。

## 仓库结构

| 目录/文件 | 用途 |
|-----------|------|
| `Sys/config.py` | 集中配置：路径、模型、NPU、PageRank、时序、Skill 选择 |
| `Sys/Preprocess/Preprocessor.py` | **数据预处理**：RAW 合并 → 校验 → 提取 NODE 数据 |
| `Sys/RootCauseAnalyze/SkilledAnalyzer.py` | Skill 触发 + LLM 重排审核的 RCA 分析器 |
| `Sys/RootCauseAnalyze/evidence_fusion.py` | 证据融合层：两个 Skill 输出 → 候选设备综合证据表 + Top-K 详情 |
| `Sys/RootCauseAnalyze/skill_pipeline.py` | 纯算法流水线：Skill 组合评分融合（不依赖 LLM/NPU），端到端评测 |
| `Sys/RootCauseAnalyze/llm_alarm_scorer.py` | LLM 告警打分：对缺失告警去重后用 LLM 语义打分 1-100，补全权重表 |
| `Sys/Score/Score_N.py` | 评分模块（Top-1~5），skill/llm 分层评测 |
| `Sys/Score/failure_analyzer.py` | 失败案例 node 数据诊断 |
| `Sys/AlarmWeightBuilder.py` | 全局告警权重构建器：`build()` / `learn_from_labels()` |
| `SkillBank/SkillExecutor.py` | 动态 Python Skill 插件系统 |
| `SkillBank/skills/topo.py` | **Skill 1** — 有向 PageRank + Top-K 数据提取 |
| `SkillBank/skills/temporal_score.py` | **Skill 2** — 时序 Burst/EarlyBird/Density |
| `scripts/` | Bash 推理/消融脚本 |
| `tmp/` | 服务器端诊断/预处理/标注辅助脚本 |
| `Baseline/` | 基线方法：TraceRCA、NetEventCause、BiAn |
| `data/` | 标注数据（nodes_labeled, pingmesh_labeled） |
| `docs/` | 汇报、方案介绍、绘图提示词、开发教训 |

## 技术栈
- **LLM 推理**: DeepSeek-R1-Distill-Qwen-32B (vLLM 0.7.3 + Ascend 910B3 NPU)
- **核心依赖**: PyTorch 2.5.1, LangChain 0.3.12, NumPy, pandas, networkx

## 实验结果总览

### 最佳结果 (159 例人工标注, 2026-06 最新)

| 组合 | Top-1 | Top-3 | Top-5 |
|------|-------|-------|-------|
| **[1,2] topo+temporal (manual权重)** | **76.10%** | 85.53% | 91.19% |
| [1,2] topo+temporal (llm权重) | 66.67% | 88.05% | 93.71% |
| [2] temporal only (manual) | 62.89% | 88.05% | 94.34% |
| [1] topo only (manual) | 50.31% | 74.21% | 84.28% |

**LLM 后置推理** (基于 [1,2] manual 权重 + evidence_fusion):
| 评测层 | Top-1 | Top-3 | Top-5 |
|--------|-------|-------|-------|
| skill_evaluation (纯算法) | 76.10% | 84.91% | 91.19% |
| llm_evaluation (LLM 重排) | 75.47% | 86.79% | 86.79% |

LLM 基本未做变更——综合分差距足够大时 LLM 信任算法排名，这与 prompt 设计一致。

### 历史对比

| 数据 | 案例数 | 标注 | Top-1 (topo+temp) | 关键发现 |
|------|--------|------|-------------------|---------|
| 毕设 (v1.0) | 104 | 非人工 | 60.00% | 旧标注不可靠 |
| nodes_labeled (脱敏) | 146 | 人工 | 56.64% | 告警稀疏, 136/146 case 告警 ≤5 |
| **nodes_extend (当前)** | **159** | **人工** | **76.10%** | **完整告警数据** |

### 消融结论
- Topo 单独: 50.31% (比脱敏数据 38-43% 高 7-12pp → 告警恢复后 PR 生效)
- Temporal 单独: 62.89% (时序有效, 仍是最强单信号)
- **Topo + Temporal: 76.10% (+13pp over temporal alone)** — 协同证据确凿
- LLM 重排: 75.47% (LLM 不应主动改排名, 仅在信号接近时裁决)

## 当前方案（v2.0）

```
Pingmesh 告警 → ┬─ Skill 1: 有向 PageRank ─┐
                └─ Skill 2: 时序嫌疑度    ─┤
                                           ↓
                                    归一化等权融合
                                           ↓
                                    证据融合层（紧凑表）
                                           ↓
                                    LLM 重排审核
                                           ↓
                                      最终根因 IP
```

### Skill 1：有向 PageRank
Personalization 向量由告警权重 + cross 交汇度 + source/sink 邻近度初始化。
在 Spine-Leaf 拓扑中使用有向图（linked_from/linked_to 作为方向，但需注意这是层次标签而非因果方向）。

### Skill 2：时序嫌疑度
| 特征 | 公式 | 权重 |
|------|------|------|
| Burst Score | `count(abs(t - ref_time) ≤ 5min) / total` | 0.40 |
| Early Bird | `1 / rank(first_alarm_among_all_devices)` | 0.35 |
| Temporal Density | `alarm_count / active_span_min` (cap 20/min) | 0.25 |

是当前最强单信号。参考时间 fallback：`ref_time_ms` → `info["alarm_time"]` → `*_info.json`。

### 证据融合层
直接调用 skill_pipeline 的评分函数（与消融实验一致），输出三段紧凑文本，压缩比 75-93%。

### LLM 角色
"重排审核专家" — 算法已按综合分排好，LLM 在信号接近时用告警语义裁决。

LLM 对全量告警做 causal/symptom/noise 三分类。temporal 单独 +1.9pp，但融合退步 −6.6pp
（分类加权只覆盖命中权重表的告警，未覆盖裸告警名 → PR 均匀分布淹没 temporal）。
下一步需扩展覆盖范围。

## 配置管理

**方案 A（当前）**：环境变量 + `scripts/common.sh` 作为单一来源。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PINGMESH_PROJECT_ROOT` | `/home/sbp/lixinyang/pingmesh` | 项目根目录 |
| `PINGMESH_DATA` | `.../data/node/nodes_labeled` | node 数据目录 |
| `PINGMESH_RESULTS` | `.../data/res` | 结果目录 |
| `PINGMESH_WEIGHTS_MANUAL` | `.../all_alarms.json` | 人工权重 |
| `PINGMESH_WEIGHTS_LLM` | `.../alarm_weights.json` | LLM 学习权重 |
| `PINGMESH_SKILLS` | `1 2` | 默认 Skill |
| `PINGMESH_TOP_K` | `5` | 候选数 |

## 推理脚本

| 脚本 | 依赖 | 用途 |
|------|------|------|
| `run_inference.sh` | NPU | 单次推理 + 评分 |
| `run_full_ablation.sh` | 无 | 6 组纯算法消融 |
| `run_llm_alarm_scoring.sh` | NPU | LLM 告警去重打分 |

## 待办（按优先级）

### P0: 结构化 Prompt（✅ 已完成）
### P0: 告警信息规范化（1.3）
### P1: 小模型前置打分（2.1-2.4）
### P2: 其他 — 调 K / NIKA / LoRA SFT

## 注意事项
- co_occur Skill 已弃用删除
- 有向 PageRank：Spine-Leaf 拓扑中 linked_from/to 是层次标签，不编码因果方向，论文应诚实呈现
- 告警字段约定（全仓库统一）：`alarm_name > name > 空字符串`
- historical 数据泄漏已修复（`temporal_score.py` 不再读 `label.json`）
