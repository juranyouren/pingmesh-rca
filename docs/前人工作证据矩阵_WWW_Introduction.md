# 前人工作证据矩阵：WWW Introduction

> 更新日期：2026-08-25  
> 研究问题：如何为 Pingmesh 触发的数据中心网络故障，同时完成根因设备排序与证据可回溯的传播路径重构？  
> 使用方式：本文档先固定可由文献支持的事实与缺口边界，再据此撰写 Introduction。`未报告` 表示本轮阅读位置未提供或尚未抽取该字段，不以推测补齐。

## 1. 核心结论

本轮检索支持以下三项论文动机：

1. **Sparse Cases with Dense Information。** 生产故障标签和根因确认依赖专家，真实标注有限；图自监督研究则证明，可以把图内节点、属性和关系本身转化为训练信号。本文可据此为 PC-STGR 设计独立的图内掩码预训练策略，但该策略不替代监督式 PC-STGR。
2. **Multidimensional Evidence with Complex Interactions。** Eadro、DiagFusion、MULAN、Nezha 和 GAMMA 均明确指出，日志、指标、调用链、拓扑或组件状态之间存在异构且相互作用的证据，单一模态、独立建模或简单融合会遗漏故障模式。本文的差异是进一步面向 Pingmesh 场景，将源—目的路径条件、Device–Event 归属和设备内/跨设备时间关系放入同一张图中。
3. **Root-Cause Rankings with Limited Diagnostic Verifiability。** ART、DejaVu、FaultInsight、Nezha 以及图解释研究均把可解释性与工程理解、信任、行动性联系起来。不过，已有“解释”并不等价于本文需要的传播验证：设备排名、特征贡献、历史相似案例、事件模式差异或一般因果图，各自回答的是不同问题。本文 Stage 2 提供外部证据驱动的诊断验证，而不是忠实还原 PC-STGR 的内部推理过程。

因此，Introduction 中最稳妥的总缺口不是“现有工作没有解释性”，而是：

> 现有方法已经能够输出根因排名、细粒度异常模式、指标贡献或因果关系，但这些解释通常没有在事后 Pingmesh case 的观测条件下，同时满足物理拓扑合法、从候选根可达、方向不确定性显式保留以及原始告警/时间证据可回溯。该结论属于“实验未覆盖 + 研究者推断”，不能写成所有相关论文作者的明确结论。

## 2. Survey evidence matrix

