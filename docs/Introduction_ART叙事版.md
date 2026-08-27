# Introduction（证据可核验根因诊断主线中文草稿）

> 更新日期：2026-08-25  
> 核心主线：`Detection is not Diagnosis → Candidate Learning → Propagation Verification → Verifiable Diagnosis`。  
> 命名说明：整体框架与自监督预训练模块尚未定名，本文暂用功能性表述。监督式 PC-STGR 仍是 Stage 1 主模型；图内自监督只作为独立预训练策略，不改变 PC-STGR 的推理结构与输出契约。  
> 结果边界：新的 grouped OOF、自监督预训练对照和 Stage 2 路径标注实验尚未完成。本稿不使用历史 IC-STGR 指标，也不预设尚未得到的性能提升。正文中的方括号为引用或实验占位符。

## 1. 引言

大型云服务依赖数据中心网络持续提供低时延、高吞吐和高可用的通信能力。随着网络规模扩大以及 Clos、ECMP 等多路径机制的广泛部署，链路、设备或协议状态异常可能同时影响多个网络层级，并最终表现为端到端时延升高或丢包。Pingmesh 一类主动测量系统能够持续探测端点之间的网络质量，为生产故障发现提供及时入口 `[Pingmesh, R-Pingmesh]`。然而，**发现异常并不等于完成诊断**。一次异常探测通常只能说明某个源—目的端点对的通信受到影响；ECMP 隐藏了实际经过的内部路径，端到端症状也不能直接指出真正的物理根因设备。告警触发后，运维人员仍需在大量候选设备、物理连接和事件中回答两个紧密相关的问题：哪台设备最可能是根因，以及该候选能否解释当前 case 中分散出现的异常观测？这两个问题直接影响故障缓解时间，也决定设备隔离、链路切换和路由调整等操作是否安全。

现有研究已从主动探测、事件关联、多模态根因分析和可解释诊断等方向推进故障定位。专用探测和路径诊断系统能够通过额外测量或特定网络观测缩小故障范围 `[Pingmesh, R-Pingmesh]`；多模态 RCA 方法能够联合日志、指标和调用链学习组件依赖或根因排名 `[Eadro, DiagFusion, MULAN]`；进一步地，可解释方法还可以给出历史相似案例、异常事件模式、指标贡献、事件触发链或动态因果网络 `[DejaVu, Nezha, FaultInsight, NetEventCause, ShapleyIQ]`。这些工作证明了自动化定位和多种解释形式的价值，但不同解释回答的问题并不相同：设备分数回答“谁更可疑”，特征贡献回答“哪些输入影响预测”，事件关系或因果网络描述观测之间的关联；它们并不直接等价于事后 Pingmesh case 所需要的设备级传播解释。

本文关注一种面向 Pingmesh 故障的**证据可核验根因诊断**任务：给定异常源—目的端、case 物理拓扑以及设备告警和日志，系统不仅需要输出根因设备排序，还需要为候选根因构建一张受本次物理拓扑约束、从候选根可达并能够回溯原始事件证据的传播假设图。这里的“传播”表示由拓扑、事件时序和告警语义共同支持的故障影响假设，而不是未经独立干预验证的真实因果链。该输出使运维人员能够进一步核验候选是否与观测一致、评估影响范围并定位可操作的处置位置。实现这一目标面临三个关键挑战。

**挑战一：Case 数量少，但一个 case 中的设备与事件复杂（Sparse Cases with Dense Information）。** 生产故障 case 的收集周期长，根因标签还需要运维专家结合多源观测进行确认。虽然单个 case 内可能包含大量设备、告警、日志和关系边，其监督信号通常仍只是一个 case 级根因标签；图中节点多并不意味着存在同等数量的独立根因样本。仅依赖这些稀疏标签训练深度模型，容易记忆少量 case 特有的端点组合、告警模式或拓扑结构，并在新故障上产生过拟合。已有无监督 AIOps 和 masked graph learning 工作表明，节点属性与图结构本身可以提供额外训练信号 `[ART, GraphMAE, GraphMAE2]`。因此，本任务首先需要解决的是：如何在不泄漏验证 case 信息的前提下，将单个 case 内密集的设备、事件和关系转化为图内学习约束，并服务于 case 级根因排序。

