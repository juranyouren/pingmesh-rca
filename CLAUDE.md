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
| `utils/prompts.py` | 全量Prompt模板（约15个）：RCA定位、错案反思、规则蒸馏、共现挖掘、孪生对比等 |
| `Baseline/TraceRCA/` | 基线：基于Jaccard索引的纯拓扑统计方法 |
| `Baseline/NetEventCause/` | 基线：简化的时序点过程（指数衰减核）+原始NEC开源代码 |
| `Baseline/BiAn/` | 基线：两阶段LLM（节点摘要→全局RCA），模拟三Agent架构 |
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

## 论文当前状态
- 中文毕设论文已完成（南开大学，2026年5月）
- 目标期刊：智能运维/网络方向
- 主要短板见下方讨论

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

## Git状态
- 仓库存在大量已删除文件的残留索引（`git status` 显示大量D/M标记）
- 有未跟踪的新目录：Baseline/, SkillBank/部分数据文件, docs/, Sys/CaseReviewer/FeatureExtract.py等
- 建议在投稿前清理仓库状态