| 论文 | 问题 | 核心假设 | 输入信号 | 方法 | Dataset | Baseline | Metrics | 主要结果 | 局限及证据类型 | 证据位置 | 与我的关系 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Pingmesh (SIGCOMM 2015) | 大规模数据中心端到端网络时延测量与故障定位 | 大规模主动探测可持续暴露端到端网络异常 | TCP 探测、源/目的端、网络拓扑及运维信息 | 全互测量基础设施与诊断案例 | 微软生产 DCN | 未报告 | 测量覆盖、开销及案例效果 | 证明 Pingmesh 可作为生产网络异常入口 | **作者明确陈述：** Clos+ECMP 下服务器难以知道 TCP 实际路径，故障 spine 定位并不容易。**实验未覆盖：** 不从事后 case 的告警、拓扑和时序联合重构传播 DAG | §2.1；故障诊断案例 | 本文任务入口与场景依据；说明“探测发现异常”不等于“确定根因与传播过程” |
| R-Pingmesh | RoCE 网络中区分 RNIC 与网内丢包并开展服务感知诊断 | 专门设计的主动探测可补足 RoCE 场景的观测缺口 | RoCE/RNIC 主动探测与服务上下文 | 服务感知探测和故障分类 | 数万张生产 RNIC | 未报告 | 未报告 | 作者报告在大规模生产环境部署 | **实验未覆盖：** 针对 RoCE/RNIC 的专用诊断，不覆盖普通 Pingmesh 事后 case 的通用设备传播重构 | Abstract、Introduction | 网络诊断近邻；用于界定本文并非重新设计探测协议，而是利用已有 case 证据做后验推断 |
| ART (WWW 2025 Industry) | 在微服务生命周期中统一异常检测、故障分类和根因定位 | 三个任务可共享“异常偏离”表征；无标签训练可降低标注和规则成本 | 多模态微服务监控、调用关系、时间依赖 | Transformer/GRU/GraphSAGE 表征 + 无监督任务头 | 生产系统与公开/构造数据，具体字段本轮未统一抽取 | 未报告 | 未报告 | 作者报告统一框架在三个任务上有效 | **作者明确陈述：** 模态依赖复杂、SSL 表征难解释、下游标签稀缺；深度模型的黑盒输出会困扰运维人员。**实验未覆盖：** 不生成物理设备级、根因可达的传播 DAG | Abstract；§1 Introduction，挑战与模块映射 | 最重要的叙事样本：工程流程→三项挑战→模块一一回应；技术上支持标签稀缺、复杂交互和解释性动机 |
| GraphMAE2 (WWW 2023) | 无需人工标签的图表示学习 | 通过遮蔽属性与潜在表示预测，可从图本身产生监督信号 | 通用图的节点属性与结构 | 多视图重遮蔽、潜在表示预测的 masked graph autoencoder | 8 个公开图数据集 | 多种图 SSL 方法 | 节点分类、聚类等 | 作者报告在多个图学习基准上取得有竞争力表现 | **作者明确陈述：** 真实图的充分标签难获得；直接重建输入可能过拟合输入特征，重遮蔽与潜变量预测用于正则化。**实验未覆盖：** 非 AIOps、非 case 级根因排序 | §1 Introduction，pp.1–2；方法动机图 | 支持“把单个 case 内大量节点/边转为自监督约束”的方法依据；不能直接证明该预训练策略对生产 case 有效 |
| Eadro (ICSE 2023) | 基于多源观测联合完成微服务异常检测和根因定位 | 模态专属表示、跨模态融合及依赖图需要联合学习 | 日志、指标、调用链 | 模态专属编码、门控融合、GAT、AD/RCL 联合训练 | 两个微服务基准/系统，具体名称本轮未统一抽取 | 多种单模态及多模态 RCA 方法 | AD 与 RCL 指标 | 作者报告联合建模优于比较方法 | **作者明确陈述：** 多源数据异构、频繁交互且规模大；仅依赖 trace 不足。**实验未覆盖：** 不覆盖 DCN 物理设备、Pingmesh 路径条件和传播方向三状态 | §1 Introduction，pp.1–2 | 直接支持挑战 2；与 PC-STGR 的共同点是图上融合多源信息，差异在场景、图模式与输出 |
| DiagFusion (TSC 2023) | 使用多模态数据进行微服务故障诊断 | 日志、指标和调用链可统一嵌入，并通过依赖图传播故障信息 | 日志、指标、调用链 | 多模态嵌入、数据增强、依赖图与 GNN | 微服务故障数据，具体规模本轮未抽取 | 未报告 | 根因实例与故障类型指标 | 作者报告在根因实例和故障类型诊断上具有鲁棒性 | **作者明确陈述：** 故障会跨组件传播，多源观测需要联合利用。**实验未覆盖：** 输出根因实例/故障类型，不验证物理网络传播路径 | Abstract；§1 Introduction | 支持挑战 2，同时作为“联合多模态不自动得到传播解释”的边界工作 |
| MULAN (WWW 2024) | 多模态微服务因果结构学习与 RCA | 需要同时学习模态不变结构、模态特有结构以及各模态可靠性 | 日志、指标、调用链/多模态观测 | 日志表示、模态特定与共享因果结构、可靠性加权 | 微服务数据，具体规模本轮未统一抽取 | 多种 RCA 与因果学习方法 | RCA 指标 | 作者报告优于比较方法，具体数值本轮未抽取 | **作者明确陈述：** 手工 RCA 昂贵且易错；单模态会遗漏异常，分别处理模态会忽视跨模态相互作用。**实验未覆盖：** 因果结构不是经原始物理边校验的 Pingmesh 传播 DAG | §1 Introduction，pp.1–2；Table 1 动机案例 | 直接支持挑战 2；也是 WWW “三个挑战→四个模块”写法的核心样本 |
| GAMMA (WWW 2024) | 微服务多瓶颈定位 | 瓶颈表现和传播随时间与微服务而变，必须学习复杂服务交互 | 调用/依赖图、服务性能特征 | 可解释图学习与 mixture-of-experts | 微服务应用，具体规模本轮未抽取 | 单/多瓶颈定位方法 | F1 等 | 作者摘要报告相对比较方法获得更高 F1 | **作者明确陈述：** 异步调用、缓存、队列和设计变化造成复杂交互；既有工作多忽略多个同时瓶颈。**实验未覆盖：** 非 DCN 设备告警传播 | §1 Introduction；Abstract | 支持“固定规则难以表达随 case 变化的非线性交互”；提供 WWW 动机案例写法 |
| FaultInsight (KDD 2024) | 超大规模数据中心主机故障诊断与多视角解释 | 异构主机指标需要动态因果建模和分层解释 | 异构 host-level 指标、组件关系与时间变化 | 深度动态因果诊断；指标、组件与传播网络多视角解释 | 数十个生产事故 | SOTA 时间序列因果发现方法 | RCA 准确率、部署性等 | 作者报告优于基线，并获得工程师正面反馈 | **作者明确陈述：** 只处理同构 service KPI 的方法无法为异构 host KPI 提供有用洞察；运维人员需要可解释表示。**实验未覆盖：** 不覆盖 Pingmesh 源—目的条件和设备告警三状态方向。**研究者推断：** 其时间变化因果网络与本文传播 DAG 最接近，但物理网络边约束与证据映射目标不同 | Abstract；§1 Introduction；Motivating Case | 挑战 3 的强证据与最近解释形态之一；写作时必须承认它已输出传播网络，不能泛称前人没有传播图 |
| DejaVu (ESEC/FSE 2022) | 在线服务重复故障的 actionable、interpretable 定位 | 可将本次故障与历史故障的学习表征匹配，并提供局部与全局解释 | KPI/监控指标、组件与历史故障 | GNN/表示学习、故障单元定位、最近历史案例解释 | 3 个生产系统 + TrainTicket；601 个故障，其中 16 个多根因 | 多种故障定位方法 | Top-K、MRR 等 | 作者报告跨系统与长期演化下的定位效果 | **作者明确陈述：** 可行动、可解释结果帮助工程师理解 what/where 并采取缓解措施。**实验未覆盖：** 解释为指标组和相似历史故障，不是基于本次原始告警重构的物理传播路径 | §1；§3；Evaluation Setup，约 p.6 | 直接回答“解释性为何在工程实践重要”；也是必须区分的解释类型 |
| Nezha (ESEC/FSE 2023) | 多模态微服务细粒度、可解释 RCA | 对比正常期与故障期的事件图模式，可定位代码区域或资源类型 | 指标、调用链、日志 | 统一事件表示、事件图构建与模式差异挖掘 | 两个微服务应用 | SOTA RCA 方法 | Top-1 | 平均 Top-1 89.77%（代码区域/资源类型粒度） | **作者明确陈述：** 单模态方法限制根因粒度和解释性。**实验未覆盖：** 事件模式解释不要求物理设备拓扑合法、从候选根可达或形成传播 DAG | Abstract；§1 Introduction | 说明前人已有细粒度解释；本文差异应写成“传播结构与物理证据契约”，而非泛化的“更可解释” |
| NetEventCause | 无拓扑大规模网络中的事件驱动 RCA | 历史告警事件的触发强度能够恢复根告警与派生告警关系 | 告警事件类型与时间；不要求拓扑 | 多变量神经 TPP + attribution | 合成数据 + 真实大规模网络数据（超过 20 万实体） | TPP 与一般 RCA 方法 | 根告警识别、传播链恢复等 | 作者报告优于多数比较方法 | **作者明确陈述：** 面向拓扑缺失、实体规模极大或告警稀疏。**实验未覆盖：** 传播链不受已知物理拓扑/path corridor 约束。**研究者推断：** 事件触发链不能直接替代物理设备传播 DAG | Abstract；方法输入定义 | Stage 2 的重要近邻/边界工作；强调本文利用可用物理拓扑，而非学习无拓扑事件因果 |
| ShapleyIQ (ASPLOS 2023) | 微服务性能调试中的影响量化 | 基于 tracing 的 Shapley value 可量化组件对端到端性能的贡献 | 分布式 tracing | Shapley 值影响量化与性能调试 | TrainTicket 及故障注入；单/多根因实验 | 未报告 | 影响量化/定位指标 | 仓库提供代码与数据以复现实验 | **实验未覆盖：** 输出组件影响/贡献，不重构告警与物理拓扑支持的传播路径。**研究者推断：** attribution 分数与传播链解释是互补而非等价关系 | 论文任务定义；官方复现仓库 README | 挑战 3 的边界方法，用于区分“为什么是该组件”与“故障如何传播” |
| MicroRank (WWW 2021) | 微服务端到端时延异常定位 | 正常/异常 trace 的调用谱差异可为服务排名 | 分布式 trace | 扩展 spectrum analysis 与服务排名 | 微服务系统，具体规模本轮未抽取 | 未报告 | 排名指标 | 作者报告可定位时延问题服务 | **实验未覆盖：** 输出服务排名，未验证设备级物理传播 DAG。**研究者推断：** 高效排名仍需额外结构化证据才能支持网络处置 | Abstract；§1 Introduction | WWW 内的任务近邻与早期排序样本；帮助说明排名结果和传播解释的粒度差异 |
| Adversarial Mask Explainer (WWW 2024) | GNN 实例级解释 | 稀疏且保持预测忠实度的图掩码可以暴露模型决策依据 | 通用图结构与节点特征 | 对抗式稀疏 mask explainer | 通用图基准 | 多种 GNN explainer | Fidelity、Sparsity 等 | 作者报告无需人工 top-K/正则调节的稀疏解释 | **作者明确陈述：** GNN 结构复杂导致决策过程不清；既有 mask 方法依赖人工正则与 top-K。**实验未覆盖：** 解释模型预测所用子图，不保证该子图是工程语义上的故障传播路径 | Abstract；§1 Introduction | 支持挑战 3 的通用黑盒论据；也提醒不能把 attention/mask 直接称为故障传播证据 |
| SEHG (WWW 2025) | 可自解释的异构图神经网络 | 将解释机制融入模型训练可同时优化预测与解释 | 异构图特征与边 | 两阶段训练，学习异构 feature/edge mask | 通用异构图基准 | post-hoc 与 self-explainable 方法 | 预测与解释指标 | 作者报告兼顾预测与解释效果 | **作者明确陈述：** HGNN 是黑盒；post-hoc 解释不改变预测且可能解释次优模型；同构自解释方法不适合异构图。**实验未覆盖：** 不提供 AIOps 传播语义、时间方向或物理拓扑有效性 | Abstract；§1 Introduction | WWW 2025 写作样本；支持解释机制需与任务语义对齐，而非只展示权重 |

