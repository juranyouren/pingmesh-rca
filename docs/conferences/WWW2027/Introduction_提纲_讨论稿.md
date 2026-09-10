# Introduction 提纲

更新日期：2026-09-10

# 总体主线

本文提出 **RPG-Recon（Root-conditioned Propagation Graph Reconstruction）**，用于从 Pingmesh 异常触发后的不完整设备观测中恢复与当前故障对应的设备级传播结构。

RPG-Recon 不直接从全部设备事件中一次性生成唯一传播图，而是将传播图重构组织为三个相互衔接的模块：

* **M1：候选起点建模（Root Hypothesis Modeling）**：综合 Pingmesh 异常上下文、设备事件和物理拓扑，形成多个候选传播起点假设；
* **M2：局部传播支持建模（Local Propagation Support Modeling）**：在物理相邻设备对上汇总时间、告警、日志及接口等旁证，表示不同传播方向及无直接传播关系的相对支持；
* **M3：根因条件传播图重构（Root-Conditioned Graph Reconstruction）**：针对每个候选起点，结合局部支持与物理、可达和结构约束选择并组合设备关系，恢复设备级传播图。

三个模块对应现有两阶段实现：Stage 1 = M1（PC-STGR），Stage 2 = M2 + M3（P0）；不与代码中历史 `m1/m2` 目录编号混用。

其中，M1 为传播重构提供竞争性的起点假设，M2 保留局部关系中的不确定性，M3 则在候选根条件下将局部证据组织为整体结构，是 RPG-Recon 的核心。

本文关注**设备粒度的故障解释**。Pingmesh 异常是诊断触发条件和故障上下文，主要解释对象是设备之间的有向影响关系。本文所称“传播关系”并不表示已观测到严格因果传播，而是指受到设备事件支持、并受原始物理拓扑约束的设备级有向影响假设。候选根因设备相应地作为传播结构的候选起始节点，而非更细粒度硬件、配置或软件故障的最终物理原因。

---

# 1. 引入

考虑一次端到端丢包告警触发后的排查场景。图 1 给出一个合成工程示例：H1 与 H2 之间的 Pingmesh 探测异常，交换设备 C 记录了面向 S 的接口 down 告警，S 记录了 BGP 会话回退，C 的日志还显示与 S 的邻居状态变化，而连接端点的 L1、L2 没有相应事件记录。面对这些信息，工程师可以先固定异常窗口，分别打开 C、S 的告警和日志，核对接口与邻居对应关系，再将“C 的异常影响 S”等假设展开为手工排障树，并为每一分支记录支持证据和仍需检查的项目。这里的工作尚未结束于找到一台可疑设备：还需要判断 C、S 在本次异常中的关系，以及现有证据能否将这一解释继续连接到其他设备。

即使候选设备相同，不同的起点和边方向仍会产生不同的故障解释。如果先把 S 固定为唯一根因，围绕 C 构造的传播结构就可能被提前排除；如果仅按告警顺序连接设备，又可能把相关现象误判为直接影响。沿物理拓扑把关系延伸至 L1、L2 同样缺少依据，因为没有记录既不证明设备正常，也不证明异常经过它们。工程师因而需要同时维护候选起点、核对设备对的局部证据，并把能够共同成立的关系组织为可检查的整体解释。

这一任务发生在支撑 Web 服务的数据中心网络运维中。搜索、在线存储等分布式服务依赖服务器之间的通信，Pingmesh 等端到端测量为网络异常分析提供观测入口。[Pingmesh，§1–2](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/11/pingmesh_sigcomm2015.pdf)。本文关注由此触发的后续诊断：给定异常端点、故障窗口内的设备告警与日志和原始物理拓扑，恢复与当前 incident 对应的设备级有向影响图，并提供逐边可核查的证据及未决关系。该图将起点假设、设备影响关系和解释缺口放入同一结构，服务于 Web 基础设施的故障核查与交接。业务端影响及人工排障收益需要另行验证，不能从本合成示例推算。

具体观测、排障步骤、假设树与设备图的区别见[案例设计](./论文引入设计：从工程师排障现场到传播图恢复.md)。

