# 相关工作：三类方法与缺口（INFOCOM 版本）

更新日期：2026-07-11

> **状态说明（2026-08-28）：** 本文档按旧的“设备根因定位”问题整理，保留为
> 文献素材，不再直接代表论文任务定义。当前论文以
> [`../论文方案.md`](../论文方案.md) 为准：先由 PC-STGR 输出根因 Top-K，再由
> P0在候选根因条件下恢复设备传播 DAG。下文涉及“映射为根因”“设备定位”的缺口，
> 后续写作时需改写为“局部事件/拓扑证据为何不足以恢复全局传播图”。

## 1. 分类原则

本文不按“告警、拓扑、LLM”三个关键词机械分类，而按每类方法如何把观测映射为根因来分类：

1. **事件依赖方法**：从告警共现、时间激励或语义知识推断事件关系。
2. **路径约束方法**：用端到端路径结果、真实 provenance 或工作负载结构约束内部故障位置。
3. **知识/语义推理方法**：用因果图、专用工具或 LLM 组织多源证据并输出根因。

探测或监控系统不单独作为“现有方法缺口”。只有当其方法思想确实能缓解本文问题时，才分析将该思想迁移到既有 Pingmesh 数据时缺少什么观测或违反什么假设。

## 2. 第一类：事件依赖与告警相关方法

### 2.1 COLA（ICSE-SEIP 2024）

**方法。** COLA 先用相关性挖掘捕获告警对的时空关系，高置信告警对由轻量模块处理；只有低置信告警对才交给 LLM。LLM 通过 SOP 获得告警触发条件、影响、潜在根因和处置知识，并通过多轮提示压缩长 SOP。任务输出是告警对是否应被聚合。其生产数据包含约 50 万条告警和 3000 份 SOP，报告 F1 0.901-0.930。

**对本文有用的思想。** 轻量统计处理常见模式，昂贵语义推理只处理不确定样本。这直接支持本文的 selective reasoning 设计。

**直接用于 Pingmesh 设备定位为何不成立。** 告警对相关并不提供根因设备排序。一个下游症状设备可以因告警种类多、重复次数高而与大量事件相关；一个物理根因设备可能只产生一条端口 down 告警。SOP 能解释两个告警在语义上为何相关，但不能证明相应设备位于当前 source-sink 的可行受影响路径。本文应迁移 COLA 的“置信分流”，不能把告警聚合结果直接等价为物理根因。

### 2.2 NetEventCause / NEC（TNNLS 2025）

**方法。** NEC 在拓扑未知时，把告警类型和实体类型的组合作为多元事件类型，用连续时间神经 temporal point process 预测给定历史事件后的条件强度。它比较先验强度与历史贡献来识别 root alarm，再用 attribution method 计算历史事件对后续事件强度的贡献，恢复导出告警的 causative alarm 集合。真实数据来自管理 20 万以上实体的平台，训练历史为 2021-2022，测试为 2023。

**对本文有用的思想。** 原始时间戳不仅可用于“谁最早”，还可用于估计一个事件对后续事件的增量解释力；相对 onset 比窗口内事件数量更接近传播证据。

**直接用于本文为何不成立。** NEC 的统计关系依赖长期重复历史和稳定的事件类型。论文明确指出其对新告警类型无效，并建议引入日志文本或其他模态。本文只有 159 个生产 case，低频故障和长尾告警难以支持高维 TPP；更重要的是，条件强度与 attribution 仍可能把共同受同一隐藏故障影响的两个症状告警连接起来。没有物理路径约束时，它恢复的是事件传播解释，不是当前故障的物理设备归属。

### 2.3 SkyNet（SIGCOMM 2025）

**方法。** SkyNet 将多种监控源统一成包含时间、位置和类型的告警记录，按时间与网络位置构建层次告警树，把告警分组为 incident；随后按流量、用户影响和持续时间评估严重度，并调用不同遥测工具逐层缩小位置。它强调输出故障范围和严重度，生产部署一年半后用于缩短 mitigation time。