## 3. 方法谱系与分组

### 3.1 观测与定位：发现异常不等于解释传播

- Pingmesh、R-Pingmesh 代表主动探测与专用网络诊断。它们证明端到端探测可以发现网络异常，但 ECMP 与内部路径不可见使根因设备定位仍然困难。
- MicroRank、ShapleyIQ 代表基于 trace 的排序或影响量化。它们能回答“哪个服务更可疑/贡献多大”，但输出契约不同于物理设备传播 DAG。
- NetEventCause 能从告警序列中恢复事件传播链，是 Stage 2 的重要近邻；其关键假设是拓扑未知，因此并不使用本文可获得的物理边和 Pingmesh path corridor。

### 3.2 多源异构图学习：共同点是融合，差异在图模式与任务契约

- Eadro、DiagFusion、MULAN、Nezha 均使用或统一日志、指标、调用链等多模态观测。
- GAMMA、FaultInsight 强调组件/指标间复杂且随时间变化的交互。
- PC-STGR 的特定差异不应写成“首次使用图神经网络”，而应写成：面向 Pingmesh case 构造路径条件化 Device–Event 时空异构图，显式保留事件节点、事件归属、设备内/跨设备时间关系，并执行 case 内设备排序。

### 3.3 少标签与自监督：把图内信息转化为训练信号

