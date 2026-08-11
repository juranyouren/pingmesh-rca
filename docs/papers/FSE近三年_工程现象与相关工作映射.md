# FSE 近三年文献与 Pingmesh 工程现象映射

更新日期：2026-07-14

## 1. 结论先行

本文最合适的 Related Work 不是按“告警、拓扑、LLM”罗列关键词，而是按三项工程挑战组织三类方法：

1. **拓扑、时序与因果传播方法**：对应“ECMP 路径不确定、故障级联、告警漂移”。
2. **证据裁剪、告警压缩与多模态融合方法**：对应“单设备数百至上千条异构事件、上下文膨胀和信号稀释”。
3. **LLM/Agent 与置信度辅助诊断方法**：对应“故障要求及时定位，但复杂语义推理增加时延且可能误判”。

这样组织后，论证链是闭合的：

| 工程现象 | 现有方法最接近的能力 | 尚未覆盖的 Pingmesh 条件 | 本文需要的能力 |
|---|---|---|---|
| source/sink 已知，但 ECMP 下真实路径未知；故障沿拓扑级联；告警存在漂移 | 路径约束、事件图、因果图、变点检测、多时滞建模 | 服务调用图或 trace 不等于实际转发路径；设备事件稀疏异步；症状设备可能比根因更显著 | incident-conditioned 可行路径支持 + 抗告警量偏差的相对时序 |
| 单设备 P99 为 1,177.46 条事件、约 9,988.65 token，最大约 10,046 token | 图裁剪、告警汇总、日志抽取、事件规范化、多模态融合 | 压缩目标通常不保证保留物理端口、链路、source/sink 可达性与来源指针；误剪会丢根因 | 确定性去重与证据预算 + Top-K 来源保持压缩 |
| 网络异常定位越慢，缓解越晚；全量复杂推理又增加时延 | LLM agent、层次推理、置信校准、early stop | 多数方法仍对每个 case 启动昂贵流程；置信度未直接转化为绕过、升级和拒判策略 | 基于拓扑—时序证据的选择性路由与 abstention |

## 2. FSE 近三年重点文献

这里以当前已完成的 FSE 2024--2026 为“近三年”，另补充两篇高度相关的 ESEC/FSE 2023 工作作为直接前序。Research、Industry 和 Companion track 分开标注，避免把 Companion/Industry 误写成主会 Research paper。

### 2.1 直接支撑“时空传播复杂性”的工作