---

# 2. 以往工作

已有网络故障诊断研究主要从两个方向展开。

一类工作关注“**故障可能在哪里**”，利用路径观测、设备告警、网络拓扑或跨设备推理识别故障范围和可疑设备。例如，BiAn 综合设备告警、拓扑、全局时间线和历史知识进行跨设备分析，并生成根因设备排名 [11]。这类方法能够缩小排查范围，但设备排名本身无法描述多个异常设备在一次具体故障中的影响关系。

另一类工作开始关注“**异常之间如何关联**”。例如，NetEventCause 从历史告警中学习事件依赖关系，并以告警实例为节点恢复传播 DAG [7]。这类方法说明了显式传播结构对于故障解释的重要性，但事件级依赖并不能直接等同于设备级传播结构，部分工作还依赖完整调用路径、专门遥测或较完整的历史知识。

本文关注不同的观测条件：由 Pingmesh 端到端异常触发，在缺少真实传播路径和完整设备级因果观测的情况下，仅利用异常上下文、设备告警、日志和原始物理拓扑，恢复**当前故障实例对应的设备级有向影响结构**。因此，本文既不同于仅生成根因设备排名，也不同于从历史事件中恢复一般性的事件依赖图，而是研究 **incident-specific device propagation graph reconstruction**。

---

# 3. 挑战：起点与结构耦合、局部关系不明、整体解释不一致

传播图重构需要处理**起点假设对可恢复结构的限制、局部设备关系的不确定性，以及关系组合的整体一致性**。设备规模和告警混杂是场景背景，不单列为新挑战。

## C1：起点不确定性会改变可恢复的传播结构

设备传播图中的起点决定哪些节点需要从同一来源得到解释，以及哪些方向能够构成根可达的结构。因而，根定位误差不仅改变设备排名，也可能在图恢复开始前排除正确的传播方向和分支。以物理相邻的 C、S 为例，在静态单根模型中，分别以 C 和 S 为起点会对 C→S 和 S→C 施加不同的结构条件；即使参与设备完全相同，也对应不同解释。不完整事件可能不足以先确定唯一起点，但图合法性也不能反过来证明某个起点正确。挑战是在可控代价下保留图恢复所需的起点假设，使候选结构能在相同观测和局部证据下比较，并明确哪些部分仍无法区分。

**如何保留足以支持结构恢复的起点假设，并在相同观测下比较候选起点—图解释，而不以结构合法性替代起点证据？**

## C2：不完整旁证下，局部设备关系及方向难以判断

对于物理相邻设备 \(u,v\)，仍需判断二者是否存在与本次故障相关的直接影响，以及可能方向是 \(u\rightarrow v\) 还是 \(v\rightarrow u\)。

事件时间、严重度、告警语义和接口信息等线索都只能提供部分支持。例如，A 早于 B 并不能证明 A→B，二者也可能共同受到第三个设备 R 的影响。事件缺失还使“没有观察到支持”和“可以确认不存在直接传播”难以等同。

因此，第二个问题是：

**如何综合相互支持或冲突的局部证据，同时表示关系存在性和传播方向的不确定性？**

## C3：具有局部支持的关系难以组成整体一致的传播结构

即使若干设备对分别获得了传播支持，独立选择这些关系也可能产生循环、孤立片段或彼此不兼容的传播解释。例如，A→B、B→C 和 C→A 在局部上可能分别得到支持，但不能直接组成合理的整体传播解释。

另一方面，物理邻接、连通或无环等结构合法性也不能代替传播证据。一条物理可行的边不能仅因为能够连接两个片段就被加入传播图。

因此，第三个问题是：

**如何在同一候选起点条件下，从不确定的局部关系中选择能够共同成立的一组边，并组织为结构一致且具有证据支持的传播解释？**

---

# 4. Motivation：从局部不确定观测到根因条件传播重构

上述三个挑战相互关联。传播起点会影响局部关系的组织方式，而局部关系又决定了某个候选起点能够形成怎样的整体传播结构。