- ART 明确把标签稀缺作为 AIOps 的工程挑战，并通过无监督框架降低标注依赖。
- GraphMAE2 提供通用图自监督证据：图属性和结构可以构造遮蔽/重建信号，并通过重遮蔽与潜变量预测减少对输入特征的直接过拟合。
- 图内预训练的论文口径应是“利用训练折内 case 的 Device/Event/Edge 构造自监督约束”，而不是把单个 case 的设备节点宣称为更多独立监督样本。

### 3.4 解释性：需要区分五种输出

| 解释形态 | 代表工作 | 能回答的问题 | 不能自动保证的内容 |
|---|---|---|---|
| 根因排名/概率 | MicroRank、Eadro、DiagFusion | 哪个组件最可疑 | 故障如何沿物理设备传播 |
| 特征或组件贡献 | ShapleyIQ、部分 GNN explainer | 哪些输入最影响预测/性能 | 因果方向、根可达性和拓扑合法性 |
| 历史相似案例 | DejaVu | 本次与哪些历史故障相似 | 本次 case 的原始告警传播过程 |
| 事件模式/因果关系 | Nezha、MULAN、NetEventCause、FaultInsight | 哪些事件或指标关联、如何变化 | 在 Pingmesh/DCN 条件下的物理边与路径约束 |
| 证据回溯传播 DAG | 本文 Stage 2 | 根因如何经物理邻接影响观测目标，哪些告警/时间证据支持每条边 | 仍依赖拓扑和观测完整性，需要显式输出 diagnosability |