| 文献 | 方法要点 | 对本文可迁移的思想 | 对 Pingmesh 的剩余缺口 |
|---|---|---|---|
| **Nezha**, ESEC/FSE 2023 Research, DOI [10.1145/3611643.3616249](https://doi.org/10.1145/3611643.3616249) | 将 metrics、traces、logs 转成统一事件，比较正常/故障阶段的事件图模式，定位到代码区域和资源类型 | 多模态证据应先规范化成可比较事件；传播模式比单条异常更有解释力 | 依赖微服务阶段对比和事件图；没有处理 ECMP 下实际物理路径不可见，也不保证告警采集延迟下的设备因果方向 |
| **BARO**, FSE 2024 Research, DOI [10.1145/3660805](https://doi.org/10.1145/3660805) | 用多变量 Bayesian online change-point detection 估计异常时间，再以稳健非参数检验排序根因指标 | 不能盲信外部异常时间；定位器应对检测时间误差鲁棒 | 输入是密集、规则采样的多变量指标；Pingmesh 主要是稀疏设备事件和拓扑，且根因对象是物理设备而非异常指标 |
| **Chain-of-Event**, FSE 2024 Industry/Companion, DOI [10.1145/3663529.3663827](https://doi.org/10.1145/3663529.3663827) | 自动学习带权事件因果图，用符合 SRE 经验的参数解释多模态故障链 | 应显式区分传播链上的原因事件和派生事件，并保留可解释参数 | 依赖历史 incident 学习稳定事件因果关系；新型/低频设备告警和未知 ECMP 路径会削弱可识别性 |
| **ProAlert**, FSE 2025 Research, DOI [10.1145/3729367](https://doi.org/10.1145/3729367) | 从历史告警和系统拓扑无监督学习传播模式，在线验证故障传播路径并汇总 incident | 仅看拓扑连通性不足，必须验证路径语义；传播路径可用于解释 | 任务目标是告警/incident 汇总，不是物理根因设备排序；需要历史传播模式，且服务拓扑路径不等于 ECMP 实际转发路径 |
| **LagRCA**, FSE 2026 Industry, [官方页面](https://conf.researchr.org/details/fse-2026/fse-2026-industry-papers/18/Bridging-the-Delay-Lag-Aware-Spatio-Temporal-Causal-Inference-for-Microservice-Root-) | 学习多时滞因果图与时空表示，并扣除可由上游解释的下游异常，避免高排症状节点 | 这是与“故障级联 + 告警漂移”最直接的近期证据：同步窗口会错配原因和症状，应建模异质传播时滞 | 论文使用 trace 恢复调用拓扑，并依赖固定间隔 metrics；明确将 logs 留待未来。Pingmesh 没有请求级 trace 和密集 KPI，只能从物理可行路径与稀疏事件构造弱传播证据 |
| **TORAI**, FSE 2026 Research, DOI [10.1145/3808137](https://doi.org/10.1145/3808137), [官方页面](https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/64/TORAI-Multi-Source-Root-Cause-Analysis-for-Blind-Spots-in-the-Microservice-Service-C) | 在服务调用图存在 blind spots 时，用多源异常严重度、症状聚类、因果排序和假设检验做无监督细粒度 RCA | 观测图不完整时不应把不可见节点直接排除；多源证据可以在缺图条件下辅助定位 | 聚类和因果分析仍基于微服务 telemetry 分布；物理网络中 ECMP 的问题不是简单“缺一条服务边”，而是多条同等可行路径不可区分 |
| **MetaRCA**, FSE 2026 Research, DOI [10.1145/3797069](https://doi.org/10.1145/3797069) | 离线融合 LLM、历史报告和观测构建元因果图，在线按当前上下文实例化、加权和剪枝 | 可把稳定领域知识放到离线阶段，在线只实例化局部因果结构，以改善扩展性 | 仍要求元因果知识和当前系统实体能可靠映射；Pingmesh 的物理告警、端点条件和 ECMP 可行路径需要专门的网络约束，不能直接复用服务级元图 |
| **Fang et al.**, FSE 2026 Research, DOI [10.1145/3797100](https://doi.org/10.1145/3797100), [官方页面](https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/171/Rethinking-the-Evaluation-of-Microservice-RCA-with-a-Fault-Propagation-Aware-Benchmar) | 构造更现实的故障传播感知 benchmark；11 个 SOTA 模型在现实数据上平均 Top-1 仅 0.21、最好 0.37，并出现扩展性、观测盲区和建模瓶颈 | 评价必须包含真实传播、动态负载、观测盲区和执行时间，不能只在过度简化的注入数据上报告准确率 | 本文也必须报告 case 级覆盖率、Top-K、时延/token 和拒判，而不能只给 Top-1；内部数据上的结论还需跨场景或公开基准验证 |

### 2.2 直接支撑“证据冗余与压缩”的工作

| 文献 | 方法要点 | 对本文可迁移的思想 | 对 Pingmesh 的剩余缺口 |
|---|---|---|---|
| **TraceDiag**, ESEC/FSE 2023 Industry, DOI [10.1145/3611643.3613864](https://doi.org/10.1145/3611643.3613864) | 用强化学习学习服务依赖图裁剪策略，再在小图上运行因果 RCA | 先缩小候选空间可显著降低后续推理成本；裁剪策略应可解释并随 case 调整 | 其裁剪依赖服务 trace/依赖图。Pingmesh 直接剪成很小 Top-K 时可能把安静根因设备删掉，因此必须以高候选召回率为硬约束 |
| **Nezha**, ESEC/FSE 2023 Research | 将异构 telemetry 规范化为统一事件，再挖掘事件模式 | 语义压缩前先做结构化规范化，避免把全部原文直接交给模型 | 事件模式压缩不天然保留物理端口、链路状态和原始来源，需要为网络证据另设保留规则 |
| **ProAlert**, FSE 2025 Research | 将大量告警沿验证后的传播路径汇总为 incident | 压缩应利用空间结构和传播一致性，而不只是文本相似度或时间窗口 | incident summarization 不能自动推出根因设备；同一 incident 内仍需设备级归因 |
| **L4**, FSE 2025 Industry/Companion, DOI [10.1145/3696630.3728531](https://doi.org/10.1145/3696630.3728531) | 利用跨作业、空间和时间模式，从大规模训练日志中提取故障指示事件、节点、阶段与迭代 | 面对“海量原始日志、少量有效线索”，应先提取诊断最小充分信息；论文的工业数据也显示日志筛选是主要人工瓶颈 | L4 的模式与大模型分布式训练阶段/并行结构绑定，不能直接泛化到交换机告警；且其目标不是在 ECMP 拓扑中区分根因与受害设备 |
| **TORAI**, FSE 2026 Research | 将可用 metrics、logs、traces 转换后做症状聚类、因果排序和细粒度检验 | 多源数据可先由专门统计模块处理，再融合排名 | 即使不要求完整调用图，仍需对每种 telemetry 构造稳定异常度；Pingmesh 告警文本、拓扑属性和 source/sink 约束的语义不同 |

这一类工作的统一缺口不是“没有压缩”，而是**压缩目标与本文的最终决策不一致**：

- 告警聚合优化“哪些告警属于同一 incident”，不等价于“哪个物理设备是根因”。
- 日志抽取优化“哪些行与故障有关”，不保证保留可证明设备归属的端口、链路和端点路径信息。
- 图裁剪优化计算量，但错误裁剪具有不可恢复性；本文本地实验也曾出现根因被剪出候选集的现象。
- 单设备最大输入已约 10,046 token；当多个候选设备联合推理时，不能把每台设备的完整证据串联后再依赖 LLM 自行筛选。

因此本文的 SECL 应写成 **evidence canonicalization and budgeting**，而不只是“LLM summarization”：

1. 告警按类型/接口/时间去重；
2. 强制保留最早事件、最高严重度、physical-link-down/端口状态、source/sink 路径关系和来源指针；
3. 对每设备与每 case 设证据预算；
4. 仅对 DDFL 产生的 Top-K 候选做可选语义压缩；
5. 用关键证据召回率、压缩率、token/时延以及 Top-K non-inferiority 评价，而不是只评价摘要可读性。

### 2.3 直接支撑“即时诊断与复杂推理张力”的工作

| 文献 | 方法要点 | 对本文可迁移的思想 | 对 Pingmesh 的剩余缺口 |
|---|---|---|---|
| **LM-PACE**, FSE 2024 Industry/Companion, DOI [10.1145/3663529.3663858](https://doi.org/10.1145/3663529.3663858) | 通过历史 incident 检索、两阶段提示和可学习变换，为 LLM 根因建议输出校准置信度 | 自动 RCA 需要可校准的可信度，而不是只给无依据的答案 | 它评估的是已有 LLM 建议是否可信，并不生成基于网络证据的路由策略；检索和二次 LLM 评分本身也有成本，且依赖大规模历史 incident |
| **X-Lifecycle Learning**, FSE 2024 Industry/Companion, [arXiv:2404.03662](https://arxiv.org/abs/2404.03662) | 将代码、配置、监控、服务属性、依赖和排障文档等跨生命周期上下文提供给 LLM | 只看单一数据源会漏因果背景；上下文应围绕当前任务检索 | “加入更多上下文”会与本文的 token 膨胀直接冲突；需要先证明每类上下文的边际诊断价值，再决定是否加入 |
| **LLM Agents for AIOps in Kubernetes**, FSE 2026 Industry, [官方页面](https://conf.researchr.org/details/fse-2026/fse-2026-industry-papers/38/LLM-Agents-for-AIOps-in-Kubernetes-An-Industrial-Experience-Report-with-Red-Hat-Open) | 在 Red Hat OpenShift 中把预测模型与 tool-augmented LLM agent 结合，报告生产 AIOps 的能力与局限 | LLM 更适合调用专用工具和解释结构化结果，而不是直接替代底层定位算法 | Kubernetes 运维工具和网络设备证据不同；agent 多轮工具调用带来可变时延，仍需外部路由与终止条件 |
| **Aloha**, FSE 2026 Industry, [官方页面](https://conf.researchr.org/details/fse-2026/fse-2026-industry-papers/39/Aloha-Localizing-Batch-Failures-in-Large-scale-Cloud-Systems-via-Contrast-Analysis-a) | 用对比分析和 human-in-the-loop agent 定位批量故障模式 | 大规模故障可先用轻量对比找共性，再让 agent/人处理复杂部分 | 面向同一 subject 的批量实例故障，不解决单个 Pingmesh case 的 ECMP 路径归因；其定位结果仍需要人工闭环 |

这一类的统一缺口是：**accuracy/certainty 优化尚未变成一个端到端的成本敏感决策策略**。

- 置信估计回答“模型建议看起来多可信”，但不必然回答“当前 case 是否值得调用模型”。
- 多数 agent 系统对每个 case 都执行检索、摘要、工具调用或多轮推理，成本随证据量和迭代次数增长。
- 历史 incident、SOP 和丰富监控工具可以提高 LLM 表现，但本文 Pingmesh case 的可用知识和观测更受限。
- 复杂 LLM workflow 可能选择任意证据、混淆 provenance 或在多跳传播中错误更新信念。

因此本文 SRCL 的差异点应写成：**用确定性的 topology-temporal evidence quality 决定是否调用 LLM，而不是再用一个 LLM 判断另一个 LLM 是否可信**。输出至少包含三路：

1. 高置信且拓扑/时序一致：绕过 LLM，直接返回排序与证据；
2. Top-1/Top-2 接近或拓扑/时序冲突：调用 LLM 做受约束仲裁；
3. 候选召回不足或证据不可识别：abstain，交给人工或请求新观测。

## 3. 其他直接相关文献

### 3.1 网络与告警场景

- **Pingmesh: A Large-Scale System for Data Center Network Latency Measurement and Analysis**, SIGCOMM 2015。建立端到端网状测量背景，但异常端点对并不直接给出根因设备。
- **NetEventCause: Event-Driven Root Cause Analysis for Large Network System Without Topology**, IEEE TNNLS 2025。用连续时间 point process 和 attribution 恢复事件依赖；优点是利用相对时间贡献，缺点是依赖长期重复历史和稳定事件类型，且事件因果不等于物理路径归属。
- **Knowledge-aware Alert Aggregation in Large-scale Cloud Systems: A Hybrid Approach (COLA)**, ICSE-SEIP 2024。高置信告警对由统计模块处理，低置信样本交给 LLM；这是本文“选择性推理”最接近的范式，但其输出是告警对聚合，不是根因设备排序。
- **SkyNet: Analyzing Alert Flooding from Severe Network Failures in Large Cloud Infrastructures**, SIGCOMM 2025, DOI [10.1145/3718958.3750536](https://doi.org/10.1145/3718958.3750536)。联合时间、位置和多监控源分析告警洪流；适合支撑“告警洪流与及时缓解”，但 scope/severity 或告警热点不是根因设备。
- **Towards LLM-Based Failure Localization in Production-Scale Networks (BiAn)**, SIGCOMM 2025, DOI [10.1145/3718958.3750505](https://doi.org/10.1145/3718958.3750505)。用分层摘要、逐设备分析、拓扑/时间线、多模型和 early stop 辅助网络设备定位，是最接近本文的 LLM baseline。其优势依赖丰富监控工具、SOP 和历史 incident；本文本地全量 LLM 重排未优于确定性排序，因此应把 LLM 限制为冲突仲裁器。
- **Stalled, Biased, and Confused: Uncovering Reasoning Failures in LLMs for Cloud-Based Root Cause Analysis**, FORGE 2026, DOI [10.1145/3793655.3793732](https://doi.org/10.1145/3793655.3793732)。在 48,000 个模拟场景中总结 16 类 RCA 推理失败，支持 provenance-preserving evidence、门控和拒判设计。

### 3.2 微服务多模态与 LLM RCA

- **Eadro: An End-to-End Troubleshooting Framework for Microservices on Multi-source Data**, ICSE 2023。联合 traces、logs、KPIs 和多任务学习，说明多源融合有效，但依赖服务级多源 telemetry 和训练分布。
- **Automatic Root Cause Analysis via Large Language Models for Cloud Incidents (RCACopilot)**, EuroSys 2024。按告警类型选择 handler，聚合诊断信息并用 LLM 预测根因类别和解释；其任务主要是 incident report/category，不是物理设备路径归因。
- **TAMO: Fine-Grained Root Cause Analysis via Tool-Assisted LLM Agent with Multi-Modality Observation Data in Cloud-Native Systems**, IEEE TSC 2025。用专用多模态对齐、定位和分类工具约束 LLM，支持“算法先编译证据、LLM 后组织推理”。
- **OpenRCA: Can Large Language Models Locate the Root Cause of Software Failures?**, ICLR 2025。说明真实软件故障上的长上下文、多模态和执行式推理仍很困难，可作为限制 LLM 权限的反向证据。
- **FoundRoot: Towards Foundation Model for Root Cause Analysis via Structured Deep Thinking**, ICSE 2026。将 RCA 分解为结构化推理子步骤并通过 SFT+RL 训练；它改善 zero-shot RCA，但也说明面对大量指标时需要额外训练和更长的结构化推理链，而不是零成本获得能力。

## 4. 可直接用于论文的 Related Work 三段

### 4.1 Spatio-temporal and causal localization

Recent RCA methods combine topology, event dependencies, and temporal changes to recover fault propagation. Nezha and Chain-of-Event construct event graphs from multi-modal telemetry, BARO improves robustness to anomaly-time estimation, and ProAlert validates alert propagation paths rather than relying on topology connectivity alone. The latest LagRCA explicitly models heterogeneous propagation lags, while TORAI and MetaRCA address missing call-graph observations and cross-system causal generalization. These advances establish that topology and time must be modeled jointly. However, they predominantly assume service call traces, dense aligned metrics, or reusable historical propagation patterns. A Pingmesh incident exposes only the affected endpoint pair, physical topology, and sparse asynchronous device events; under ECMP, the service/path relation is a set of feasible forwarding paths rather than an observed execution trace. Consequently, correlation or propagation salience can still favor downstream symptom devices. This setting requires incident-conditioned feasible-path support cross-validated by volume-robust relative timing.

### 4.2 Evidence reduction and multi-modal fusion

Existing systems reduce diagnostic scale through graph pruning, alert summarization, log extraction, event canonicalization, or multi-modal fusion. TraceDiag learns to prune service dependency graphs, ProAlert groups alerts along validated propagation paths, L4 extracts failure-indicating records from massive training logs, and TORAI transforms available telemetry before clustering and causal ranking. These methods reduce data volume, but their reduction objectives do not guarantee preservation of the physical-port, link-state, endpoint-reachability, timestamp, and provenance evidence required for Pingmesh device localization. Aggressive pruning is particularly risky because a quiet root device may be removed before semantic reasoning. Since a single device can contribute nearly 10k input tokens in our dataset, evidence must be canonicalized and budgeted before LLM invocation, with critical-evidence recall and ranking non-inferiority treated as constraints.

### 4.3 Trustworthy and timely LLM-assisted RCA

LLM-assisted RCA systems use retrieval, hierarchical reasoning, tool invocation, and confidence estimation to organize operational evidence. LM-PACE calibrates confidence in LLM root-cause recommendations, while RCACopilot and recent AIOps agents combine LLMs with diagnostic handlers or tools. BiAn further employs model specialization, parallelism, and early stopping for production-scale network localization. Nevertheless, most pipelines still launch retrieval or multi-stage semantic reasoning for every incident, and confidence estimation alone does not define when to bypass an LLM, escalate a conflict, or abstain under insufficient evidence. Empirical benchmarks and reasoning-failure studies also show that realistic propagation, observability blind spots, and provenance confusion remain difficult. We therefore use deterministic topology-temporal evidence quality as a routing signal: high-confidence cases bypass the LLM, conflicting cases receive constrained semantic arbitration, and non-identifiable cases are rejected for human review.

## 5. INTRO 中建议使用的中文压缩版

> 现有根因定位方法主要分为三类。第一类联合拓扑、时序或因果关系恢复故障传播链。近年的 Nezha、BARO、ProAlert、LagRCA、TORAI 和 MetaRCA 已分别从多模态事件图、变点鲁棒性、传播路径、多时滞建模、观测盲区和跨系统泛化方面推进了该方向。然而，这些方法通常依赖服务调用 trace、密集指标序列或稳定历史传播模式；在 Pingmesh 仅提供异常端点、物理拓扑和稀疏设备事件且 ECMP 实际路径不可见时，仍可能把异常显著的下游设备误作根因。第二类通过图裁剪、告警汇总、日志抽取或多模态融合减少诊断规模，但其压缩目标通常不保证保留物理端口、链路、端点可达性和原始来源，激进裁剪还可能提前移除安静根因。第三类用 LLM/agent、工具调用和置信估计组织语义证据，但全量多阶段推理增加时延，且置信分并未自动给出绕过、升级和拒判策略。上述缺口共同要求一种面向 Pingmesh 的选择性定位框架：先以可行路径和相对时序产生确定性候选，再以来源保持的预算化证据处理语义，最后只在证据冲突时调用 LLM，并在不可识别时拒判。

## 6. 引用注意事项

1. 不要把 ProAlert 写成“根因设备定位方法”；它的直接任务是 alert/incident summarization，传播路径用于提升汇总与解释。
2. 不要声称“现有方法都忽略时间漂移”。FSE 2026 LagRCA 已明确处理 heterogeneous multi-lag propagation。正确缺口是它依赖 trace-derived call topology 和 dense metrics，而 Pingmesh 是未知 ECMP 路径上的稀疏设备事件。
3. 不要把 FSE Companion/Industry papers 写成 FSE Research papers。LM-PACE、Chain-of-Event、L4、LagRCA 应标明 track。
4. 不要把“相关”写成“因果”。告警共现、point-process attribution、PageRank 和事件图只能提供候选支持，除非观测中存在可验证的实际传播或 intervention。
5. 不要把单设备最大约 10k token 写成“整个 case 只有 10k token”。这是单设备规模；跨设备联合推理的总输入会更大，但应另行实测后报告。
6. 诊断时延应报告端到端 P50/P95、LLM 调用率、token 和 coverage-risk，而不只报告平均推理时间。