一个直接方案是先确定唯一根因，再围绕它恢复传播图，但一旦起点错误，后续结构会整体受到影响。另一种方案是忽略起点、独立判断设备对之间的传播关系，但又容易得到方向冲突、孤立片段或彼此不兼容的局部结构。

因此，**传播起点与传播结构不能完全割裂处理，也不宜在观测不足时过早绑定为唯一解。** RPG-Recon 将这一过程分解为三个相互衔接的模块：首先显式保留多个候选起点，然后表示可复用的局部传播支持，最后在每个候选起点条件下利用整体结构选择和组合这些关系。

三个模块分别回答：

* **M1：从哪里开始？**
* **M2：哪些局部关系得到支持？**
* **M3：这些关系如何组成一次完整的故障解释？**

但三者共同服务于同一个目标：恢复当前 Pingmesh 异常对应的设备级传播图。

## M1：候选起点建模——延后唯一根因承诺

C1 表明，过早固定起点会限制后续可探索的传播结构。因此，RPG-Recon 综合 Pingmesh 上下文、设备事件和拓扑位置形成 incident-specific 设备评分，将 Top-K 起点交给 M3 分别恢复条件图。M1 与 M3 共同回应起点—结构耦合，不能把候选排序单独称为解决了 C1。

保留多个候选不是进行多根因推断，而是显式保留起点不确定性，使后续传播重构能够分别围绕多个合理假设展开。

当前 M1 由 PC-STGR 实现。其 path-conditioned 信息描述设备相对于异常端点的拓扑上下文，包括端点锚点、拓扑距离和候选路径范围，而不假设已经获得真实 Ping 数据包的完整转发路径。

## M2：局部传播支持建模——先表示歧义，再决定传播边

C2 表明，即使给定候选起点，也无法仅根据物理拓扑确定传播关系。因此，RPG-Recon 在物理相邻设备对上分别汇总 \(u\rightarrow v\)、\(v\rightarrow u\) 和无直接传播关系的证据支持，而不是立即作出确定的边判断。

这些局部支持一方面避免将时间先后、严重度或拓扑位置直接解释为传播因果；另一方面，由于设备对证据本身不依赖最终选择的候选根，可以在不同根因假设之间复用。

这里得到的是不同关系假设的**归一化证据支持**，而不是经过严格校准的因果概率；同时，“证据不足”与“有证据支持不存在直接传播”需要区分。

## M3：根因条件传播图重构——让整体结构参与局部关系选择

M2 得到的局部支持仍不能直接构成最终传播图。针对 M1 提供的每个候选起点，RPG-Recon 将局部关系放入同一根因条件下进行组织。

候选根提供结构起点，原始物理拓扑限定潜在传播边，局部事件提供边证据，而根可达性、无环性等结构条件用于排除不能共同成立的关系组合。

候选根不能替代边证据，结构合法性也不能证明传播关系真实存在。M3 的目标是在不完整观测下，从局部候选关系中选择一组**既具有事件支持、又能够共同形成一致故障解释**的关系，恢复候选根条件下的设备级传播图。

---

# 5. RPG-Recon：根因条件化设备传播图重构

RPG-Recon 将上述三个设计动机落实为三个模块。

## M1：Root Hypothesis Modeling

给定一次 Pingmesh 异常，M1 基于异常端点上下文、原始物理拓扑和故障窗口内的设备事件构造路径条件化 Device–Event 表示，并输出设备排序及 Top-K 候选起点。

当前实现采用 PC-STGR。模型综合事件内容、事件时间以及设备相对于异常端点的拓扑位置，对当前故障中的设备级根因相关性进行建模。

这里的 path-conditioned 指异常端点相关的拓扑上下文，而不是已知 packet-level forwarding path；Device–Event 图中的输入关系也不直接等同于最终恢复的传播边。

## M2：Local Propagation Support Modeling

M2 在原始物理拓扑允许的相邻设备对上构建根无关的局部传播支持。对于每个设备对，系统综合事件时间、告警与日志语义、接口或 peer 等可用信息，表示两个传播方向和无直接传播关系的相对支持。

M2 的输出不是最终传播边，而是一组可供不同候选根复用的局部关系假设。

