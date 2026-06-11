# CLAUDE.md — 仓库概览

## 项目定位
面向大规模数据中心网络的拓扑关联事件根因定位（RCA）系统。论文提出 **Pingmesh触发 → 个性化PageRank拓扑剪枝 → LLM语义推理复核** 的三阶段方案，基于华为云104例真实故障案例验证。

## 仓库结构

| 目录/文件 | 用途 |
|-----------|------|
| `Sys/Collect/Collector.py` | 数据采集：解析原始故障JSON，提取拓扑节点、告警、日志、路径交汇度 |
| `Sys/Modify/Modifier.py` | 拓扑剪枝：实现基于交汇度+告警权重的Jaccard评分和多variant PageRank排序（method 0~4） |
| `Sys/CaseReviewer/CaseReviewer.py` | LLM推理引擎：vLLM部署DeepSeek-R1-Distill-Qwen-32B，支持三阶段Co-occurrence规则挖掘闭环 |
| `Sys/CaseReviewer/FeatureExtract.py` | 错案Python特征提取器，为LLM反思提供结构化数据 |
| `Sys/Score/Score_N.py` | 新版评分模块（Top-1/3指标计算） |
| `SkillBank/SkillExecutor.py` | 动态Python Skill插件系统：大模型反思输出→自动生成Python诊断插件→热加载执行 |
| `SkillBank/skills/co_occur.py` | 告警共现规则挖掘Skill |
| `SkillBank/skills/temporal_score.py` | 时序嫌疑度评分Skill：Burst Score + Early Bird + Temporal Density |
| `graph_only.py` | 消融实验：无向/有向PageRank纯图算法（不依赖LLM） |
| `Sys/AlarmWeightBuilder.py` | 全局告警权重表构建器：支持 build() 和 learn_from_labels() 两种模式 |
| `utils/prompts.py` | 全量Prompt模板（约15个）：RCA定位、错案反思、规则蒸馏、共现挖掘、孪生对比等 |
| `Baseline/` | 基线方法：TraceRCA (Jaccard统计), NetEventCause (TPP), BiAn (2-stage LLM), 待新增 LM-PACE/ClusterRCA/FP-Growth/DBSCAN |
| `docs/毕业论文/` | 毕设论文LaTeX源码（main.tex, manual.tex正文, abstract.tex, nkthesis.bib） |
| `docs/papers/` | 32篇参考文献PDF+TXT+部分summary |
| `agent/` | AI Agent工作区（算法艺术/金融模型模板，与论文无关） |
| `data/` | 标签数据（nodes_labeled, pingmesh_labeled） |

## 技术栈
- **LLM推理**: DeepSeek-R1-Distill-Qwen-32B (vLLM 0.7.3 + Ascend 910B3 NPU ×8, 单卡64GB HBM)
- **硬件**: 华为鲲鹏920 (256核), 2TB内存, 8×昇腾910B3
- **核心依赖**: PyTorch 2.5.1, LangChain 0.3.12, NumPy, pandas
- **基线方法**: TraceRCA (Jaccard统计), NetEventCause (简化TPP), BiAn (2-stage LLM)

## 实验数据与结果

### 数据集
- 华为云2025年9-12月生产环境，**104例**真实网络故障
- 常规场景90例（≤600条告警），告警风暴场景14例（>600条告警）
- 划分阈值基于DeepSeek-32B的131K token上下文窗口

### 关键指标（完整方案：LLM+告警权重+PageRank, DeepSeek-R1-Distill-Qwen-32B）

| 场景 | Top-1 | Top-3 |
|------|-------|-------|
| 常规场景 | 60.00% | 92.22% |
| 告警风暴 | 35.71% | 78.57% |
| 单Case推理耗时 | — | 9.99s |

### 消融结论
- PageRank以0.026秒额外开销换取了告警风暴Top-1从7.14%→35.71%（+400%）
- LLM语义推理使常规场景Top-1从38.89%→60.00%
- 两模块互补：PageRank保下限，LLM定上限

### 基座模型对比
- 7B模型在告警风暴场景完全失效（Top-1=Top-3=0%）
- 同规模下R1蒸馏优于原生Instruct（32B告警风暴Top-1: 35.71% vs 14.29%）