**挑战二：拓扑位置、告警语义和事件时序相互耦合（Multidimensional Evidence with Complex Interactions）。** 一个设备是否可能成为根因，不仅取决于它是否产生告警，还取决于它相对异常源端和目的端的位置、与其他设备的物理邻接、设备角色与状态、告警语义，以及设备内和跨设备事件的时间顺序。这些证据的作用具有明显的条件性：同一条告警出现在源—目的路径走廊内外可能具有不同意义，相似的时间差配合不同告警语义也可能支持相反判断。已有多模态 RCA 研究指出，单一模态、相互独立地处理各模态或简单融合会遗漏跨信号作用 `[Eadro, DiagFusion, MULAN, Nezha, GAMMA]`。在 Pingmesh 场景中，人工规则或固定权重通常只能分别计算拓扑、告警和时间分数后进行加权，难以表达这种随 case 变化的非线性交互；Device-only 建模又会将多条事件过早压缩为统计量，丢失事件归属、语义和细粒度时序。

**挑战三：根因排名缺少可核验的传播依据（Root-Cause Rankings with Limited Diagnostic Verifiability）。** 学习式定位方法能够高效输出设备概率或 Top-K 候选，但这种点式预测只能回答“哪台设备最可疑”，不能说明候选根因如何解释其他设备上的异常，也不能指出哪些物理连接、告警和时间关系支持这一判断。注意力或特征重要性可以反映哪些输入影响了模型预测，却不等价于工程语义上的故障传播过程。生产网络中的根因结论可能触发设备隔离、链路切换和路由调整，运维人员需要据此核验诊断、评估影响范围并选择风险可控的处置位置 `[ART, DejaVu, FaultInsight]`。然而，从不完整观测中构建传播解释并不直接：告警缺失或延迟、事件时间区间重叠、告警语义冲突以及 ECMP 路径不确定性，使物理相邻设备之间的传播方向难以硬判定；即使能够分别估计局部边方向，独立组合这些关系仍可能产生环路、反向边、根因不可达分支或无法解释受影响目标的结构。因此，系统需要在保留局部传播不确定性的同时，将分散的边级证据组织成全局一致、可供工程人员核验的根因条件传播解释。

本文建立在两个关键观察之上。首先，**case 级标签稀疏并不意味着 case 内可学习信号稀疏**：事件属性、设备归属、物理邻接以及设备内和跨设备的时间关系，都可以转化为图内学习约束。其次，**可信根因不应只具有较高预测分数，还应能够解释当前故障中的分布式观测**：局部传播方向可以存在不确定性，但更合理的候选根因应使这些局部关系在全局上形成拓扑合法、时序一致且证据可回溯的传播假设。基于这两个观察，本文将根因诊断划分为两个连续阶段：Stage 1 执行 **Candidate Learning**，从稀疏 case 和复杂观测中产生高召回根因候选；Stage 2 执行 **Propagation Verification**，检验不同候选能否将局部证据组织成一致的传播解释。该设计将设备排名转化为“根因先验 + 传播证据”的可核验诊断，而不是把 Stage 2 作为对神经网络内部推理过程的忠实还原。

在 **Stage 1**，本文提出路径条件化时空图排序器 **PC-STGR**。PC-STGR 将候选设备与告警/日志事件分别表示为 Device 和 Event 节点，将异常源—目的端距离、端点锚点和近最短路径走廊编码为路径条件，并显式建立物理邻接、事件归属、设备内时间顺序和跨设备时间关系。关系感知图消息传递在这些异构关系上联合编码拓扑、语义与时序证据，随后通过 case 内 Softmax 输出设备级根因 Top-K。为利用少量 case 内部的密集结构，本文进一步设计一种独立的图内掩码预训练策略：仅使用当前训练折中的无标签图，执行事件名称恢复、节点数值特征重建以及边存在性与关系类型重建，再使用 case 级根因标签微调 PC-STGR。该预训练策略不增加推理阶段，不把同一 case 中的设备节点视为独立根因样本，也不改变监督式 PC-STGR 的输出契约。

在 **Stage 2 的 M1**，本文首先构建一张根因无关的三状态传播假设图。M1 将告警和日志规范化为可回溯的事件片段，并利用本次 case 的物理拓扑、异常端点走廊和事件设备裁剪候选子图。对于每一对物理相邻设备，M1 仅依据带容忍区间的事件先后、告警语义组合以及本端/远端或 peer 直接关系证据，估计三个互斥状态：`P(A→B)`、`P(B→A)` 和 `P(No Direct Propagation)`。三状态建模允许系统在证据不足或相互冲突时保留正反方向竞争，并显式表达“该物理邻接未被当前观测支持为直接传播关系”，避免二元硬判定将局部错误向后放大。Stage 1 排名和候选根距离不进入 M1，因此所有候选面对同一批局部传播证据；根因无关在此是降低候选偏置和循环论证风险的设计性质，而不是对真实因果方向的保证。