## M3：Root-Conditioned Graph Reconstruction

对于 M1 提供的每个候选起点，M3 复用 M2 的局部支持，通过受约束的路径搜索与结构组合恢复候选根条件下的传播图。

原始物理拓扑限定潜在传播边，候选根提供结构组织条件，局部证据用于评价具体关系，整体结构约束则用于排除冲突组合。

当前实现采用单根静态 DAG 作为主要解释形式，并进一步使用设备到候选根最短拓扑距离严格递增的方向规则缩小搜索空间。该规则是当前实现的**建模限制**，强于一般的根可达 DAG 条件，不被解释为真实网络传播的天然规律。当前方法采用受约束的路径搜索与合并，也不宣称获得严格全局最优解或实现端到端因果推断。

RPG-Recon 的主要输出包括：

* 候选起点条件下的设备传播图；
* 可用的局部证据引用；
* 替代关系或结构假设；
* 诊断状态。

如果需要在多个候选根条件图之间选择最终报告结果，可以按照实际配置结合 M1 根因分数和图解释信息完成选择。但本文不预设传播图评分一定能够提高根因定位准确率；当图证据不足时，应保留原始候选顺序，而不是强制根据低置信度传播结构修改根因结果。

---

# 6. 贡献

本文围绕 Pingmesh 异常下的设备级故障传播图重构，主要作出以下贡献：

1. **面向故障图恢复的起点—结构假设组织。**
   我们将起点不确定性显式传递到条件图重构，在相同观测和局部支持下比较多个单根解释。PC-STGR 的排序承担候选生成；贡献不归结为首次根因定位或首次使用 Top-K。

2. **结合局部关系不确定性与根因条件结构约束的传播图重构。**
   我们首先在物理相邻设备对上建模方向性传播支持，再针对不同候选起点，通过受物理拓扑、局部证据和整体结构条件约束的关系选择与组合，恢复当前故障实例对应的设备级有向传播结构。

3. **面向根因与传播结构的分层评价设计。**
   主指标采用有向边 P/R/F1，节点、完整标注上的全图匹配和结构合法性分开报告；raw 与结构等价投影并列，固定预测根、直接 Oracle 根和端到端设置分开。实施及旧结果重评分须遵循[指标协议](./故障传播图指标调研与最终评价方案.md)，此处不预设数值收益。

---

# 图片统一视觉规范

图 1 和图 2 采用同一套视觉语言：

* 白色或极浅暖灰背景：`#FCFCFB`
* 主文字、边框和流程箭头：近黑色 `#111111`
* 观测、设备事件、原始拓扑和结构上下文：蓝色 `#1457FF`
* 候选根因 / Root Hypothesis：紫色 `#7A5AF8`
* 被选中的传播边和最终传播图：橙色 `#FF4B1F`
* 未激活物理边、弱化结构和辅助元素：浅灰色 `#E9E9E9`

统一采用：

* publication-ready scientific figure；
* white background；
* clean monoline vector style；
* rounded rectangles；
* straight or orthogonal arrows；
* no gradient；
* no shadow；
* no 3D；
* no decorative icons；
* short English labels；
* readable at two-column paper width。

图中始终严格区分：

1. **Raw physical adjacency**
2. **Observed device events**
3. **Root hypotheses**
4. **Uncertain local propagation support**
5. **Selected propagation edges**

不得将拓扑邻接、时间先后或告警严重度直接画成确定因果关系。

---

# Figure 1：工程师排障案例

采用[案例设计中的 Figure 1](./论文引入设计：从工程师排障现场到传播图恢复.md)，在引入首段引用。以既有合成 DEMO_001 的六个设备展示“观测→核查操作与假设树→条件设备关系与解释缺口”。不再使用虚构的 R/A/B/C/D/U 告警来冒充同一个案例。

图顶标记 Illustrative Example。物理拓扑用灰色无向边；C→S 与 S→C 用虚线标为竞争假设；L1/L2 无事件记录，不补路由事件或直达端点的确定传播路径。操作流程箭头与设备关系分区显示。完整英文图注与可复核事实见案例设计。

---

# Figure 2 Prompt：RPG-Recon Framework