## 投稿计划
- **目标会议**: ICSE 2027 SEIP Track（COLA 同 venue）
- **截止日期**: 2026-06-30（摘要），2026-07-07（全文）
- **当前日期**: 2026-06-10，剩余约 20 天
- **对标论文**: COLA (ICSE 2024 SEIP) — Knowledge-Aware Alert Aggregation in Large-Scale Cloud Systems
- **中文毕设**: 已完成（南开大学，2026年5月）

## 数据管道与文件读取流程

### 原始数据 → 标注数据

```
data/pingmesh_labeled/*.json          ← 华为云原始故障 JSON (104例)
        │
        ▼  Collector.process_network_nodes()
        │    解析 full_link.task_topo / alarm_list / log_list / cross
        │
data/nodes_labeled/{timestamp}/{csn}/
        ├── pingmesh-{csn}-全链路.json   ← 节点+告警+拓扑 (name_map)
        ├── {csn}_info.json              ← 故障元信息 (source_ip, sink_ip, alarm_time)
        └── label.json                   ← 人工标注 (Modifier 之后写入)
```

### 拓扑剪枝（Modifier）

```
data/nodes_labeled/**/**/*_info.json    ← glob 递归搜索所有案例
        │
        ▼  Modifier(file_path).run()
        │    get_top_k_jaccard_ips(method) → Top-K 候选设备
        │    topo_simplify(k) → 剪除无关节点
        │
data/nodes_labeled/{timestamp}/{csn}/
        ├── nodes.json                   ← 剪枝后的节点数据 (覆盖写入)
        ├── info.json                    ← 故障元信息 (从 alarm_content 提取)
        └── label.json                   ← 人工标注 (从 alarm_content.label 提取)
```

### 各模块读取方式对照

| 模块 | 遍历方式 | 节点文件匹配 | 依赖文件 |
|------|---------|-------------|---------|
| **Modifier** | `glob(**/**/*_info.json)` | — (读 info.json) | `*_info.json` |
| **graph_only.py** | `os.walk` | `pingmesh-*-全链路.json` | `info.json` |
| **LLM Analyzers** (Skilled/SkillNRefine) | `os.walk` → `generate_prompts()` | `nodes.json` | `info.json` |
| **AlarmWeightBuilder** | `os.walk` → `_find_case_files()` | `pingmesh-*-全链路.json` / `nodes.json` | `info.json` |
| **三个基线** (TraceRCA/NEC/BiAn) | `os.walk` → `generate_prompts()` | `nodes.json` | `info.json` |
| **Scorer** | 读 `res.json` 中的 `dir` 字段 | — | `label.json`, `label_propath.json` |

### 全局告警权重表

```
data/nodes_labeled/  (全部案例)
        │
        ▼  AlarmWeightBuilder.build()
        │    遍历所有节点，提取 unique alarm_name
        │    初始权重全 0
        │
data/weights/classified_alarms/all_alarms.json
        │  格式: [{"alarm_name": "...", "alarm_priority": 0.0}, ...]
        │
        ▼  graph_only.py 读取
        │    default_weights[name.lower()] = int(priority)
        │    → PageRank personalization 向量中的告警权重项
```

### LLM 推理 → 评测

```
data/nodes_labeled/  (全部案例)
        │
        ▼  SkilledAnalyzer / SkillNRefineAnalyzer / CaseReviewer
        │    generate_prompts() → batch LLM 推理
        │
data/res/{timestamp}/res.json
        │  每项: {dir, prompt, draft_response, response, ...}
        │
        ▼  Scorer(res.json).calculate_metrics()
        │    读取每个 case 的 label.json → GroundTruth
        │    解析 draft_response/response → Prediction
        │    计算 Top-1~5 / 期望步长 / 传播路径 F1
        │
data/res/{timestamp}/
        ├── sum.json                      ← 汇总指标
        ├── draft_ranking_failures.json   ← 错案详情
        └── refined_ranking_failures.json ← refine 阶段错案
```

### 告警字段约定

告警名提取优先级（全仓库统一）：
```python
# 事件可能是 str 或 dict
name = event if isinstance(event, str) else event.get("alarm_name", event.get("name", ""))
```

即 `alarm_name` > `name` > 空字符串。

### 统一路径

所有模块默认数据根目录：`/home/sbp/lixinyang/pingmesh/data/nodes_labeled/`

## 有向 PageRank（新增）

