# WWW 投稿 Introduction 文献检索策略

> 日期：2026-08-24  
> 目标：为 Pingmesh 根因定位与传播路径重构论文建立可核验的前人工作结论，并提炼 The Web Conference（WWW）近年论文的 Introduction 叙事规律。检索完成并形成证据矩阵后，再重写中文 Introduction。

## 1. 固定研究主线

Introduction 只围绕以下三个挑战展开，不再把传播方向不确定性单列为顶层挑战：

1. **Sparse Cases with Dense Information**：Case 数量少，但一个 case 中的设备与事件复杂；仅依赖 case 级根因标签训练，容易记忆少量 case 的特定模式并产生过拟合。
2. **Multidimensional Evidence with Complex Interactions**：拓扑位置、告警语义和事件时序相互耦合；人工规则或加权统计难以表达非线性交互。
3. **Black-Box Predictions with Limited Interpretability**：深度学习模型是黑盒输出，无法直观展示模型的推理过程。

三个挑战与方法模块的对应关系为：

| 挑战 | 主要方法响应 |
| --- | --- |
| Sparse Cases with Dense Information | PC-STGR-SSL：利用事件、节点特征和关系重建进行图内自监督预训练，再进行 case 级根因排序微调 |
| Multidimensional Evidence with Complex Interactions | PC-STGR：路径条件化 Device–Event 时空异构图与关系感知消息传递 |
| Black-Box Predictions with Limited Interpretability | Stage 2：M1 根因无关三状态概率图 + M2 根因条件传播 DAG、证据映射与解释性反馈 |

## 2. 需要由文献证明的问题

### RQ-L1：少 case、密集图内信息是否是 AIOps/RCA 的真实困难？

- 生产故障标签为何昂贵、稀缺或长尾？
- 现有监督式 RCA/定位方法是否报告过拟合、泛化或新故障类型问题？
- 自监督、无监督或预训练方法如何利用节点、事件、拓扑、时间序列或多模态观测？
- 哪些方法与 PC-STGR-SSL 最接近，哪些差异必须在 Introduction 中说明？

### RQ-L2：多维证据复杂交互为何不能由规则或线性加权充分表达？

- 现有方法使用了哪些证据：拓扑、告警、日志、指标、调用链、主动探测、端点路径？
- 哪些论文明确指出单一模态、独立建模或简单融合的不足？
- 哪些图模型显式建模实体关系、事件时间关系或路径条件？
- 对 Pingmesh 场景而言，现有方法缺少的是哪些观测或任务适配，而不是泛化地说“模型不够复杂”？

### RQ-L3：黑盒根因输出为何不足，已有解释性 RCA 到什么粒度？

- 已有方法输出设备/实例分数、因果图、事件链、传播路径还是自然语言解释？
- 作者如何定义 actionable、interpretable、evidence-grounded 或 provenance-aware？
- 现有解释是否能够映射到原始物理拓扑边、告警和时间证据？
- “已有方法没有传播路径解释”是作者明确陈述、实验未覆盖，还是本文的研究者推断？

### RQ-WWW：WWW 论文通常怎样组织 Introduction？

- 第一段如何从 Web/在线服务/图系统的重要性落到具体任务？
- 相关工作缺口是在 Introduction 中按方法类别展开，还是只压缩为一段？
- 挑战、insight、模块和贡献是否一一对应？
- 方法总览图、动机案例和结果数字分别出现在哪里？
- 贡献列表更强调新任务、新机制、系统实现还是实验规模？

## 3. 检索范围

### 时间范围

- 核心方法与 WWW 写作样本：2022–2026。
- 任务奠基工作（如 Pingmesh、网络层析、经典 RCA）不设严格起始年份。

### 来源优先级

1. 本地 Zotero 已有论文及附件全文；
2. ACM Digital Library、IEEE Xplore、USENIX、会议官网和作者公开论文；
3. arXiv 仅用于尚未正式出版或正式页面缺少全文的论文；
4. 不使用二手博客、营销页面或搜索结果摘要支撑技术缺口。

### 重点会议与期刊

- 目标写作样本：The Web Conference / WWW；
- 网络与系统：SIGCOMM、NSDI、INFOCOM、CoNEXT、IMC、TNSM；
- 软件工程与 AIOps：ICSE、FSE、ASE、ISSRE、KDD；
- 必要时补充 TSE、TSC、TNNLS 等正式期刊。

## 4. 查询族

### Q1：少样本、自监督与图内稠密信息

```text
(incident OR failure OR root cause localization) AND
(self-supervised OR unsupervised OR pretraining OR few-shot) AND
(graph OR topology OR alerts OR telemetry)
```

```text
(AIOps OR microservice OR data center network) AND
(label scarcity OR limited labels OR unseen failures OR long tail) AND
(root cause OR fault localization)
```