```text
Create a publication-ready left-to-right system overview for a paper on incident-specific device fault-propagation graph reconstruction.

Title the framework:
“RPG-Recon: Root-Conditioned Propagation Graph Reconstruction”.

Use exactly the same visual language as the motivation figure:
white or very light warm-gray background #FCFCFB;
near-black #111111 for text, borders, and workflow arrows;
blue #1457FF for observed events, topology context, and evidence;
purple #7A5AF8 for root hypotheses;
orange #FF4B1F for selected propagation relations and final propagation graphs;
light gray #E9E9E9 for inactive or secondary structure.

Use a clean monoline scientific vector style, thin outlines, rounded rectangles, orthogonal or straight workflow arrows, generous spacing, and short English labels readable at two-column paper width. No gradients, shadows, 3D effects, decorative illustrations, people, logos, or watermarks.

Organize the framework into exactly three main modules inside one large RPG-Recon container.

INPUTS

On the left, show three input blocks:

“Pingmesh Anomaly Context”
“Raw Physical Topology”
“Device Alarms, Logs, and Event Times”

Pingmesh is diagnostic context only.

Do not show a known end-to-end forwarding path.
Do not represent raw topology or temporal order as confirmed causal relations.

M1 — ROOT HYPOTHESIS MODELING

Label the first module:

“M1: Root Hypothesis Modeling”

Add the method label:
“PC-STGR”.

Inside show:

“Path-Conditioned Device–Event Representation”
→
“Incident-Specific Device Scoring”

Use small blue feature labels:
“Endpoint Anchors”
“Topology Distance”
“Event Timing”
“Event Semantics”.

The output is a purple ordered list:
“Top-K Root Hypotheses”

showing r1, r2, ..., rk with simple score bars.

Do not present the Top-1 root as confirmed ground truth.

M2 — LOCAL PROPAGATION SUPPORT MODELING

Label the second module:

“M2: Local Propagation Support Modeling”.

Feed it directly from Raw Physical Topology and Device Alarms, Logs, and Event Times.

Show one example physical adjacent pair u--v.

For this pair display three compact support bars:

“u→v”
“v→u”
“No Direct Propagation”.

Label them:
“Normalized Evidence Support”.

Add small blue evidence cues:
“Temporal”
“Alarm / Log Semantics”
“Interface / Peer”.

Add the note:
“Unknown ≠ No Direct”.

Make clear that M2 outputs uncertain local relation support, not selected propagation edges and not calibrated causal probabilities.

Show that this local support is reusable across multiple root hypotheses.

M3 — ROOT-CONDITIONED GRAPH RECONSTRUCTION

Label the third and visually most prominent module:

“M3: Root-Conditioned Graph Reconstruction”.

Feed both:
the purple Top-K Root Hypotheses from M1,
and the Local Propagation Support from M2.

Show several small branches:
“Assume root r1”
“Assume root r2”
“...”.

Each branch enters:

“Constrained Path Search & Graph Assembly”.

Show compact constraint labels:

“Raw Physical Edges”
“Local Evidence Support”
“Root Reachability”
“Acyclicity”.

Add a smaller subordinate note:

“Distance-increasing direction rule
(model assumption)”.

Do not present this rule as a universal property of network fault propagation.

Each root branch produces a small candidate propagation DAG.

Use orange only for selected propagation edges and purple only for the assumed root.

OUTPUT

On the right, show a large orange-highlighted:

“Incident-Specific Device Propagation Graph”.

Show:
one purple root node,
orange directed propagation edges,
small blue evidence-reference badges.

Below it show smaller subordinate outputs:

“Evidence References”
“Alternative Hypotheses”
“Diagnostic Status”.

If a candidate-root selection block is shown, label it neutrally:
“Root Score + Graph Explanation”.

Also include:
“Insufficient graph evidence:
retain root ranking”.

Do not imply that graph reconstruction always improves root-cause ranking.

VISUAL PRIORITY

The visual hierarchy must clearly communicate:

Incomplete Observations
→
Root Hypotheses
+
Local Propagation Support
→
Root-Conditioned Graph Reconstruction
→
Incident-Specific Device Propagation Graph.

M3 and the final propagation graph should be visually dominant.

Use M1/M2/M3 as conceptual module labels. A small grouping note may show Stage 1 = M1 and Stage 2 = M2 + M3 to match the implementation.
Do not include P0, P1, P4, LLM, multi-root recovery, supervised edge labels, ground-truth inputs, global-optimality claims, or causal-certainty claims.

Include a compact legend using exactly the same visual semantics as Figure 1:
Raw physical adjacency,
Observed evidence,
Root hypothesis,
Uncertain local relation,
Selected propagation edge.
```---

