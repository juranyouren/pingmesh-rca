# www24-mulan — MULAN: Multi-modal Causal Structure Learning and Root Cause Analysis for Microservice Systems

| 字段 | 值 |
| --- | --- |
| 年份 / 轨道 | 2024 / WWW Research Track |
| 正式题名 | MULAN: Multi-modal Causal Structure Learning and Root Cause Analysis for Microservice Systems |
| DOI | 10.1145/3589334.3645442 |
| 原始 PDF | www24-mulan.pdf（来源：arXiv 2402.02357；版本：arXiv v1，2024-02-04，共 11 页） |
| 抽取文本 | tmp/www-web-relevance/txt/www24-mulan.txt |
| Introduction 定位 | www24-mulan.intro.md，PDF 第 1–2 页，P1–P43（P3/P42 为作者块，分页把挑战列表切碎） |
| 深读状态 | 已深读（全文 11 页；Tables 2–4 数值格未进入抽取文本，见 §6） |

**版本与身份差异（须记录）**：① PDF 首页题名只有 "Multi-modal Causal Structure Learning and Root Cause Analysis"，缺少 "MULAN:" 与 "for Microservice Systems" 后缀；摘要正文出现 MULAN，作者与单位（NEC Labs America / UIUC）一致，判定为同一工作。② 抽取文本运行页眉为 ACM 模板占位符 "Conference'17, July 2017, Washington, DC, USA"（全文 10 次），说明拿到的是投稿版式而非 WWW'24 正式排版，本文页码不等于 ACM 正式版页码。

## 1. 问题定义

【作者陈述】输入是系统 KPI 时间序列 y、多模态微服务数据（指标时间序列 + 非结构化日志）；目标是构造因果图 G={V,A}，据此找出与 y 最相关的 top-k 系统实体（§2 Problem Statement，PDF p.3）。【作者陈述】输出因此是**一个排序的根因实体列表**，图 G 只是中间产物；评价只用 PR@K / MAP@K / MRR（§4.2，PDF p.6）。使用者被设定为微服务运维。研究对象是"系统实体"（pod / 容器 / VM / pod 级 Kubernetes 条目），不是网络设备。

## 2. Web 关联

> **2026-09-12 T006 更正（覆盖本节原有结论）**：本节原判"只剩会议归属"**不成立**，
> 属 T005 验收 R1 指出的"用字频替代相关性分析"。更正后的结论见 §10.1，三栏分别为：
> **作者显式叙述 = 无**；**工作负载提供的联系 = 有**（三个数据集都是 Web 应用系统）；
> **业务收益验证 = 无**。字频检索只能支撑第一栏，不能推出后两栏。

【实验支持】我对全文做大小写不敏感检索，"web" 仅出现 3 次，**全部在参考文献**（WWW'21、WWW'20 等），正文 0 次。引言 P1 只写 "real-world complex systems"、"pod-level Kubernetes entries"；关键词写 "Microservice Systems"。因此就**作者显式叙述**而言，MULAN 连 GAMMA 那种 "web application" 措辞都没有。去掉 Web 术语，技术主张一字不变。——**但这句话仅适用于"作者怎么写"，不适用于"研究对象是什么"**，见 §10.1。

## 3. 段落作用

P1 背景→重要性（RCA 影响用户体验与财务损失）；P2/P4 现有工作（因果发现建图，[21] 条件独立性检验、[46,47] 层次 GNN）；P5 缺口（单模态捕捉不到异常模式，Table 1 举例：Database/Login Failure 需日志，Disk Space Full 需指标+日志同看）；P6 多模态学习在其他领域成熟、在 RCA 未探索；P7 任务形式化；C1/C2/C3 三大挑战（日志表示、模态共同/特有信息、模态可靠性）；P33 四模块方法总览；P35–P41 三条贡献；P43 章节安排。

## 4. 现有工作与缺口