**对本文有用的思想。** 网络位置层次可以过滤跨区域噪声，时间与位置应联合使用，且原始告警应先规范化、去重和保留来源。

**直接用于本文为何不成立。** 时间-位置聚类只能说明哪些告警可能属于同一 incident。层次树中的热点位置可能是受影响范围或流量汇聚点，而非故障起点。SkyNet 自身也指出“把第一条告警视为根因”并不可靠，因为网络行为可能先异常，根因设备日志随后才出现。本文必须在聚类之后进一步验证设备对当前 source-sink 可行路径的解释能力，并用相对时序而非单一 earliest event 判断因果方向。

### 2.4 本类的统一缺口

可在 INTRO 中压缩为三点：

- **量偏差**：症状设备的事件量和相关边可能多于安静的根因设备。
- **历史依赖**：低频、首次出现或告警类型演化会削弱共现/TPP 模式。
- **物理归属缺失**：事件相关不能证明设备位于当前端点对的可行影响路径。

因此，本文不是否定事件相关，而是把它降为路径约束下的时间辅助证据。

## 3. 第二类：路径、拓扑与 provenance 约束方法

### 3.1 PROTON（INFOCOM 2023）

**方法。** 在初始节点/链路状态未知、监控预算有限和路由不可控的条件下，PROTON 用 Boolean Network Tomography 根据工作/失败路径更新近似失效概率，再按期望修复代价、路径容量和需求恢复收益安排修复与新监控点。

**可迁移思想。** 端到端失败只形成路径内部元素的概率支持；路径必须服从现实路由；不确定性应进入后续决策。

**迁移障碍。** PROTON 可反复主动探测并通过修复改变下一轮观测，本文只有一次事件后的固定被动证据；其二值路径状态也不能完整描述 ECMP 与灰故障。

### 3.2 D2NeT（INFOCOM 2025）

**方法。** 多个监控点根据 path-probe utility 和 information-exchange utility 贪心选择下一次交互，用 failure centrality 近似内部节点后验，并通过新旧证据一致性检查跟踪动态失败/恢复。论文还显式评价 rank、uncertainty 和最差监控点，而不只评价是否命中。

**可迁移思想。** 设备分数应表达其能解释多少尚未解释的异常路径；观测不足时应输出可诊断性/不确定性；时间证据可用于冲突更新。

**迁移障碍。** D2NeT 能主动选择下一条探测路径并假设绕路常导致可检测额外时延；既有 Pingmesh case 不能创造新观测，等价 ECMP 绕路也可能没有明显额外时延。

### 3.3 Hawkeye（SIGCOMM 2025）

**方法。** Hawkeye 通过 PFC-aware programmable telemetry 记录 PFC 对流的细粒度影响，在数据平面追踪 PFC 因果关系，最后用 provenance breakdown 定位 RDMA 性能异常的类型和根因。测试报告超过 90% precision，并显著降低追踪开销。

**可迁移思想。** 对级联异常，最强证据不是一般物理邻接，而是能够说明“哪个设备的哪次行为影响了哪条流”的 provenance。

**迁移障碍。** 普通 Pingmesh 数据没有 PFC 因果遥测，也没有逐包记录故障传播边。若只在 Clos 物理图上运行 PageRank，不能获得 Hawkeye 意义上的 provenance。本文可以用端点与可行路径构造弱 provenance 支持，但必须明确它是候选约束，不是实际因果链追踪。

### 3.4 SkeletonHunter（SIGCOMM 2025）

**方法。** SkeletonHunter 利用大模型训练流量规律且稀疏的特性，推断一组持续被训练流量经过的关键路径，即 traffic skeleton；在该结构上执行快速检测和定位。生产部署六个月，报告定位准确率 95.7%。