# 可选任务示意图（不替代新版 Figure 1 案例）

以下为通用任务示意的旧 prompt，仅保留作素材。不得作为 DEMO_001 的观测或实际模型输出。

## Figure 0 Prompt：task illustration
Create a publication-ready scientific task illustration for a paper on incident-specific device fault-propagation graph reconstruction.

The purpose of this figure is to visually explain:

1. what observations are available after a Pingmesh anomaly,
2. why suspicious-device ranking alone is insufficient,
3. what the device propagation graph reconstruction task outputs,
4. why such a structured output is useful for fault diagnosis.

Use a horizontal four-panel layout from left to right.

Use exactly the same visual language as the other figures in the paper:

- white or very light warm-gray background: #FCFCFB;
- near-black #111111 for text, borders, and primary workflow arrows;
- blue #1457FF for observed device events, Pingmesh context, physical topology context, and evidence references;
- purple #7A5AF8 for root hypotheses or candidate root devices;
- orange #FF4B1F for selected device-to-device propagation relations and reconstructed propagation graphs;
- light gray #E9E9E9 for inactive physical links, unresolved structure, and secondary elements.

Use a clean monoline scientific vector style, thin outlines, rounded rectangles, straight or orthogonal arrows, generous whitespace, and short English labels readable at two-column paper width.

No gradients, shadows, 3D effects, decorative illustrations, people, logos, watermarks, or unnecessary icons.

Label the entire figure:

“Task Illustration: From Pingmesh Anomaly to Device Propagation Explanation”

Use the same six devices throughout the figure:
R, A, B, C, D, and U.

Use the same raw physical topology whenever a topology is shown.

The raw physical topology contains exactly these undirected links:

R--A
R--B
A--B
A--C
B--C
C--D
B--U

Do not add any other physical link.

All raw physical links must be shown as thin light-gray lines unless specifically highlighted as part of the reconstructed propagation graph.

---

PANEL (a): INCOMPLETE INCIDENT OBSERVATIONS

Title:

“(a) Incomplete Incident Observations”

At the top, show a compact blue context card:

“Pingmesh Anomaly”

with two small endpoint symbols and the subordinate label:

“End-to-end anomaly context”

Do not draw a known packet-level forwarding route between the endpoints.

Below it, show the six-device raw physical topology.

Attach small blue observation cards to devices R, A, B, C, D, and U.

Use symbolic event labels such as:

eR
eA
eB
eC
eD
eU

Optionally add a few qualitative observation cues such as:

“earlier event”
“higher severity”
“sparse evidence”

Do not use fabricated timestamps, numerical probabilities, production statistics, or measured path traversal counts.

No device is a confirmed root.
No physical edge is shown as a confirmed propagation edge.

Add a short bottom caption:

“Mixed and incomplete device observations”

The visual message should be:

Pingmesh reports that a communication anomaly occurred, while alarms, logs, and topology provide only fragmented device-level evidence.

---

PANEL (b): DEVICE RANKING IS NOT ENOUGH

Title:

“(b) Device Ranking Is Not Enough”

On the left side of this panel, show a compact ranked list:

“Suspicious Devices”

with entries such as:

1. R
2. A
3. B
4. C

Highlight the listed devices with subtle purple markers.

Do not label the first device as a confirmed root.

Next to the ranking, show two or three small alternative graph sketches using the same devices.

For example, illustrate different possible relations such as:

R→A→C

R→B→C

R→A and R→B

Use dashed, uncertain arrows rather than solid selected propagation edges.