### 设计动机
无向 PageRank 假设故障影响在拓扑中对称传播，但真实网络中故障沿 `上游→下游` 方向传播 (linked_from → device → linked_to)。根因定位需要反方向追踪：从受影响的 endpoint 沿上游回溯到根因设备。

### 实现 (`graph_only.py:133-181`)
```python
def run_directed_pagerank(node_list, infodta, weight_dirpath=...):
    G = nx.DiGraph()
    for node in node_list:
        ip = node.get("mgmt_ip", ...)
        G.add_node(ip)
        # Edge 方向指向故障传播的上游（反向于故障传播方向）
        for upstream_neighbor in node.get("linked_from", []):
            G.add_edge(ip, upstream_neighbor)      # device → 上游邻居
        for downstream_neighbor in node.get("linked_to", []):
            G.add_edge(downstream_neighbor, ip)    # 下游邻居 → device
    # 共享 _compute_personalization() 构建 personalization 向量
    rwr_scores = nx.pagerank(G, alpha=0.85, personalization=personalization)
```
- Edge 反向：故障传播 `upstream → device → downstream`，PageRank 随机游走 `device → upstream`, `downstream → device`
- 共享辅助函数 `_load_alarm_weights()`, `_parse_endpoint_ips()`, `_compute_personalization()` 与无向版本
- CLI: `python graph_only.py --directed` 运行有向版本消融实验

### 共享辅助函数（重构提取）
- `_load_alarm_weights(weight_dirpath)`: 加载 JSON 告警权重数组 → {name_lower: priority}
- `_parse_endpoint_ips(infodta)`: 从 info dict 提取 source_ips / sink_ips 列表
- `_compute_personalization(node_list, weights_dict, source_ips, sink_ips)`: 基于告警权重 + cross count + endpoint 邻近度构建 per-device PageRank personalization 向量

## 时序嫌疑度 Skill（新增）

### 设计动机
纯拓扑 PageRank 忽略了告警的时间维度——根因设备的告警往往最先触发且集中爆发，而级联设备的告警延迟出现且分散。时序模块解决此信息盲区。

### 实现 (`SkillBank/skills/temporal_score.py`)
三个时序特征，综合为设备嫌疑度：

| 特征 | 公式 | 权重 | 含义 |
|------|------|------|------|
| **Burst Score** | `count(abs(t - ref_time) ≤ 5min) / total` | 0.40 | 告警在故障参考时间附近集中度 |
| **Early Bird** | `1 / rank(first_alarm_among_all_devices)` | 0.35 | 最早告警的设备排名 |
| **Temporal Density** | `alarm_count / active_span_minutes` (cap 20/min) | 0.25 | 单位时间告警密度 |

```python
SKILL_META = {"skill_id": "5", "skill_name": "temporal_score_devices", ...}

def temporal_score_devices(node_list, info, dirpath, ref_time_ms, window_ms=300000):
    # 1. 确定参考时间: info["alarm_time"]
    # 2. 收集每设备时间戳: node["alarms/logs"][*]["alarm_time"] + label.json fallback
    # 3. 计算三特征 → combined = 0.40*burst + 0.35*early + 0.25*norm_density
    # 4. 输出 JSON: {device_scores: {ip: score}, top_devices: [...]}
```
- 输出格式兼容 `graph_only.py` 的 PageRank personalization 向量更新
- 参考时间 fallback 链: `ref_time_ms` 参数 → `info["alarm_time"]` → `*_info.json` 文件
- 时间戳 fallback: node alarms/logs → label.json 中 root_cause 设备的告警

### 与 PageRank 集成路径
时序得分可与 PageRank personalization 向量相乘或加权求和，或替换 personalization 中的告警权重项。执行指令见 `SKILL_META["execution_instructions"]`。

## 公开数据集

为补充仅在华为云104例私有数据上的评估，已识别以下公开数据集：

| 数据集 | 规模 | 特点 | 可行性 |
|--------|------|------|--------|
| **NIKA** | 640 网络故障，54 故障类型，5 网络场景 (CLOS/ISP/DC) | 含拓扑 + 事件 + 根因标注，CLOS 场景与 Pingmesh DC 拓扑最接近 | 高 — 直接可用 |
| **LEMMA-RCA** | 多模态微服务 RCA | 含 metric/log/trace 多模态数据 | 中 — 需适配网络场景 |
| **GAIA** | 微服务多模态异常检测 | 含 metric/log/trace | 低 — 非网络场景 |

