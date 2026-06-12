# CLAUDE.md — 仓库概览

## 项目定位
面向大规模数据中心网络的拓扑关联事件根因定位（RCA）系统。论文方案：**Pingmesh 触发 → 个性化 PageRank 拓扑剪枝 → LLM 语义推理复核**，基于华为云 104 例真实故障案例验证。

## 关键约束
- **纯内网环境**：无法调用任何外部 LLM API（GPT-4 / Claude / Gemini 等不可用），所有模型必须本地部署
- **数据合规**：华为云内部 104 例故障数据，无法公开发布
- **硬件**：华为鲲鹏 920 (256 核) + 2TB 内存 + 8× Ascend 910B3 NPU（64GB HBM/卡）

## 仓库结构

| 目录/文件 | 用途 |
|-----------|------|
| `Sys/config.py` | **集中配置**：路径、模型、NPU、PageRank、时序、Skill 选择 |
| `Sys/Collect/Collector.py` | 数据采集：解析原始故障 JSON，提取拓扑节点、告警、日志、路径交汇度 |
| `Sys/Modify/Modifier.py` | 拓扑剪枝：基于交汇度 + 告警权重的 Jaccard 评分与 PageRank（method 0~4） |
| `Sys/CaseReviewer/CaseReviewer.py` | LLM 推理引擎：vLLM + DeepSeek-R1-Distill-Qwen-32B，含三阶段 Co-occurrence 规则挖掘闭环 |
| `Sys/CaseReviewer/FeatureExtract.py` | 错案 Python 特征提取器，为 LLM 反思提供结构化数据 |
| `Sys/RootCauseAnalyze/SkilledAnalyzer.py` | Skill 触发的 LLM RCA 分析器 |
| `Sys/RootCauseAnalyze/SkillNRefineAnalyzer.py` | Skill + Refine 双阶段分析器 |
| `Sys/RootCauseAnalyze/evidence_fusion.py` | **证据融合层**：三个 Skill 输出 → 紧凑「候选设备综合证据表」+ Top-K 详情，解决 prompt 超长截断 |
| `Sys/RootCauseAnalyze/skill_pipeline.py` | **纯算法流水线**：任意 Skill 组合评分融合（不依赖 LLM/NPU），端到端评测 |
| `Sys/RootCauseAnalyze/llm_alarm_scorer.py` | **LLM 告警打分**：对缺失告警去重后用 LLM 语义打分 1-100，补全权重表 |
| `Sys/Score/Score_N.py` | 评分模块（Top-1~5） |
| `Sys/AlarmWeightBuilder.py` | 全局告警权重构建器：`build()` 初始化 / `learn_from_labels()` 基于 P(root\|alarm) 学习 |
| `SkillBank/SkillExecutor.py` | 动态 Python Skill 插件系统：LLM 反思 → 自动生成插件 → 热加载 |
| `SkillBank/skills/topo.py` | **Skill 1** — `topology_pagerank_rank`：无向 + 有向 PageRank + Top-K 数据提取 |
| `SkillBank/skills/co_occur.py` | **Skill 2** — `co_occurrence_alarm_check`：告警权重 + 共现规则匹配 |
| `SkillBank/skills/temporal_score.py` | **Skill 3** — `temporal_score_devices`：Burst + Early Bird + Density |
| `graph_only.py` | 消融实验：无向/有向 PageRank（`--directed`，内部委托给 skill_pipeline） |
| `scripts/` | Bash 推理/消融脚本：单次推理、全量消融(22组)、LLM 告警打分 |
| `Baseline/` | 基线方法：TraceRCA、NetEventCause、BiAn（待补 FP-Growth / DBSCAN / Random Walk） |
| `docs/毕业论文/` | 毕设论文 LaTeX 源码（已完成） |
| `docs/papers/` | 参考文献 PDF + TXT + summary |
| `data/` | 标注数据（nodes_labeled, pingmesh_labeled） |

