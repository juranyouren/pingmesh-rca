# Introduction（上一稿：WWW 三挑战叙事结构）

> 更新日期：2026-08-25  
> 写作说明：借鉴 ART 及近年 WWW 论文的论证功能顺序——工程问题、已有能力、精确缺口、三项挑战、设计 insight、模块响应、实验和贡献；不复用其具体措辞。  
> 方法边界：监督式 PC-STGR 是 Stage 1 主模型；PC-STGR-SSL 是独立的自监督预训练变体。M1 构建根因无关概率图，M2 才进行根因条件传播 DAG 求解。  
> 结果边界：新的 grouped OOF、PC-STGR-SSL 对照和 Stage 2 路径标注实验尚未完成。本稿不使用历史 IC-STGR 指标，也不预设尚未得到的提升。正文中的方括号为引用或实验占位符。

## 1. 引言

大型云服务依赖数据中心网络持续提供低时延、高吞吐和高可用的通信能力。随着网络规模扩大以及 Clos、ECMP 等多路径机制的广泛部署，链路、设备或协议状态异常可能跨越多个网络层级，并最终表现为端到端时延升高或丢包。Pingmesh 一类主动测量系统能够持续探测端点之间的网络质量，为生产故障发现提供及时入口 `[Pingmesh, R-Pingmesh]`。然而，一次异常探测通常只能说明某个源—目的端点对的通信受到影响：ECMP 隐藏了实际经过的内部路径，端到端症状也不能直接指出真正的物理根因设备。告警触发后，运维人员仍需在大量候选设备、物理连接和告警事件中回答两个紧密相关的问题：**哪台设备是根因，以及故障如何从该设备传播并影响当前观测目标？** 这两个问题直接影响故障缓解时间，也决定设备隔离、链路切换和路由调整等操作是否安全。

现有研究已从主动探测、事件关联和学习式根因分析等方向推进了故障定位。专用探测和路径诊断系统能够通过额外测量或特定网络观测缩小故障范围 `[Pingmesh, R-Pingmesh]`；多模态 RCA 方法能够联合日志、指标和调用链学习组件依赖或根因排名 `[Eadro, DiagFusion, MULAN]`；可解释诊断方法还可以给出历史相似案例、异常事件模式、指标贡献或动态因果关系 `[DejaVu, Nezha, FaultInsight, ShapleyIQ]`。这些工作证明了自动化定位和解释的可行性，但其输出与事后 Pingmesh case 所需的工程证据仍不完全等价。一个设备分数、特征权重、事件触发链或一般因果图，并不自动保证解释沿本次 case 的物理拓扑成立、能够从候选根因到达受影响设备，或能回溯到支持每条传播边的原始告警和时间证据。要弥合这一差距，系统既要从有限生产 case 中学习复杂的根因模式，又要把学习结果转化为受网络约束、可供工程人员核验的传播过程。

实现这一目标面临三个关键挑战。

**挑战一：Case 数量少，但一个 case 中的设备与事件复杂（Sparse Cases with Dense Information）。** 生产故障 case 的收集周期长，根因标签还需要运维专家结合多源观测进行确认。虽然单个 case 内可以包含大量设备、告警、日志和关系边，其监督信号通常仍只是一个 case 级根因标签；图中节点多并不等于存在同等数量的独立根因标注样本。仅依赖这些稀疏标签训练深度模型，容易记忆少量 case 中特定的端点组合、告警模式或拓扑结构，并在新故障上产生过拟合。已有无监督 AIOps 和 masked graph learning 工作表明，图的属性与结构本身可以提供额外训练信号 `[ART, GraphMAE, GraphMAE2]`。但对于本任务，关键问题是如何在不泄漏验证 case 根因信息的前提下，把一个 case 内密集的设备、事件和关系转化为自监督约束，再服务于 case 级设备排序。