## 4. 已被证据支持的局限

以下表述可以在 Introduction 中直接引用文献：

1. **生产 RCA 的人工分析和根因标注成本高。** ART、MULAN、DejaVu 等在 Introduction 中明确描述了专家诊断成本或标注稀缺。
2. **单模态或相互独立的多模态建模会遗漏异常模式和跨模态作用。** Eadro、MULAN、Nezha、DiagFusion 均有直接陈述。
3. **异构实体之间的依赖会随时间和故障场景变化，固定规则或单一统计关系难以覆盖。** GAMMA、FaultInsight 直接支持这一点；“固定线性加权不够”是结合本文规则基线的进一步研究者判断。
4. **仅给出黑盒结果会妨碍工程师理解、信任和采取行动。** ART、DejaVu、FaultInsight 直接支持；通用 GNN 解释工作进一步支持图模型决策过程不透明。
5. **ECMP 使事后确定实际内部路径和故障设备困难。** Pingmesh 的网络场景论述可直接支持。

## 5. 尚未验证的缺口假设

以下内容只能标记为“实验未覆盖”或“研究者推断”，不能写成前人作者的一致结论：

1. **现有 RCA 方法普遍不能生成传播路径。** 这一说法过强；FaultInsight 与 NetEventCause 已输出传播网络/事件链。可改为：它们未在本文观测设定下验证物理拓扑合法且证据回溯的根因条件传播 DAG。
2. **三状态概率是解决方向不确定性的最佳方式。** 目前是本文设计 insight，需要通过 Stage 2 边概率消融和路径标注实验验证，不能由现有文献直接推出。
3. **传播解释一定会提高根因准确率。** 这是待验证的实验主张。若 Stage 2 只提升解释性而没有稳定改善排名，也应如实报告。
4. **PC-STGR 的图内预训练一定缓解过拟合。** GraphMAE2 与 ART 只提供机制可行性，本文仍需 grouped OOF、学习曲线及有无预训练的对照。
5. **所有输出物理边都是真实 L1 传播边。** 当前实现只能保证边来自 `task_topo.links` 并有 topology edge ID，尚未与独立物理资源台账交叉核验。

