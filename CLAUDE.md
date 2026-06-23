# CLAUDE.md

## 项目定位
面向大规模数据中心网络的根因定位（RCA）系统。方案：**Pingmesh 触发 → Skill Pipeline（topo+temporal 并行评分融合）→ 证据融合层 → LLM 重排审核**，基于华为云 146 例人工标注故障案例验证。

## 关键约束
- **纯内网环境**：无法调用外部 LLM API，所有模型必须本地部署
- **数据合规**：华为云内部故障数据，无法公开发布
- **硬件**：华为鲲鹏 920 (256 核) + 2TB 内存 + 8× Ascend 910B3 NPU（64GB HBM/卡）

## 仓库结构

| 目录/文件 | 用途 |
|-----------|------|
| `Sys/config.py` | 集中配置：路径、模型、NPU、PageRank、时序、Skill 选择 |
| `Sys/Collect/Collector.py` | 数据采集：解析原始故障 JSON，提取拓扑节点、告警、日志、路径交汇度 |
| `Sys/Modify/Modifier.py` | 拓扑剪枝（基于交汇度 + 告警权重的 Jaccard 评分与 PageRank） |
| `Sys/RootCauseAnalyze/SkilledAnalyzer.py` | Skill 触发 + LLM 重排审核的 RCA 分析器 |
| `Sys/RootCauseAnalyze/evidence_fusion.py` | 证据融合层：两个 Skill 输出 → 候选设备综合证据表 + Top-K 详情 |
| `Sys/RootCauseAnalyze/skill_pipeline.py` | 纯算法流水线：Skill 组合评分融合（不依赖 LLM/NPU），端到端评测 |
| `Sys/RootCauseAnalyze/llm_alarm_scorer.py` | LLM 告警打分：对缺失告警去重后用 LLM 语义打分 1-100，补全权重表 |
| `Sys/Score/Score_N.py` | 评分模块（Top-1~5），skill/llm/refined 分层评测 |
| `Sys/AlarmWeightBuilder.py` | 全局告警权重构建器：`build()` / `learn_from_labels()` |
| `SkillBank/SkillExecutor.py` | 动态 Python Skill 插件系统：LLM 反思 → 自动生成插件 → 热加载 |
| `SkillBank/skills/topo.py` | **Skill 1** — 有向 PageRank + Top-K 数据提取 |
| `SkillBank/skills/temporal_score.py` | **Skill 2** — 时序 Burst/EarlyBird/Density |
| `graph_only.py` | 纯 PageRank 消融实验（内部委托给 skill_pipeline） |
| `scripts/` | Bash 推理/消融脚本 |
| `Baseline/` | 基线方法：TraceRCA、NetEventCause、BiAn |
| `data/` | 标注数据（nodes_labeled, pingmesh_labeled） |
| `docs/progress_report.md` | 进展汇报 |

## 技术栈
- **LLM 推理**: DeepSeek-R1-Distill-Qwen-32B (vLLM 0.7.3 + Ascend 910B3 NPU)
- **核心依赖**: PyTorch 2.5.1, LangChain 0.3.12, NumPy, pandas, networkx

## 实验数据

- 146 例人工标注（华为云生产环境 Pingmesh 拨测 + 拓扑 + label.json）
- 全链路文件 → 所有数据路径统一读取

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

## 消融结果（146 例人工标注，2026-06-17 修正后）

**重要**：此前 87.41% / 76.22% 因 temporal_score 从 label.json 泄漏标注数据而虚高。修正后：

| 组合 | Top-1 | Top-3 | Top-5 |
|------|-------|-------|-------|
| `[1,2]` topo+temporal (llm权重) | **56.64%** | 59.44% | 62.24% |
| `[1,2]` topo+temporal (manual权重) | 54.55% | 58.74% | 64.34% |
| `[2]` temporal only | 49.65% | 57-58% | 58-61% |
| `[1]` topo only (manual权重) | 42.66% | 53.85% | 57.34% |
| `[1]` topo only (llm权重) | 38.46% | 52.45% | 60.14% |