**挑战二：拓扑位置、告警语义和事件时序相互耦合（Multidimensional Evidence with Complex Interactions）。** 一个设备是否可能成为根因，不仅取决于它是否产生告警，还取决于它相对异常源端和目的端的位置、与其他设备的物理邻接、设备角色与状态、告警语义，以及设备内和跨设备事件的时间顺序。不同证据的作用还会随拓扑角色和故障类型而变化：同一条告警出现在路径走廊内外具有不同意义，相同时间差配合不同告警语义也可能支持不同传播解释。现有多模态 RCA 研究已经指出，单一模态、分别建模各模态或简单融合会遗漏跨信号作用 `[Eadro, DiagFusion, MULAN, Nezha]`。在 Pingmesh 场景中，人工规则或固定权重通常只能分别计算拓扑、告警和时间分数后进行加权，难以表达这种条件化的非线性交互；Device-only 建模又会把多条事件过早压缩为统计量，丢失事件归属、语义和细粒度时序。

**挑战三：深度学习模型是黑盒输出，无法直观展示模型的推理过程（Black-Box Predictions with Limited Interpretability）。** 根因概率或 Top-K 排名能够提高筛查效率，却不能直接说明模型为何选择该设备，也不能展示故障从哪里开始、经过哪些物理设备以及哪些观测支持这一过程。解释性在生产网络中并非附加展示：运维人员需要核验诊断是否与原始告警和物理连接一致，判断影响范围和风险可控的处置位置，并为跨团队协同、变更审计和事后复盘保留证据 `[ART, DejaVu, FaultInsight]`。将预测权重直接可视化也不足以解决这一问题，因为“模型关注了哪些输入”不等于“故障沿哪些设备传播”。更困难的是，告警缺失、时间区间重叠、语义冲突和 ECMP 会使两个相邻设备之间的传播方向难以硬判定；即使得到每条边的局部方向概率，逐边选择最大概率状态也可能产生环路、反向边、根因不可达分支或拓扑非法路径。因此，可解释性要求同时处理局部方向不确定性和全局传播结构约束。

本文建立在两个关键观察之上。首先，生产故障的 case 级根因标签虽然稀疏，但单个 case 内并不缺少可学习信息：事件属性、设备归属、物理邻接以及设备内和跨设备的时间关系，都可以转化为图内监督信号。其次，一个可信的根因不应仅仅具有较高的模型预测分数，还应能够将分散在不同设备上的告警与状态组织成符合物理拓扑和事件时序的传播过程。换言之，局部传播方向可以存在不确定性，但正确的根因应使这些局部关系在全局上形成更一致、可回溯的解释。

基于上述观察，本文将根因诊断划分为“候选发现”和“传播验证”两个阶段。Stage 1 使用 PC-STGR 联合学习路径位置、拓扑结构、告警语义和事件时序之间的复杂交互，并通过独立的 PC-STGR-SSL 变体利用 case 内图结构进行自监督预训练，从而获得高召回的根因候选。Stage 2 不再仅依据设备分数判断根因，而是先以三状态概率保留相邻设备之间的传播方向不确定性，再针对不同候选根因求解拓扑合法、从根可达且证据可回溯的传播 DAG。候选根因能否形成与观测一致的传播解释，进一步作为检验和修正根因排序的依据。

在 **Stage 1**，本文提出路径条件化时空图排序器 **PC-STGR**。PC-STGR 将候选设备与告警/日志事件分别表示为 Device 和 Event 节点，将异常源—目的端距离、端点锚点和近最短路径走廊编码为设备的路径条件，并显式建立物理邻接、事件归属、设备内时间顺序和跨设备时间关系。关系感知的图消息传递在这些异构关系上联合编码拓扑、语义与时序证据，随后通过 case 内 Softmax 输出设备级根因 Top-K。为回应稀疏 case 与密集图内信息之间的不平衡，本文进一步设计一个与监督主模型分离的自监督预训练变体 **PC-STGR-SSL**：仅使用当前训练折中的无标签图，执行事件名称掩码恢复、节点数值特征重建以及边存在性与关系类型重建，再使用少量 case 级根因标签进行排序微调。该设计不是把同一 case 中的设备节点视为独立根因样本，而是把节点、事件和边转换为密集的图内学习约束。