## 技术栈
- **LLM 推理**: DeepSeek-R1-Distill-Qwen-32B (vLLM 0.7.3 + Ascend 910B3 NPU)
- **核心依赖**: PyTorch 2.5.1, LangChain 0.3.12, NumPy, pandas, networkx
- **本地可部署 LLM**: DeepSeek-Distill 系列、Qwen2.5 系列（待考察 Qwen3、Internlm2.5、Llama 3.x 内网可用性）

## 实验数据与当前结果

### 数据集
- 华为云 2025 年 9-12 月生产环境，**104 例**真实网络故障
- 常规场景 90 例（≤600 条告警），告警风暴场景 14 例（>600 条告警）
- 划分阈值基于 DeepSeek-32B 的 131K token 上下文窗口

### 当前指标（毕设最终态：LLM + 告警权重 + 无向 PageRank, DeepSeek-32B）

| 场景 | Top-1 | Top-3 | 单 case 耗时 |
|------|-------|-------|--------------|
| 常规场景 | 60.00% | 92.22% | 9.99s |
| 告警风暴 | 35.71% | 78.57% | 9.99s |

### 消融结论
- PageRank 以 0.026s 额外开销换取风暴 Top-1 从 7.14% → 35.71%（+400%）
- LLM 语义推理使常规 Top-1 从 38.89% → 60.00%
- 两模块互补：PageRank 保下限，LLM 定上限

### 基座模型对比
- 7B 在风暴场景完全失效（Top-1 = Top-3 = 0%）
- 同规模下 R1 蒸馏 > 原生 Instruct（32B 风暴 Top-1: 35.71% vs 14.29%）

## 数据管道与文件读取流程

### 原始数据 → 标注数据

```
data/pingmesh_labeled/*.json          ← 华为云原始故障 JSON (104例)
        │
        ▼  Collector.process_network_nodes()
        │
data/nodes_labeled/{timestamp}/{csn}/
        ├── pingmesh-{csn}-全链路.json   ← 节点+告警+拓扑
        ├── {csn}_info.json              ← 故障元信息
        └── label.json                   ← 人工标注
```

### 拓扑剪枝 → LLM 推理 → 评测

```
nodes_labeled/                        Modifier(file_path).run()
        │                             get_top_k_jaccard_ips → topo_simplify
        ▼                                       │
   nodes.json ←─────────────────────────────────┘
        │
        ▼  SkilledAnalyzer / CaseReviewer
        │  generate_prompts() → batch LLM 推理
        │
   data/res/{timestamp}/res.json
        │
        ▼  Scorer.calculate_metrics()
        │
   data/res/{timestamp}/
        ├── sum.json                      ← 汇总指标
        ├── draft_ranking_failures.json   ← 错案详情
        └── refined_ranking_failures.json
```

### 各模块文件读取约定

| 模块 | 遍历方式 | 节点文件 | 依赖文件 |
|------|---------|---------|---------|
| Modifier | `glob(**/**/*_info.json)` | — | `*_info.json` |
| graph_only.py | `os.walk` | `pingmesh-*-全链路.json` | `info.json` |
| LLM Analyzers | `os.walk` → `generate_prompts()` | `nodes.json` | `info.json` |
| AlarmWeightBuilder | `os.walk` → `_find_case_files()` | `pingmesh-*-全链路.json` / `nodes.json` | `info.json` |
| Baselines | `os.walk` → `generate_prompts()` | `nodes.json` | `info.json` |
| Scorer | 读 `res.json` 的 `dir` 字段 | — | `label.json`, `label_propath.json` |

### 告警字段约定（全仓库统一）
```python
name = event if isinstance(event, str) else event.get("alarm_name", event.get("name", ""))
# 即 alarm_name > name > 空字符串
```