在 **Stage 2 的 M2**，本文针对不同候选根因执行根因条件传播验证。对于 Stage 1 的每个候选，M2 在同一张 M1 假设图上校验原始拓扑边，并仅保留概率支持充分且从候选根向外的方向关系；随后针对各受影响目标执行受深度和搜索宽度约束的路径搜索，将高分路径无环合并为从候选根可达的传播 DAG。每条输出边保留对应的 topology edge ID、M1 假设 ID、原始告警/日志 evidence ID 以及支持和反证信息，从而允许运维人员逐边核验。M2 进一步计算候选根能够组织成合法传播图的解释分数，并与 Stage 1 根因先验联合形成最终排序。当 M1 没有有效传播关系，或所有候选均无法形成传播边时，系统保持 Stage 1 排序，避免在缺乏传播证据时强制重排。因此，Stage 2 提供的是独立的、证据驱动的诊断验证，而不是对 PC-STGR 内部注意力或消息传递过程的事后可视化。

我们将在生产 Pingmesh case 上从候选学习、传播建模和诊断验证三个层面评估该框架。具体而言，实验将回答：PC-STGR 能否在 grouped OOF 设置下获得可靠的根因候选召回；路径条件、事件语义和时间关系分别贡献多少；图内掩码预训练能否改善有限 case 下的泛化；三状态建模能否更好地区分正向、反向和无直接传播关系；以及根因条件传播 DAG 是否满足拓扑合法、根可达和证据可回溯要求，并能否在控制错误重排的前提下改善最终诊断。`[待实验完成后填写：可公开的数据统计口径；PC-STGR 及其预训练版本的 Top-K/MRR；M1 Macro-F1、Log Loss/Brier/ECE；M2 路径有效性、目标覆盖率、证据回溯率、wrong→correct 与 correct→wrong 净收益以及推理开销。]`

本文的主要贡献如下：

1. **面向稀疏 case 和复杂观测的根因候选学习。** 提出路径条件化 Device–Event 时空图排序器 PC-STGR，并设计不引入折间泄漏的图内掩码预训练策略，将源—目的路径位置、物理拓扑、事件语义和时间关系统一用于 case 内设备排序。
2. **面向局部方向不确定性的三状态传播建模。** 在不读取根因候选排名的条件下，对每个物理相邻设备对估计正向、反向和无直接传播三种竞争概率，为所有候选提供共享的局部传播假设。
3. **面向诊断可核验性的根因条件传播验证。** 通过拓扑约束筛边、逐目标路径搜索和无环合并生成从候选根可达、证据可回溯的传播 DAG，并利用候选解释全局观测的能力辅助检验根因排序。

## 2. 引用占位符映射

| 占位符 | 论文 |
|---|---|
| `[Pingmesh]` | *Pingmesh: A Large-Scale System for Data Center Network Latency Measurement and Analysis*, SIGCOMM 2015 |
| `[R-Pingmesh]` | *R-Pingmesh*，RoCE/RNIC 服务感知主动诊断工作 |
| `[ART]` | *ART: A Unified Unsupervised Framework for Incident Management in Microservice Systems*, WWW 2025 Industry |
| `[GraphMAE]` | *GraphMAE: Self-Supervised Masked Graph Autoencoders* |
| `[GraphMAE2]` | *GraphMAE2: A Decoding-Enhanced Masked Self-Supervised Graph Learner*, WWW 2023 |
| `[Eadro]` | *Eadro: An End-to-End Troubleshooting Framework for Microservices on Multi-source Data*, ICSE 2023 |
| `[DiagFusion]` | *Robust Failure Diagnosis of Microservice System Through Multimodal Data*, TSC 2023 |
| `[MULAN]` | *MULAN: Multi-modal Causal Structure Learning and Root Cause Analysis for Microservice Systems*, WWW 2024 |
| `[GAMMA]` | *GAMMA: Graph Neural Network-Based Multi-Bottleneck Localization for Microservices Applications*, WWW 2024 |
| `[DejaVu]` | *Actionable and Interpretable Fault Localization for Recurring Failures in Online Service Systems*, ESEC/FSE 2022 |
| `[Nezha]` | *Nezha: Interpretable Fine-Grained Root Causes Analysis for Microservices on Multi-modal Observability Data*, ESEC/FSE 2023 |
| `[FaultInsight]` | *FaultInsight: Interpreting Hyperscale Data Center Host Faults*, KDD 2024 |
| `[NetEventCause]` | *NetEventCause: Event-Driven Root Cause Analysis for Large Network System Without Topology* |
| `[ShapleyIQ]` | *ShapleyIQ: Influence Quantification by Shapley Values for Performance Debugging of Microservices*, ASPLOS 2023 |

