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
- 全链路文件（376 节点）→ 所有数据路径统一读取

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

## 消融结果（146 例人工标注）

| 组合 | Top-1 | 发现 |
|------|-------|------|
| `[1,2]` topo+temporal (llm权重) | **87.41%** | 纯算法天花板 |
| `[2]` temporal only | 76.22% | 时序是最强单信号 |
| `[1]` topo only | 14-17% | PageRank 单独很弱 |

核心结论：时序提供主信号（76%），topo 补上 ~13 个 case（→87%，+11pp）。

## 推理脚本

| 脚本 | 依赖 | 用途 |
|------|------|------|
| `run_inference.sh` | NPU | 单次推理 + 评分（默认 skills=[1,2] k=5） |
| `run_full_ablation.sh` | 无 | 6 组纯算法消融 (3 组合 × 2 权重来源) |

## 注意事项
- co_occur Skill 已弃用删除
- 有向 PageRank：Spine-Leaf 拓扑中 linked_from/to 是层次标签，不编码因果方向，论文应诚实呈现
- 告警字段约定（全仓库统一）：`alarm_name > name > 空字符串`