### 全局告警权重表
```
data/nodes_labeled/  →  AlarmWeightBuilder.build() / learn_from_labels()
                    →  data/weights/classified_alarms/all_alarms.json
                       [{alarm_name, alarm_priority}, ...]
                    →  graph_only.py / Skill 读取并写入 personalization 向量
```

## 已实现模块

### 有向 PageRank（`graph_only.py` + `SkillBank/skills/topo.py`）
故障传播方向：`linked_from → device → linked_to`（上游→下游）。RCA 反方向追踪：边方向反转，使 PageRank 随机游走从受影响 endpoint 流向上游根因。

```python
# graph_only.py:133-181 + SkillBank/skills/topo.py 同步实现
for upstream in node.get("linked_from", []):
    G.add_edge(ip, upstream)          # device → 上游
for downstream in node.get("linked_to", []):
    G.add_edge(downstream, ip)        # 下游 → device
```
- 共享辅助函数：`_load_alarm_weights`, `_parse_endpoint_ips`, `_compute_personalization`
- CLI: `python graph_only.py --directed`

### 时序嫌疑度 Skill（`SkillBank/skills/temporal_score.py`，skill_id=3）

| 特征 | 公式 | 权重 |
|------|------|------|
| Burst Score | `count(\|t - ref_time\| ≤ 5min) / total` | 0.40 |
| Early Bird | `1 / rank(first_alarm_among_all_devices)` | 0.35 |
| Temporal Density | `alarm_count / active_span_min` (cap 20/min) | 0.25 |

参考时间 fallback：`ref_time_ms` 参数 → `info["alarm_time"]` → `*_info.json`

### AlarmWeightBuilder.learn_from_labels()（`Sys/AlarmWeightBuilder.py`）
基于标注数据用条件概率学习权重：

```
P(root_cause | alarm) = root_cause_hits[alarm] / total_appearances[alarm]
weight                = round(P * 100)
```

当 nodes 无告警数据时，自动 fallback 到 label.json root-cause-only 统计。

### SkillBank 整理（5 个 → 3 个）

| ID | 文件 | Executor | 用途 |
|----|------|----------|------|
| 1 | `topo.py` | `topology_pagerank_rank` | 无向/有向 PageRank + Top-K 数据提取 |
| 2 | `co_occur.py` | `co_occurrence_alarm_check` | 告警权重 + 共现规则匹配 |
| 3 | `temporal_score.py` | `temporal_score_devices` | 时序 Burst/EarlyBird/Density |

清理动作：
- 删除 `weight_cal.py`（功能被 co_occur.py 完全覆盖）
- 删除 `topo_nodes.py`（合并进 topo.py）
- 修复 `co_occur.py` 与 `weight_cal.py` 的 executor 同名冲突

### 集中配置（`Sys/config.py`）
6 组配置：`DataPaths` / `SkillPaths` / `ModelConfig` / `PageRankConfig` / `TemporalConfig` / `SkillConfig`。所有硬编码路径与参数从此读取，旁注常用选项。

```python
from Sys.config import config
LLM(model=config.model.model_path, ...)
config.data.nodes_labeled
config.skill.skill_ids  # [1, 2, 3]
```

已迁移到 config 的模块：`SkilledAnalyzer.py`, `Score_N.py`。

### 证据融合层（`Sys/RootCauseAnalyze/evidence_fusion.py`）

**问题**：三个 Skill 输出被原样拼接进 `SKILLED_PROMPT`，实测常规 case 达 6057 字符（nodes.json 的 2.4 倍）。`topo` 的 `top_suspects_full_data` 逐字复制 `NODES`；`temporal` dump 全部设备；截断逻辑只截 `INFO`/`NODES` 而 `skill_ret` 永不截断 → 风暴 case 撑爆预算导致整个 prompt 腰斩。

**方案**：在「skill 输出 → prompt」边界压缩（Skill 文件不动，消融实验保持完整）。`build_fused_evidence()` 按 IP 合并三个 skill，输出三段紧凑文本：