## 6. 相互冲突的结果

- 暂未发现直接否定“多源联合建模有益”或“解释性有工程价值”的核心论文。
- 文献对“解释”的定义并不一致：DejaVu 强调 actionable 历史案例和指标组，Nezha 强调正常/故障事件模式差异，FaultInsight 强调多层次动态因果视图，通用图解释器强调 fidelity/sparsity。本文不能把这些指标横向等同。
- 无监督、自监督和监督方法使用的数据、标签粒度及场景差异大，不能用其他论文的性能数字推断 PC-STGR 图内预训练的收益。

## 7. 检索盲区

1. 仍需在最终 Related Work 阶段补充网络层析、网络 provenance 和多路径故障定位的系统论文，以检查是否已有与“物理传播 DAG + 原始证据映射”更接近的工作。
2. 本轮 WWW 写作样本以图学习、RCA 和解释性为主，并非 WWW 全体论文的统计样本；提炼的是该子社区的共同写法。
3. 部分论文的完整 Dataset、Baseline 和全部 Metrics 尚未做实验复现级抽取，表中以 `未报告` 或“本轮未抽取”标识。
4. 2026 年新近工作仍可能改变最近邻判断，投稿前需要用相同查询族做一次增量检索。

## 8. 必引论文

- 场景与任务：Pingmesh。
- 叙事与统一 AIOps 参照：ART。
- 少标签/图自监督：GraphMAE2（以及基础 GraphMAE，若方法部分需要追溯）。
- 多源复杂交互：Eadro、MULAN、DiagFusion，三者按篇幅择二至三篇。
- 可解释 RCA 近邻：DejaVu、Nezha、FaultInsight。
- 事件传播链近邻：NetEventCause。

## 9. 可选引用

- GAMMA：用于强调多瓶颈与服务交互复杂性，也可作为 WWW Introduction 写作样本。
- MicroRank：用于 WWW 内微服务定位方法谱系。
- ShapleyIQ：用于区分影响量化与传播重构。
- Adversarial Mask Explainer、SEHG：用于解释通用 GNN 黑盒问题；若 Introduction 篇幅紧，可移至 Related Work。
- R-Pingmesh：用于说明主动测量在 RoCE/RNIC 场景的扩展，不必作为本文最核心近邻。

## 10. 本轮核验的主要来源

- [GraphMAE2 作者公开版](https://keg.cs.tsinghua.edu.cn/jietang/publications/WWW23-Hou-GraphMAE2.pdf)
- [MULAN 作者公开版](https://zhengzhangchen.github.io/publication/MULAN_WWW24.pdf)
- [GAMMA 作者公开版](https://www3.cs.stonybrook.edu/~anshul/www24_gamma.pdf)
- [Adversarial Mask Explainer（OpenReview）](https://openreview.net/forum?id=DJttojBfnX)
- [SEHG（OpenReview）](https://openreview.net/pdf?id=gfqM0MyzLn)
- [Eadro 作者公开版](https://zbchern.github.io/papers/icse23c.pdf)
- [DiagFusion 作者公开版](https://nkcs.iops.ai/wp-content/uploads/2025/09/Robust_Failure_Diagnosis_of_Microservice_System_Through_Multimodal_Data.pdf)
- [DejaVu 作者公开版](https://netman.aiops.org/wp-content/uploads/2022/11/DejaVu-paper.pdf)
- [Nezha 作者公开版](https://www.aiops.cn/gitlab/aiops-nankai/model/nezha/-/raw/7cd85ba6ea6983a02c14878a94afdcd195c8c07a/FSE2023_Nezha.pdf?inline=false)
- [FaultInsight 机构出版记录](https://scholars.mssm.edu/en/publications/faultinsight-interpreting-hyperscale-data-center-host-faults/)
- [ShapleyIQ 官方复现仓库](https://github.com/lonyle/ShapleyIQ)
- [NetEventCause 摘要与出版记录](https://pubmed.ncbi.nlm.nih.gov/40471725/)