核心结论：topo+temporal 互补（+7pp over temporal alone），两个信号都有效且非泄漏。

## 配置管理

**方案 A（当前）**：环境变量 + `scripts/common.sh` 作为单一来源。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PINGMESH_PROJECT_ROOT` | `/home/sbp/lixinyang/pingmesh` | 项目根目录 |
| `PINGMESH_DATA` | `.../data/nodes_labeled` | 数据目录 |
| `PINGMESH_RESULTS` | `.../data/res` | 结果目录 |
| `PINGMESH_WEIGHTS_MANUAL` | `.../all_alarms.json` | 人工权重 |
| `PINGMESH_WEIGHTS_LLM` | `.../alarm_weights.json` | LLM 学习权重 |
| `PINGMESH_SKILLS` | `1 2` | 默认 Skill |
| `PINGMESH_TOP_K` | `5` | 候选数 |

- Bash 脚本：`source scripts/common.sh`，CLI 参数 `$2:-${PINGMESH_SKILLS}` 可覆盖
- Python：`config.py` 用 `os.environ.get(key, default)` 读取
- 切换数据集：`export PINGMESH_DATA=/new/path` 或 `PINGMESH_DATA=/new/path ./scripts/run_inference.sh`

## 推理脚本

| 脚本 | 依赖 | 用途 |
|------|------|------|
| `run_inference.sh` | NPU | 单次推理 + 评分 |
| `run_full_ablation.sh` | 无 | 6 组纯算法消融 |
| `run_llm_alarm_scoring.sh` | NPU | LLM 告警去重打分 |

## 关键发现：136/146 的 case 有告警的设备 ≤5

当前 `nodes_labeled` 数据严重脱敏，80% case 告警全空。即使非空的 case，有告警的设备也只有 1-5 台。导致 temporal 有效候选池极小，Top-3 与 Top-5 几乎等于 Top-1。

**方向 1**：切换到 `data/nodes`（告警信息更完整的数据集）
**方向 2**：探索无告警场景下的根因诊断（纯拓扑信号 + 其他特征）

## 待办（按优先级）

### P0: 结构化 Prompt（✅ 已完成）
`evidence_fusion.py` 输出从文本表改为 JSON 字典，topo/temporal/combined 三个独立信息块 + devices 详情。LLM 更容易解析。

### P0: 告警信息规范化（1.3）
**1.3.1 自动化提取重要告警** — 对 Top-K 候选设备，根据告警权重表和严重程度，自动滤出高优告警名称（当前 `high_severity_alarms` 字段已部分实现，需验证权重覆盖率）。

**1.3.2 小模型摘要（1.5B）** — 用小型 LLM 对 Top-K 内每个设备单独做摘要，替换当前的原始告警名列表。摘要内容包括：告警类型、时间模式、可能的故障指向。减小输入长度 + 消除冗余告警名。

### P1: 小模型前置打分（2.1-2.4）
**2.1 告警语义打分** — 对一个 case，收集全部告警名（去重），小模型根据网络运维严重程度打 0-100 分，写入 personalization 向量。

**2.2 设备级打分** — 小模型直接对每个设备打分，分数作为 PageRank 初始得分（替代告警权重表间接初始化）。

**2.3 设备摘要 + 大模型打分** — 小模型对每设备做摘要 → 汇总后给大模型做最终打分。

**2.4 并行化** — 小模型可并行部署，多 case 或多设备同时推理。

### P2: 其他
- 调 K（3/5/10）找 LLM 重排的最佳候选数
- NIKA 公开数据集集成
- LoRA SFT 微调（可选，内网可行）

## 注意事项
- co_occur Skill 已弃用删除
- 有向 PageRank：Spine-Leaf 拓扑中 linked_from/to 是层次标签，不编码因果方向，论文应诚实呈现
- 告警字段约定（全仓库统一）：`alarm_name > name > 空字符串`