在 **Stage 2 的 M1**，本文构建一张所有候选根因共享的根因无关概率传播图。M1 将告警和日志规范化为可回溯的事件片段，并利用本次 case 的物理拓扑、异常端点走廊和事件设备裁剪候选子图。对于每一对物理相邻设备，M1 仅依据带容忍区间的时间先后、告警语义组合以及本端/远端或 peer 直接关系证据，估计三个互斥状态：`P(A→B)`、`P(B→A)` 和 `P(No Direct Propagation)`。三状态建模允许系统在证据不足或相互冲突时保留正反方向竞争，并显式表达“这条物理邻接没有被本次故障激活”，避免二元硬判定把局部错误连续放大。拓扑在此只限定允许评估的设备对，不为某个方向加分；Stage 1 排名和候选根距离也不进入 M1，因此不同根因候选面对的是同一组传播假设。

在 **Stage 2 的 M2**，本文将局部概率关系转化为根因条件的全局传播解释。对于 Stage 1 的每个候选根因，M2 在同一张 M1 图上执行拓扑边校验和根因条件筛选，只保留概率支持充分且从候选根向外的方向边；随后针对各受影响目标执行受路径深度和搜索宽度约束的束搜索，并将高分路径无环合并为从候选根可达的传播 DAG。每条输出边保留对应的物理 topology edge ID、M1 假设 ID、原始告警/日志 evidence ID 以及支持和反证信息，使工程人员能够逐边核验传播依据。M2 进一步计算候选根能够组织成合法传播图的证据解释分数，并与 Stage 1 根因先验联合形成最终排序；当 M1 没有有效传播关系或所有候选均无法形成传播边时，系统保持 Stage 1 排序，避免在没有传播证据时强制重排。

我们将在生产 Pingmesh case 上系统评估根因排序、传播重构和端到端效率，并围绕三个挑战分别回答：图内自监督是否改善有限 case 下的泛化，路径条件化时空交互是否优于规则融合和简化图表示，以及三状态建模与根因条件路径求解能否生成拓扑合法、证据可回溯的传播解释。`[待实验完成后填写：可公开的数据统计口径；PC-STGR 与 PC-STGR-SSL 的 grouped OOF Top-K/MRR；M1 边概率消融；M2 路径有效性、目标覆盖率、重排净收益与推理开销。]`

本文的主要贡献如下：

1. **面向 Sparse Cases with Dense Information 的图内自监督方案。** 提出独立的 PC-STGR-SSL 变体，将训练 case 内的设备、事件和关系转化为掩码与重建任务，在不增加根因标注成本且不引入折间泄漏的前提下，为 case 级根因排序提供预训练表示。
2. **面向复杂多维交互的路径条件化时空排序。** 提出监督式 PC-STGR，将 Pingmesh 源—目的路径位置、物理拓扑、事件级语义和设备内/跨设备时间关系统一到 Device–Event 图中，直接学习候选集合随 case 变化的设备根因排序。
3. **面向局部方向不确定性的根因无关三状态建模。** M1 将每个物理相邻设备对表示为正向、反向和无直接传播三种竞争概率，并让所有根因候选共享同一张假设图，从而保留不确定性并降低循环论证风险。
4. **面向工程核验的根因条件传播路径重构。** M2 通过根因条件筛边、逐目标束搜索和无环路径合并生成拓扑合法、从根可达且证据可回溯的传播 DAG，并用解释能力辅助检验根因排序。

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
| `[DejaVu]` | *Actionable and Interpretable Fault Localization for Recurring Failures in Online Service Systems*, ESEC/FSE 2022 |
| `[Nezha]` | *Nezha: Interpretable Fine-Grained Root Causes Analysis for Microservices on Multi-modal Observability Data*, ESEC/FSE 2023 |
| `[FaultInsight]` | *FaultInsight: Interpreting Hyperscale Data Center Host Faults*, KDD 2024 |
| `[ShapleyIQ]` | *ShapleyIQ: Influence Quantification by Shapley Values for Performance Debugging of Microservices*, ASPLOS 2023 |