**可迁移思想。** 先找出与当前工作负载稳定相关的关键路径结构，再定位设备，可以显著缩小全网候选空间。

**迁移障碍。** traffic skeleton 依赖集合通信和训练业务的规律流量；普通 Pingmesh case 不具备相同工作负载结构。本文应从 source、sink 与 ECMP 可达性构造 incident-specific corridor，而不是假设存在可重复训练骨架。

### 3.5 Canary（TNSM 2024，作为边界证据）

**方法。** Canary 在可编程交换机上选择部分大流监测，并把实际经过的路径编码到包头，从而比较上下游观测并定位 silent drop/corruption 链路。

**可迁移思想。** 如果观测中存在真实逐包路径，ECMP 歧义可以大幅消除。

**迁移障碍。** 本文部署条件没有包头路径编码和 P4 上下游计数。Canary 因此不应被写成本文必须优于的 RCA baseline；它适合用来说明本文为何只能在可行路径集合上做被动推断，并在观测不可识别时 abstain。

### 3.6 本类的统一缺口

这类方法给出本文最重要的正向原则：**根因设备必须解释受影响路径，而不仅是全图中心或告警热点。** 其迁移缺口集中在：

- 现有方法通常能主动选择/重复路径观测，本文只能处理固定事后证据；
- 专用系统拥有真实 provenance、逐包路径或规律流量骨架，普通 Pingmesh case 没有；
- 二值路径假设无法充分覆盖 ECMP、等价绕路与灰故障。

因此第一模块应做事件条件化的可行路径支持，而不是把物理 PageRank 包装成因果传播。

## 4. 第三类：因果图、专用工具与 LLM 辅助 RCA

### 4.1 NRCAC（INFOCOM 2025）

**方法。** 公开摘要显示，NRCAC 用 eBPF 从宿主机内核非侵入采集微服务活动，并在 RCD-DK 中用领域知识缩小因果图搜索空间。

**可迁移思想。** 领域知识应先约束可行因果边，避免在全部遥测变量之间盲目搜索。

**迁移障碍。** 交换机告警和物理拓扑没有与 eBPF 服务活动等价的因果变量；多个设备告警可能共享隐藏故障父节点，ECMP 又使边方向不可识别。本文可以用网络角色、端点和物理路径约束候选关系，但不能声称从现有告警恢复完整因果图。

### 4.2 BiAn（SIGCOMM 2025）

**方法。** BiAn 采用分层 LLM 推理：先总结监控告警，再逐设备分析异常，最后联合评分；第二阶段加入简化拓扑与全局时间线。它用小模型处理摘要和单设备任务，用 entropy early stop 控制是否继续复杂推理，并通过历史 incident 更新提示知识。357 个非平凡 case 上报告 95.5% accuracy，Hot Device 为 70.5%；消融中设备联合推理、拓扑和时间线继续提高准确率，early stop 将时间降到 70% 且只损失 0.5% accuracy。

**可迁移思想。** 分层证据组织、拓扑/时间线交叉验证以及按不确定性 early stop 都与本文高度相关。

**直接照搬为何风险很高。** BiAn 的输入是多种监控工具、SOP 和历史 incident，可为单设备分析提供丰富上下文；本文小模型目前主要看到设备自身的角色、告警名和邻居，缺少跨设备对比和稳定保留的端口/物理链路描述。更重要的是，本文实测全量 LLM 重排 Top-1 为 75.47%，低于确定性 76.10%。因此本文不能仅复刻“每设备摘要 + LLM 联合评分”，而应让确定性路径-时序排序先产生候选与冲突，再选择性调用 LLM。

### 4.3 TAMO（TSC 2025）

**方法。** TAMO 不让 LLM 直接消费原始多模态数据，而提供多模态对齐、根因定位和故障类型分类三个专用工具。它把 metric、log、trace 对齐到统一时间表示，并用专门定位模型构造因果依赖，再由 LLM 组织诊断与修复建议。论文报告两个 benchmark 上 Acc@1 平均提升 4.8%。