| 段 | 内容 | 填入占位符 |
|----|------|-----------|
| `evidence_str` | 候选设备综合证据表（排名\|IP\|角色\|PR有向\|PR无向\|时序分\|告警权重\|Cross\|关键告警）+ 共现警告 | `{SKILLRET}` |
| `info_brief` | info.json 只取关键字段（不整体 dump） | `{INFO}` |
| `candidate_detail` | Top-K 候选告警/日志名称（去重，不 dump 完整 dict） | `{NODES}` |

**效果**：常规 case 6057 → 1526 字符（−75%）；伪风暴 case（750 告警）从 ~26k → 1522 字符（−93%）。**告警去重后融合输出大小与告警量解耦**，风暴 case 不再撑爆。

集成点：`SkilledAnalyzer._build_final_prompt`、`SkillNRefineAnalyzer._prepare_context` 改用融合层 + 证据表优先的安全网截断。`SKILLED_PROMPT` 三个占位符语义重定义（Info / 证据表 / Top-K 详情）。

### Skill Pipeline 纯算法流水线（`Sys/RootCauseAnalyze/skill_pipeline.py`）
不依赖 LLM/NPU，对任意 Skill 组合评分融合（归一化后等权平均），输出 `res.json` 可直接评测。

```bash
python Sys/RootCauseAnalyze/skill_pipeline.py -s 1 3 --directed -k 5 -o my_test
```

### LLM 前置告警打分（`Sys/RootCauseAnalyze/llm_alarm_scorer.py`）
对权重表中缺失的告警名去重后，由 LLM 根据网络运维严重程度打出 1-100 分，合并后输出 enriched 权重文件供 PageRank 使用。

### 推理脚本 CLI

| 脚本 | 依赖 | 用途 |
|------|------|------|
| `scripts/run_inference.sh` | NPU | 单次推理 + 评分（默认 skills=[1,3] k=5） |
| `scripts/run_full_ablation.sh` | 无 | 22 组纯算法消融 (11 Skill × 2 权重来源) |
| `scripts/run_skill_ablation.sh` | 无 | 8 组纯算法消融 |
| `scripts/run_llm_alarm_scoring.sh` | NPU | LLM 告警去重打分 → 新权重 → skill_pipeline 评测 |

### 关键发现（146 例人工标注数据，2026-06-12 消融结果）

| 等级 | 组合 | Top-1 | Top-5 | 发现 |
|------|------|-------|-------|------|
| S | `[1,3]` topo+temporal dir (llm权重) | **87.41%** | 89.51% | 纯算法天花板，时序是压倒性最强信号 |
| A | `[3]` temporal only | 76.22% | 88.81% | 3/4 的 DCN 故障中根因设备告警最先爆发 |
| C | `[1]` topo only | 14-17% | 28-33% | 人工标注数据上 PageRank 单独很弱（旧数据 39% 因标注偏拓扑） |
| D | `[2]` co_occur only | 1-8% | 3-20% | 告警权重单独几乎无用，需绑定 topo/temporal |

**核心结论**：
- 时序 + 拓扑协同：topo 把时序抓不到的 ~13 个 case 补上了（76→87%）
- co_occur（Skill 2）在等权融合中拖后腿 — 每个加它的组合都掉分
- LLM 复核从 87% 目前的 dropout（→35%），因候选详情给 LLM 的信息量过大（K=10 + raw JSON），已修复为紧凑版 + 可调 K

### 后续实验方向

1. **Test 1: LLM 复核** — 调 K（3→5→10），紧凑版详情（`-k` 参数）
2. **Test 2: LLM 前置告警打分** — 去重后用 LLM 给缺失告警打分 → 补全权重表 → topo+temporal 对比
3. **新方案**：LLM 前置打分 → topo+temp 排名 → LLM 复核 Top-K（三阶段）

---

## 投稿计划