These mini-graphs are only conceptual alternatives and do not need to include every device.

Add a prominent short statement:

“Ranking tells where to inspect,
but not how devices are related.”

Below it add:

“Same devices, different propagation explanations”

The visual message should be:

A list of suspicious devices narrows the inspection scope but cannot reveal the directional influence relationships, branches, or propagation structure of this particular incident.

---

PANEL (c): OUR TASK — DEVICE PROPAGATION GRAPH RECONSTRUCTION

Title:

“(c) Incident-Specific Propagation Graph”

Make this panel visually dominant.

Show the same raw physical topology faintly in light gray in the background.

Mark R with a purple outline and label:

“Root hypothesis R”

Highlight only the following device propagation relations using solid orange directed arrows:

R→A
R→B
A→C
C→D

Every orange propagation edge must correspond to an existing raw physical link.

Do not add propagation edges that are absent from the raw physical topology.

Keep device U visible but outside the selected propagation structure.

Label U:

“Unattributed event”

Optionally show B→C as a dashed unresolved relation outside the selected graph, labeled:

“Alternative relation”

Attach small blue evidence-reference badges to selected orange edges, such as:

E1
E2
E3

These represent supporting alarm/log/event observations and must not be shown as ground-truth causal proof.

Around the reconstructed graph, add three compact callouts:

“Incident participants”

“Directional influence”

“Paths and branches”

At the bottom add:

“Structured, inspectable device-level explanation”

The visual message should be:

The task is not merely to identify suspicious devices, but to recover which devices participate in the incident and how supported directional relations form an incident-specific propagation structure.

Do not label this graph as:
“Ground Truth”
“Actual Fault Path”
or
“True Causal Graph”.

Use:
“Reconstructed Explanation”
or
“Root-Conditioned Explanation”
if an additional label is needed.

---

PANEL (d): WHY IT MATTERS

Title:

“(d) Why It Matters”

Do not introduce another complex topology.

Instead, show three compact vertically stacked value blocks connected from the reconstructed propagation graph.

Value block 1:

“Trace Fault Influence”

Subtext:

“Follow the incident from a candidate origin through affected devices”

Value block 2:

“Support Operator Inspection”

Subtext:

“Check devices and supporting evidence edge by edge”

Value block 3:

“Separate Incident-Relevant Events”

Subtext:

“Distinguish propagation participants from unrelated observations”

Optionally include a fourth smaller block if space permits:

“Explain Diagnosis Results”

Subtext:

“Provide structure beyond a suspicious-device ranking”

Use small orange graph symbols and blue evidence badges sparingly.

The panel should emphasize operational interpretability rather than claiming causal certainty.

---

OVERALL FLOW

Use a clear left-to-right visual progression:

Pingmesh anomaly + device observations
→
Suspicious device ranking
→
Incident-specific device propagation graph
→
Inspectable fault explanation

Place small near-black workflow arrows between the four panels.

The main conceptual contrast should be:

“Which devices are suspicious?”
versus
“How are the devices related in this incident?”

Make the third panel, the reconstructed device propagation graph, the visual center of gravity.

---

LEGEND

Include one compact shared legend at the bottom or upper-right corner.

Use exactly these semantic categories:

“Raw physical adjacency”
— thin light-gray undirected line

“Observed device event”
— blue event badge

“Root hypothesis”
— purple node outline

“Uncertain relation”
— dashed directed arrow

“Selected propagation relation”
— solid orange directed arrow

Do not use different visual semantics from the motivation or RPG-Recon framework figures.

---

SCIENTIFIC CAUTION

The figure must not imply that:

- Pingmesh directly observes device-level propagation;
- temporal order proves causality;
- alarm severity proves causal direction;
- all alarmed devices belong to the same incident;
- the highest-ranked device is necessarily the true root;
- the reconstructed graph is uniquely identifiable from the displayed observations;
- the orange propagation graph is ground truth.

The intended message is:

Incomplete endpoint and device observations can identify suspicious devices, but understanding an incident additionally requires reconstructing a structured device-level propagation explanation that organizes supported directional relations under a candidate root hypothesis.