【作者陈述】具体批评三处：(a) 依赖单一模态的因果发现 "failing to capture the intricacies of various abnormal patterns"（P5）；(b) 已有因果发现方法（条件独立性、层次 GNN）只用指标数据；(c) 已有**多模态** RCA [18,54] "primarily aim to extract information from individual modalities, often missing the potential interplay between them"（P6），且把两模态同等对待，在低质量模态下退化（C3）→ 方法：log-tailored LM、对比学习（不变/特有表示）、KPI-aware attention 融合。缺口落在"模态交互与可靠性"，**不在"图不可审计"**。

## 5. 核心洞察与贡献

任务定义贡献：把多模态因果结构学习引入微服务 RCA（相对新）。方法贡献：KPI-aware attention 的模态重加权（Eq.9–11，§3.3，PDF p.5）+ node/edge 级对比正则。评价贡献弱：沿用 PR@K/MAP@K/MRR。真正立身之本是**低质量模态下的鲁棒性**，作者把它写成贡献清单第二条（P37–P39）。

## 6. 证据强度

【作者陈述】引言称 "Extensive experimental results with real-world datasets"（P33/P40）。【实验支持】支撑在 §4.4.1（PDF p.7，Tables 2–4）：MRR 在 Product Review 超 REASON 12.5%，在 Online Boutique 超 Nezha 13.2%（MRR）/ 8%（MAP@5）。鲁棒性主张支撑在 §4.4.2 与 Fig 3（PDF p.8），模态权重自适应见 Fig 3(c)。消融 §4.4.4 / Table 5（PDF p.8）：去掉 edge loss 分别掉 16.7%、23.3%，去掉 node loss 掉 18.7%。

问题点：(a) "real-world" 与实际来源有落差——三个数据集是 Product Review（234 pods / 6 台云服务器 / 4 个故障，2021-05 至 2021-12）、Online Boutique（5 个故障）、Train Ticket（5 个故障），后两者标注引 [54]=Nezha。【本次推断】Online Boutique 与 Train Ticket 是公开微服务演示应用基准，其"故障"来自故障注入实验；【实验支持】全文检索 "inject" 命中 0 次，论文**从未交代故障如何产生**。(b) 日志模态训练标签 y_log 由现成日志异常检测器（OC4Seq/DeepLog）产生（§3.1 Phase 2/3，PDF p.3），不是真值。(c) Tables 2–4 数值格在抽取文本中丢失（只剩指标名与行名），无法逐格复核。(d) **只测了排名，却全程以 "causal structure learning" 自称**：无任何边级/图级指标，图从未被单独评测。

## 7. 与本项目（RPG-Recon）的关系

- 可借鉴的论证步骤：用一张"故障类型 × 证据模态"的交叉表（Table 1）直观证明"单类证据必然漏检"，我们的 alarms/logs + task_topo + Pingmesh 可做同构的证据覆盖论证。
- 不能迁移的前提：需要 (i) 每个故障的真值根因集合（PR@K 的分母）；(ii) 覆盖全部实体的密集指标时间序列；(iii) 外部日志异常检测器造标签。我们没有注入式真值根因，标签语义尚未冻结。
- 潜在重合与差异：都走"建图 + 传播假设（随机游走）"路线（§3.4，PDF p.5）。但 MULAN 的 A 是**可学习邻接矩阵**，仅受无环约束（Eq.12，PDF p.5），无任何拓扑约束，边可以不对应任何真实关系；输出是 top-k 排名。我们的边必须存在于 raw task_topo、未知关系 mask 而非当负样本、根是竞争候选集、输出是 root-conditioned 可逐边审计的 DAG，并显式标出证据缺口。

## 8. Reviewer 视角

- 去掉 Web 术语论证**完全成立**（本来就没有 Web 论证）；进 WWW 的理由仅剩"微服务系统属 Web 基础设施"这一层级。
- 最可能被质疑：数据集 "real-world" 性质与故障来源不透明；图未被评测却自称学因果结构；日志表示的实现细节未充分公开。
- 我们应避免：只报排名却宣称交付了结构；把第三方基准含糊成 real-world；正文只给百分比而不给可核对的数值。