### 目标
- **目标会议**: ICSE 2027 SEIP / FSE / KDD / INFOCOM（按 Phase 完成情况升档）
- **时间**: 不设硬截止，优先完善方法与精度
- **对标论文**: COLA (ICSE 2024 SEIP) — Knowledge-Aware Alert Aggregation
- **中文毕设**: 已完成（南开大学 2026 年 5 月）

### 当前评估

**优势（被低估）**：
- 8× Ascend NPU 本地部署 → 可做 SFT（COLA 有，多数 LLM RCA 论文无）
- 3 个 Skill 已实现但**未串进主流程**（有向 PR / temporal / 学习版权重）
- 104 例标注完整 → 可做 80/20 split 或 5-fold CV
- SkillBank 动态插件系统是论文里**最特别但未被讲清楚**的工程贡献

**真正瓶颈不是缺 GPT-4，是自己方法未榨干**：60% / 35.71% Top-1 距离上限至少还有 15-25 pp。

### 反驳"无外部 LLM 对比"的策略

| 反驳点 | 策略 |
|--------|------|
| "为什么不用更强模型" | 内网可部署的 **backbone 多样性**：DeepSeek-Distill / Qwen2.5 / Qwen3 / Internlm2.5 / Llama3.x 跨家族 5 个 |
| "为什么不微调" | **做 LoRA SFT** — 转劣势为优势章节 |
| "为什么不开源对比" | 强调 **数据合规 + 工业部署**（SEIP track 核心定位，COLA 同样是华为云数据） |

---

## 六阶段行动计划

### Phase 1：榨干已实现但未集成的工作（1.5 周，预期 +8~15 pp）

| # | 任务 | 工时 | 预期增益 |
|---|------|------|---------|
| 1.1 | 把有向 PageRank 集成进 Modifier（替换无向） | 1 天 | Top-1 +2~5 pp |
| 1.2 | 把 temporal Skill 串进 SkilledAnalyzer 默认 skill list `[1,2,3]` | 1 天 | 风暴 Top-1 +3~8 pp |
| 1.3 | 用 `learn_from_labels()` 学到的权重替换静态权重 | 1 天 | Top-1 +2~5 pp |
| 1.4 | 三者合在一起，跑完整消融表（8 行变体） | 2 天 | 量化各模块独立/联合贡献 |
| 1.5 | 把 ~42 个失败案例分类（拓扑错 / PR 排第 4-5 / LLM 选错 / 标签问题） | 2 天 | 锁定下阶段方向 |

### Phase 2：方法改进（2~3 周，预期 +5~10 pp）

| # | 任务 | 工时 | 预期增益 |
|---|------|------|---------|
| 2.1 | LLM Top-K reranking + 置信度 + PageRank 加权融合 | 3 天 | Top-1 +3~7 pp |
| 2.2 | 风暴场景两轮 CoT：summarize → verify（COLA 同款） | 3 天 | 风暴 Top-1 +3~8 pp |
| 2.3 | PageRank α / Top-K / cross 乘数敏感性扫描 | 1 天 | +1~3 pp + 堵超参攻击点 |
| 2.4 | 闭环验证 co-occurrence skill 自演进（反思→规则→重评测） | 4 天 | 风暴 Top-1 +2~6 pp，独家亮点 |
| 2.5 | PageRank + Temporal + Weight 三分数 learned-weight 线性组合 | 2 天 | +2~5 pp |

### Phase 3：LoRA SFT（3~4 周，预期 +5~15 pp，转劣势为优势）

| # | 任务 | 工时 | 说明 |
|---|------|------|------|
| 3.1 | 80/20 train/test split 或 5-fold CV | 0.5 天 | 防过拟合 |
| 3.2 | 数据格式化：(prompt, gold reasoning, gold root IPs) | 2 天 | 从 label.json 构造 |
| 3.3 | LoRA on DeepSeek-32B (MS-Swift / LLaMA-Factory on Ascend) | 1 周 | 8 卡可行，主要环境调试 |
| 3.4 | 对照实验：ICL only / SFT only / ICL+SFT | 1 周 | 三组对比 |
| 3.5 | LoRA rank ∈ {8, 16, 32, 64} 扫描 + 过拟合检测 | 3 天 | — |