候选种子：ART、Eadro、DiagFusion、DejaVu、Nezha、MULAN、CloudRCA，以及 WWW 中使用自监督图表示或少标注图学习的论文。

### Q2：异构、多维和时空交互

```text
(root cause analysis OR fault localization) AND
(multimodal OR heterogeneous OR spatio-temporal) AND
(graph neural network OR graph attention OR topology)
```

```text
(network fault localization OR Pingmesh) AND
(topology OR path OR ECMP) AND
(alert OR event OR temporal OR semantic)
```

候选种子：Pingmesh、R-Pingmesh、PROTON、D2NeT、SkyNet、NetEventCause、BiAn、TAMO、Hawkeye、SkeletonHunter。

### Q3：解释性、证据链与传播路径

```text
(interpretable OR explainable OR actionable OR evidence-grounded) AND
(root cause localization OR incident diagnosis) AND
(graph OR causal graph OR propagation path OR provenance)
```

```text
(failure propagation OR cascading failure OR propagation graph) AND
(data center network OR microservice OR cloud system) AND
(root cause)
```

候选种子：DejaVu、Nezha、ShapleyIQ、MicroHECL、NRCAC、MULAN、Glint，以及具有路径或 provenance 输出的网络诊断工作。

### Q4：WWW Introduction 写作样本

```text
site:dl.acm.org/doi The Web Conference 2024 graph anomaly detection
site:dl.acm.org/doi The Web Conference 2025 root cause analysis
site:dl.acm.org/doi The Web Conference 2023 self-supervised graph learning
site:dl.acm.org/doi The Web Conference explainable graph neural network system
```

优先选择与本文至少共享两个属性的 WWW 论文：图学习、异常/故障诊断、多模态证据、自监督学习、可解释推理或工业系统。只因“同属 WWW”但任务完全无关的论文不进入技术 Related Work，可作为写作样本单独标记。

## 5. 纳入与排除标准

### 纳入

- 正式论文或作者公开版本可获得摘要和方法/实验正文；
- 至少直接支持三个挑战之一，或能代表 WWW Introduction 写法；
- 能提取任务、输入、假设、方法、输出、实验和局限的明确证据；
- 对“最接近工作”优先阅读全文，对外围工作至少阅读摘要、Introduction 和 Conclusion。

### 排除

- 只讨论通用图自监督、与故障/异常/解释任务没有可迁移联系；
- 只输出网络监控数据但不执行定位、诊断或传播分析；
- 缺少原始论文，仅有博客或新闻摘要；
- 与 WWW 写作样本重复、但无法提供新的叙事模式；
- 论文任务和观测假设与 Pingmesh 完全不相容，且没有可迁移机制。

## 6. Zotero 操作规则

1. 先按 DOI、标题和作者检索本地 Zotero，避免重复导入。
2. 新发现论文统一加入已有集合 `aiops/00_待分类`，并添加 `status/to-read`。
3. 技术前人工作添加 `role/related-work` 和 `work/pc-stgr/related`；WWW 写作样本添加 `role/writing-model` 和 `work/pc-stgr/style`。
4. 根据论文内容使用已有 `data/*` 与 `method/*` 标签，不创建同义标签。
5. 每篇核心论文建立模式对应的子笔记，重要局限必须标记为：`作者明确陈述`、`实验未覆盖` 或 `研究者推断`。
6. 所有写入均为 add-only，不删除 `00_待分类` 之外的既有集合成员关系，不修改标题、作者、年份、DOI 和附件。

## 7. 证据矩阵字段

```text
论文 | 挑战映射 | 问题 | 核心假设 | 输入信号 | 方法 | 输出解释粒度 |
Dataset | Baseline | Metrics | 主要结果 | 局限及证据类型 | 证据位置 |
与 PC-STGR/M1/M2 的关系 | Introduction 叙事作用
```

## 8. 停止条件与交付物

满足以下条件后停止扩展检索并开始写作：

1. 每个挑战至少有 3 篇直接相关核心论文和 2 篇边界/反例论文；
2. 三个挑战的主要缺口均能区分“作者明确陈述”“实验未覆盖”和“研究者推断”；
3. 至少分析 5 篇近年 WWW 代表论文的 Introduction；
4. 新增搜索连续两轮不再改变方法分组或核心缺口判断；
5. 已形成 Zotero 证据矩阵、WWW writing-model 卡片和必引/可选引用清单。

最终交付：

- `docs/前人工作证据矩阵_WWW_Introduction.md`；
- `docs/WWW_Introduction写作规律.md`；
- 重写后的 `docs/Introduction_ART叙事版.md`；
- Zotero 新增条目、标签和笔记的核验清单。