## 9. 原文定位索引

Table 1（p.1）；§2 Problem Statement（p.3）；§3.1 日志表示（p.3）；§3.3 KPI-aware attention / Eq.12（p.5）；§3.4 随机游走（p.5）；§4.1.1 数据集（p.5–6）；§4.2 指标定义（p.6）；§4.4.1 与 Tables 2–4（p.7）；§4.4.2 与 Fig 3（p.8）；§4.4.4 / Table 5（p.8）；Fig 1（p.3）、Fig 2（p.4）。

## 10. T006 复核更正（2026-09-12）

### 10.1 §2 的"只剩会议归属"判断作废（T005 验收 R1）

**更正后的三栏**（T006 要求的 A/B/C 三分，见 [argument_chains.md](../../argument_chains.md) §6.2）：

| 维度 | 结论 |
| --- | --- |
| **A. 作者如何表述相关性** | **无。** 引言 P1 只写 "real-world complex systems"，正文 "web" 出现 0 次。此栏原判断正确。 |
| **B. 对象与工作负载实际提供了什么联系** | **有。** §4.1.1（PDF p.5–6）的三个数据集都是 **Web 应用系统**：① Product Review——"a microservice system dedicated to **online product reviews**"；② **Online Boutique**——"a microservice system designed for **e-commerce**"；③ **Train Ticket**——铁路售票服务。其中 Online Boutique 是 Google 公开的 Web 电商微服务演示应用。 |
| **C. 实验证明了什么效果** | **在上述三个 Web 应用系统上验证了根因排名效果**（PR@K / MAP@K / MRR）。**未测这些系统的用户侧或业务侧收益。** |

**为什么原来的推论不成立**：字频只测量 A 栏。"正文没有 Web 术语"与"研究对象不是 Web 系统"
是两件事；把前者当作后者的证据，等于用措辞判断对象。
**正确写法**：MULAN 的 Web 联系属于**工作负载提供的联系**——
引言未论证，联系由评测数据集的系统属性提供。按 T006 纪律，这类联系
**必须单列，不得改写成"作者引言已经论证"**。

**这一条对本项目有直接价值**：它说明"实验负载是 Web 系统"可以构成一种真实存在的
（尽管薄弱的）关联方式，而它**不需要作者在引言里写任何 Web 论证**。
反过来也提醒我们：`www24-inart` 的负载是 Cifar-10 图像分类，
**连这一层联系都没有**。[argument_chains.md](../../argument_chains.md) §5.1 已记录。

**2026-09-12 T006-R 追加更正（验收 R5）**：本节初稿把 C 栏写成"与 Web 无关"，
理由是"评价用排名指标"——**推理不成立**，那是把**指标类型**当成了**对象相关性**。
评测对象恰恰是三个 Web 应用系统的根因排名。正确写法见上表 C 栏。
同理，`www24-gamma` 的对应判断也已更正。**"用排名指标" ≠ "与 Web 无关"。**

### 10.2 Intro 段落号

本卡第 10 行记"P1–P43（P3/P42 为作者块…）"。本轮确认 **P3 是作者块**（NEC Labs America / UIUC
姓名行），并补充：P1–P2 之后正文继续，**P8 起是 C1/C2/C3 挑战列表的碎片**，
与 InArt/WiseStart/JitterSketch 的贡献 bullet 碎片是同一类抽取噪声。
引用 Introduction 时请以**段落的实际功能**为准，不要按 P 编号计数。

### 10.3 本轮引用的锚点

Intro P1（"real-world complex systems"）；§4.1.1 三个数据集（PDF p.5–6）；
§4.2 指标定义（PDF p.6）。均在 arXiv 2402.02357v1 页码下——**需注意该版式是 ACM 模板
占位符页眉（"Conference'17, July 2017"），不是 WWW'24 正式排版**（本卡开头已记录）。