**过拟合风险缓解**：
- LoRA rank ≤ 16
- 只调最后几层
- 5-fold CV 报告均值 ± 方差
- 必要时**生成合成数据**：32B 自反思生成"错案→修正推理"训练数据，扩到 500+ 条

### Phase 4：基线 + Backbone 多样性（2 周，防御性）

| # | 任务 | 工时 |
|---|------|------|
| 4.1 | FP-Growth 告警共现挖掘 baseline | 1 天 |
| 4.2 | DBSCAN 时空聚类 baseline | 1 天 |
| 4.3 | 重新校准 TraceRCA（14.44% Top-1 太低，疑有 bug） | 2 天 |
| 4.4 | 新增 backbone：Qwen3-32B / Internlm2.5-20B（内网可用性确认后） | 1 周 |
| 4.5 | Random Walk 无权 PageRank（消融 baseline） | 0.5 天 |

### Phase 5：NIKA 公开数据集（2 周，扩大评估面）

| # | 任务 | 工时 |
|---|------|------|
| 5.1 | NIKA 数据下载 + 格式转换适配 Collector | 3 天 |
| 5.2 | NIKA 上跑完整 pipeline + 消融 | 1 周 |
| 5.3 | 跨数据集泛化分析（华为云训练 → NIKA 测试） | 3 天 |

**注意**：NIKA 结果可能比华为云**差**（领域不同）。可诚实呈现，加 Discussion "跨域泛化的局限性"，反而显得论文可信。

### Phase 6：理论框架 + 论文重写（3 周）

| # | 任务 | 工时 |
|---|------|------|
| 6.1 | 重写 Introduction "3 挑战 → 3 设计" 叙事（COLA 同款） | 1 周 |
| 6.2 | 新增章节 "Self-Evolving Skill-Based Architecture"，凸显 SkillBank 工程贡献 | 1 周 |
| 6.3 | PageRank personalization 理论化为贝叶斯先验（数学推导） | 3 天 |
| 6.4 | 失败案例 + 局限性章节 | 3 天 |
| 6.5 | Bootstrap CI + 显著性检验，所有结果加置信区间 | 2 天 |

### 总时间表

| 阶段 | 时长 | 累计 | 关键产出 |
|------|------|------|---------|
| Phase 1 | 1.5 周 | 1.5 周 | 当前方法的 +10 pp 上限验证 |
| Phase 2 | 3 周 | 4.5 周 | 方法改进到工程上限 |
| Phase 3 | 4 周 | 8.5 周 | SFT 章节，转劣势为优势 |
| Phase 4 | 2 周 | 10.5 周 | 基线 + backbone 防御 |
| Phase 5 | 2 周 | 12.5 周 | NIKA 公开数据集 |
| Phase 6 | 3 周 | 15.5 周 | 论文重写到顶会水平 |

**约 16 周（4 个月）— 可达的顶会投稿状态。**

### 最终成绩区间预估

| 阶段后 | 常规 Top-1 | 风暴 Top-1 | 适合投稿 |
|--------|-----------|-----------|---------|
| 当前 | 60.00% | 35.71% | 毕业论文 |
| Phase 1 后 | 65~70% | 45~50% | 二档会议 (NetSoft / IPCCC) |
| Phase 2 后 | 70~75% | 55~60% | ICSE SEIP 边缘 |
| Phase 3 后 | 75~82% | 60~70% | ICSE SEIP 稳 / FSE 边缘 |
| Phase 4-5 后 | 75~82%（多数据集） | 60~70% | FSE / KDD / INFOCOM |