**可迁移思想。** 数值时间序列、文本与图结构应先由专用算法转成受控证据，LLM 负责调用工具和组织结果，而不是替代底层定位器。

**迁移障碍。** 本文数据没有完整微服务 metrics/traces 或动态 service graph，不能直接使用 TAMO 的多模态对齐和服务因果模型。可迁移的是“算法先编译证据、LLM 后推理”的架构原则。

### 4.4 LLM reasoning failure 研究（FORGE 2026）

**发现。** Stalled, Biased, and Confused 在 48,000 个模拟故障场景上比较多种 LLM 与 agent workflow，整理出 16 类 RCA reasoning failure，包括 fabricated evidence、confused provenance、arbitrary evidence selection、evidential insufficiency、failure to update belief 和 excessive speculation。研究强调多跳传播和输入模态变化会显著影响最终正确性。

**对本文的意义。** LLM 结果必须带原始证据来源；确定性高置信结果不应被无约束覆盖；弱证据应触发 abstention；门控评价应同时报告覆盖率与选择性风险。

### 4.5 本类的统一缺口

- 因果图效果依赖足够且方向可识别的因果变量；
- LLM 效果依赖高质量知识、受控工具和证据编排，而不是参数规模本身；
- 全量推理存在成本、时延与错误覆盖正确排序的风险。

因此本文的第三模块应是 selective arbitration，而不是 full-case LLM ranker。

## 5. INTRO 中的推荐压缩顺序

INFOCOM 版不建议按“事件方法 -> 拓扑方法 -> LLM 方法”的常见顺序。更强的逻辑是：

1. **先讲路径约束方法。** 它们与“端到端 Pingmesh 异常定位内部设备”最接近，先确立本文的问题坐标。
2. **再讲事件依赖方法。** 说明告警时间与语义可补充路径证据，但不能替代物理归属。
3. **最后讲因果图/LLM。** 说明它们可处理冲突与文本知识，但必须受确定性证据和成本约束。

三类方法可各用一个段落，统一以“可迁移思想 -> 在当前观测条件下为何失效 -> 本文需要什么”收束。不要写成“这些工作解决别的任务，因此不适用”。

## 6. 可直接使用的三段缺口

### 路径约束段

Network-tomography approaches infer internal failures from end-to-end path outcomes, and recent systems further exploit fine-grained provenance or workload-specific traffic structures to restrict the diagnosis space. These works establish the importance of path-constrained localization. However, they either actively select and repeatedly acquire binary path observations, or rely on mechanism-specific visibility such as PFC provenance and stable training traffic. A post-incident Pingmesh case provides neither capability; moreover, equal-cost rerouting and gray failures make a single working/failed path abstraction unreliable. Hence, the task requires passive support over feasible source-sink paths and an explicit estimate of whether the fixed observations can distinguish candidate devices.

### 事件依赖段

Event-correlation methods aggregate alerts through semantic similarity, historical co-occurrence, temporal excitation, or time-location clustering. These signals are useful for suppressing noise and recovering likely event dependencies, but they can favor downstream devices that emit many derivative alerts, degrade on rare or evolving alarm types, and do not establish whether the corresponding device lies on a feasible path affected by the current endpoint pair. Event evidence therefore needs to be conditioned on the physical incident and made robust to alert volume.

### 语义推理段

Causal-graph and LLM-assisted RCA systems use domain knowledge, specialized tools, and hierarchical reasoning to organize heterogeneous telemetry. Their success depends on causal variables or rich monitoring sources that may not exist in switch-level Pingmesh incidents. Processing every device with unrestricted semantic reasoning also incurs substantial cost and can select evidence arbitrarily or overwrite a correct deterministic ranking. Semantic reasoning should therefore be invoked only for calibrated topology-temporal conflicts, with provenance-preserving evidence and an abstention path for insufficient cases.