**NIKA 优先**：CLOS 拓扑与数据中心网络结构同构，可直接用于补充评估。

## 待新增基线

当前仅 3 个基线（TraceRCA 统计、NetEventCause TPP、BiAn LLM），需补充以对标 COLA 的 6 基线标准：

| 基线 | 类型 | 来源 | 作用 |
|------|------|------|------|
| **LM-PACE** | LLM-based | FSE 2025 | LLM + 时序事件链排序，最直接对标 |
| **ClusterRCA** | 统计+LLM | KDD 2024 | 告警聚类 + LLM 语义 RCA |
| **FP-Growth** | 统计规则 | 经典关联挖掘 | 告警共现频繁项集，纯规则 baseline |
| **DBSCAN** | 聚类 | 经典时空聚类 | 基于时间/空间的告警聚类 RCA |
| **Random Walk (无权重)** | 图算法 | 消融对比 | 无向 PageRank 去掉告警权重，验证权重贡献 |

## COLA 论文对标分析

### COLA 核心架构
```
原始告警流 → 相关性挖掘（时序条件概率 + node2vec 空间嵌入）
           → 告警聚合图（异构信息网络 HIN）
           → LLM 推理（ICL + P-tuning v2 微调）
           → 部署经验总结（4 条工业实践）
```

### COLA 的三挑战 → 三方案

| 挑战 | COLA 方案 | 我们的对应/差距 |
|------|-----------|----------------|
| **领域知识缺失** | ICL + SFT (P-tuning v2) 注入知识 | ICL 通过 Prompt，无 SFT |
| **长文本上下文** | 两轮 CoT（聚合→摘要→推理） | 单轮 CoT + 拓扑剪枝截断 |
| **效率瓶颈** | 统计预过滤（时序+空间相关性） | PageRank 剪枝 + Skill 预计算 |

### COLA 的三个 Research Questions

| RQ | COLA 发现 | 可对标性 |
|----|----------|---------|
| RQ1: 效果 | 告警聚合 F1 优于纯规则方法，LLM 提升跨领域泛化 | 我们有 Top-1/3/5 指标 |
| RQ2: 效率 | 统计预过滤减少 60%+ LLM 调用 | PageRank 耗时 0.026s/case |
| RQ3: 消融 | ICL + SFT 各自贡献；两轮 CoT 比单轮好 | 已有消融（PageRank +400% 告警风暴 Top-1） |

### 主要差距与改进方向

| 差距 | 行动 |
|------|------|
| 缺少 SFT 微调对比 | 是否需要 P-tuning v2？目前仅有 ICL |
| 缺少部署经验/工程实践章节 | 可补充 NPU 部署、vLLM 调优经验 |
| 公开数据集评估缺失 | NIKA 作为第二评估数据集 |
| 基线数量不足（3 vs 6） | 新增 LM-PACE, ClusterRCA, FP-Growth |
| 缺少时序信号 | temporal_score Skill 已实现 |
| 无向图假设过强 | 有向 PageRank 已实现 |

### COLA Introduction 叙事链
1. 云运维依赖告警聚合 → 现有方法（规则/统计）泛化差
2. LLM 有知识但不了解具体系统 → 需要注入领域知识
3. 长告警序列超出 LLM 上下文 → 需要预过滤和两轮推理
4. **三个挑战 → 三个方案**，在华为云/微软真实数据验证
5. 贡献：HIN 建模 + LLM 知识注入 + 两轮 CoT + 工业验证

## 四项并行任务进展

| # | 任务 | 状态 |
|---|------|------|
| 1 | 添加时序模块 | ✅ temporal_score Skill 已实现 |
| 2 | 提升拓扑模块性能 | ✅ 有向 PageRank 已实现，待与无向版本对比 |
| 3 | 扩充数据集 | 🔍 NIKA/LEMMA-RCA 已识别，待下载集成 |
| 4 | 补充基线+文献调研 | 🔍 LM-PACE/ClusterRCA/FP-Growth/DBSCAN 已识别，待实现 |

## Git状态
- 仓库存在大量已删除文件的残留索引（`git status` 显示大量D/M标记）
- 有未跟踪的新目录：Baseline/, SkillBank/部分数据文件, docs/, Sys/CaseReviewer/FeatureExtract.py等
- 建议在投稿前清理仓库状态