### 关键判断点（每阶段后停一下决定下一步）

1. **Phase 1 结束**：若三模块涨幅 < 5 pp → 说明信号已被 LLM 隐式学到，Phase 2 应聚焦 reranking/CoT 而非"信号增强"
2. **Phase 2 结束**：若 reranking + CoT 涨幅 < 3 pp → LLM 已是上限，必须 SFT 才能突破
3. **Phase 3 结束**：若 SFT 严重过拟合 → 退回 ICL，把 SFT 作为"我们尝试过但不行"写进 Discussion

### 不建议做的事
- 不做外部 LLM 对比（内网约束）
- 不重写 PageRank 算法（已够好）
- 不等所有实验完美再投（残缺但真实 > 拖延）

---

## COLA 论文对标分析

### COLA 核心架构
```
原始告警流 → 相关性挖掘（时序条件概率 + node2vec 空间嵌入）
           → 告警聚合图（异构信息网络 HIN）
           → LLM 推理（ICL + P-tuning v2 微调）
           → 部署经验总结（4 条工业实践）
```

### 三挑战 → 三方案 对应

| 挑战 | COLA 方案 | 我们的对应/差距 |
|------|-----------|----------------|
| 领域知识缺失 | ICL + SFT (P-tuning v2) | ICL only（Phase 3 补 SFT） |
| 长文本上下文 | 两轮 CoT（聚合→摘要→推理） | 单轮 CoT + 拓扑剪枝截断（Phase 2.2 补两轮） |
| 效率瓶颈 | 统计预过滤 | PageRank 剪枝 + Skill 预计算 |

### Research Questions 对照

| RQ | COLA 发现 | 我们的可对标性 |
|----|----------|---------------|
| RQ1: 效果 | 告警聚合 F1 优于纯规则 | Top-1/3/5 指标 |
| RQ2: 效率 | 统计预过滤减少 60%+ LLM 调用 | PageRank 0.026s/case |
| RQ3: 消融 | ICL + SFT 各自贡献；两轮 CoT 优于单轮 | 已有四组消融（PageRank +400% 风暴 Top-1） |

### COLA Introduction 叙事链（待对齐）
1. 云运维依赖告警聚合 → 现有方法泛化差
2. LLM 有知识但不了解具体系统 → 需注入领域知识
3. 长告警序列超出 LLM 上下文 → 需预过滤和两轮推理
4. **三挑战 → 三方案**，华为云/微软真实数据验证
5. 贡献：HIN 建模 + LLM 知识注入 + 两轮 CoT + 工业验证

---

## 公开数据集

| 数据集 | 规模 | 特点 | 可行性 |
|--------|------|------|--------|
| **NIKA** | 640 网络故障，54 类型，5 场景（CLOS/ISP/DC） | 拓扑 + 事件 + 根因标注，CLOS 与 Pingmesh DC 同构 | 高 — 直接可用（Phase 5）|
| LEMMA-RCA | 多模态微服务 RCA | metric/log/trace 多模态 | 中 — 需适配 |
| GAIA | 微服务多模态异常 | metric/log/trace | 低 — 非网络场景 |

---

## 待新增基线

| 基线 | 类型 | 来源 | 作用 | 阶段 |
|------|------|------|------|------|
| **FP-Growth** | 统计规则 | 经典关联挖掘 | 告警共现频繁项集 | Phase 4.1 |
| **DBSCAN** | 聚类 | 经典时空聚类 | 时间/空间告警聚类 RCA | Phase 4.2 |
| **Random Walk (无权)** | 图算法 | 消融对比 | 验证告警权重贡献 | Phase 4.5 |
| LM-PACE | LLM-based | FSE 2025 | LLM + 时序事件链排序 | 暂缓（依赖外部 LLM）|
| ClusterRCA | 统计 + LLM | KDD 2024 | 告警聚类 + LLM 语义 RCA | 暂缓（依赖外部 LLM）|
