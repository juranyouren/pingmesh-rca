# comp25-flow-of-action — Flow-of-Action: SOP Enhanced LLM-Based Multi-Agent System for Root Cause Analysis

| 字段 | 值 |
| --- | --- |
| 年份 / 轨道 | 2025，WWW **Industry Track**，刊于 Companion 卷（WWW Companion '25, Sydney）——**不是 Research Track** |
| 正式题名 | Flow-of-Action: SOP Enhanced LLM-Based Multi-Agent System for Root Cause Analysis |
| DOI | 10.1145/3701716.3715225（**已核对**：PDF 第 1 页 front matter 与 ACM Reference Format 两处均印出，非 DOI UNKNOWN） |
| 原始 PDF | comp25-flow-of-action.pdf（来源：arXiv 2502.08224；版本：正文为 ACM camera-ready 排版，含 WWW Companion '25 页眉，ACM ISBN 979-8-4007-1331-6/2025/04，10 页） |
| 抽取文本 | tmp/www-web-relevance/txt/comp25-flow-of-action.txt（10 页） |
| Introduction 定位 | comp25-flow-of-action.intro.md，PDF 第 1–3 页，P1–约 P20（该文件抽到第 7 页，P20 之后已进入 §2/§3） |
| 深读状态 | 已深读（§1、§2、§3.1–§3.4、§4、附录 A）。**未核对**：Table 3（各方法 LA/TA/APL 数值）的表体在抽取文本中整体缺失，只剩表注；Table 1、Table 2 亦只见表注 |

## 1. 问题定义

研究对象是**微服务架构（MSA）下的根因定位与根因类型分类**。输入是 Kubernetes 环境的多模态数据（metric / log / trace）、运维 API 工具集、SOP 知识库与历史事件库【作者陈述】（§2.1–§2.2，PDF p.3–4）。输出是**根因位置 + 根因类型两个标签**，不是图、不是路径、也不是故障传播结构【作者陈述】（§3.1.2，PDF p.6）。使用者是 SRE【作者陈述】（P3，PDF p.2）。

**为何值得研究**：论文的动机不是网络，而是"线上大规模 Web 服务在微服务化后故障频发、损失可观"。引言举的唯一具体例子是 2023-11-12 阿里云大故障（多服务中断近三小时）【作者陈述】（P2，PDF p.2）。作者对现有深度学习 RCA 的两条批评是：适应性差、需重训；只给根因不给诊断过程，可解释性差导致 SRE 不信任【作者陈述】（P3，PDF p.2）。

## 2. Web 关联

> **2026-09-12 T006-R 旁注（本卡本轮未被引用，不做全面返工，留待 T005-R 统一处理）**：
> 下面"与 Web 无关"的判断沿用了 T006 已更正的推理方式——
> **"用排名指标"或"未测页面指标"不等于"与 Web 无关"**；该实验系统本身是电商微服务。
> 本节末的"把 web 换成 online service 后主张不变"同理，只说明**适用范围**，不是不相关的判据。

关联出现在**引言首句**："In today's large-scale web systems and services..."（P1，PDF p.1）。【本次推断】这是纯场景限定词，且近乎英语惯用搭配。全文没有研究任何 Web 协议、Web 基础设施或 Web 测量对象；引用的 WWW 系工作（[1] Causil、[24] GAMMA、[28] ReVAVE、[37] MULAN）全部是 microservice RCA，作者借此把"WWW 的微服务/RCA 传统"当作领域归属。实验系统是 GoogleOnlineBoutique（一个演示用电商微服务），**未测 Web 服务侧收益**【作者陈述】（§3.1.1，PDF p.6）。

把 "web" 换成 "online service" 后论文主张完全不变。因此本篇属于**"仅领域命名（microservice systems）"型关联**。

**关键限定**：本篇发表于 WWW **Industry Track / Companion 卷**。它可以作为我们**写作**上的参考（尤其是"把 LLM 幻觉翻译成动作选择问题"这一修辞），但它**不能作为 Research Track 接受某类 framing 的证据**——Industry Track 的评审口径与 Research Track 不同，把它的关联写法当作研究轨道的先例是无效论证。此点必须写进综合矩阵。

## 3. 段落作用（P1–约 P20）

- **P1/P2（PDF p.1–2）**：背景。单体应用的三重困境（部署复杂、扩展受限、迭代频繁）→ 微服务化的收益 → 实例数量与多样性上升 → 故障频发 → 阿里云案例。功能：background → 后果的实感化。
- **P3（PDF p.2）**：三层推进。① RCA 是 AIOps 的热门方向；② 传统深度学习方法两条缺陷（适应性差、不可解释导致不信任）；③ LLM agent（ReAct、ToolFormer）能展示完整排查过程——随即转入"但是"：**Challenge 1（随机性与幻觉导致不合理动作选择）**。功能：现有工作 → 缺口 → 挑战。
- **P3 末–P4（PDF p.2）**：**Challenge 2（观测复杂多变导致多个合理动作）**，并用 Figure 1 给一个具体二选一（code error "Service name not found"，根因可能在代码生成或 SOP 文档，因而可行动作有再生成代码或修订文档）。功能：用一张小图把抽象挑战具体化——这是本篇写得最好的一处。
- **P5（PDF p.2）**：方案概述。三条：SOP 进知识库形成 SOP flow；thought-**actionset**-action-observation 范式替代 thought-action-observation；多 agent 分工（MainAgent / CodeAgent / JudgeAgent / ObAgent / ActionAgent）。
- **P6（PDF p.3）**：四条贡献（框架 / SOP 概念 / 多 agent 协作 / 实验提升）。
- 后续 §2 是系统设计（知识库、工具三分、SOP flow 四个子流程、动作集、MAS），§3 是评测。

引言全部是定性叙述，**唯一数字是阿里云故障**；"降低 trial and error 成本"是动机陈述，没有任何引言层面的自测数字【本次推断】。

## 4. 现有工作与缺口

抽取文本中**未找到独立的 Related Work 节**（§2 直接进入系统设计）；相关工作散落在 §1 的 P3 与 §3.2 RQ1。我按 "Related Work" 与 "related work" 检索全文，均无命中。

实际批评（均具体）：① 传统深度学习 RCA "poor adaptability to new scenarios, requiring model retraining"、"only output the root cause... without providing the entire diagnostic process"（P3，PDF p.2）；② K8SGPT "primarily queries Kubernetes metadata... often insufficient for RCA, as faults may not necessarily manifest in metadata"；③ HolmesGPT 与 K8SGPT 因只支持一类故障而固定得 11.11；④ Reflexion "given that previous paths are predominantly incorrect, reflecting on a wealth of erroneous knowledge makes it arduous to arrive at accurate insights"（§3.2 RQ1 与 Table 3 表注，PDF p.7）【作者陈述】。缺口 → 方法的推导是"给编排加软约束 + 先出动作集再决策"。

## 5. 核心洞察与贡献

- **任务定义贡献**：主张这是"首个以 SOP 为中心的 agent 故障定位流程"（§1 贡献条，PDF p.3）【作者陈述】。
- **方法贡献**：thought-**actionset**-action-observation 范式；SOP→SOP code→run_sop 工具链（把 SOP 编译成代码一次性执行，理由是"代码执行比文本执行准"且可减少 token 消耗）【作者陈述】（§2.3.2，PDF p.6）；延迟公平之外，五 agent 分工含 JudgeAgent（判停）与 ObAgent（降噪）【作者陈述】（§2.3.4–2.4，PDF p.6）。
- **系统实现贡献**：完整 agent 系统（代码未开源，抽取文本中未见仓库链接）【本次推断】。
- **工程/评价贡献**：在 GoogleOnlineBoutique（10+ 服务，K8s；Prometheus + Elastic + DeepFlow + Jaeger 采集，ChaosMesh 注入）上构造 **90 条事件、9 类故障**的数据集【作者陈述】（§3.1.1，PDF p.6）。
**立身之本**是"SOP 软约束 + 动作集"这一组合把 ReAct 的 35.50% 提到 64.01%（摘要，PDF p.1）。

## 6. 证据强度

- "35.50% → 64.01%"只出现在摘要（PDF p.1）；正文 §3.2 RQ1（PDF p.7）改写为"超越 SOTA 23%（LA）与 28%（TA）"。**Table 3 表体在抽取文本中整体缺失**，我无法逐方法核对这两个数字，只能确认方向与量级一致【本次推断】。
- LLM 主干是 **GPT-3.5-Turbo**（Table 4 表注，PDF p.8）【作者陈述】——基线偏弱，这是最强的对比条件质疑点【本次推断】。
- 评测口径存在**对 LLM 方法有利的人为上限**：最多 3 个根因、最大 20 步（§3.1.2 与 §3.4，PDF p.6/p.8）【作者陈述】；论文未对这些上限做敏感性分析（除 APL 外）【本次推断】。
- 数据规模真实但**只是仿真注入**：单套 demo 微服务、9 类 Chaos 故障、90 条事件，无生产事件、无真实故障工单【作者陈述】（§3.1.1，PDF p.6）。
- **"只测 X 却声称 Y"**：摘要在"real-world 电商系统的故障注入仿真平台"上测得 64.01% 后直接写 "meeting the accuracy requirements for RCA in real-world"，但正文没有给出该"要求"的来源、阈值或引用【本次推断】（这是本篇最明显的一处）。此外索引里提到 GoogleOnlineBoutique 是公开演示项目，并非"real-world e-commerce system"的严格表述【本次推断】。
- 消融（Table 4，PDF p.8）显示去 SOP 后≈退回 ReAct、去 action set 后复杂场景失败——**这一部分证据方向与结论自洽，是本篇最扎实的实验**【本次推断】。

## 7. 与本项目（RPG-Recon）的关系

**可借鉴的论证步骤**：(a) 把"模型会幻觉"翻译为"**动作选择不合理**"这一可失效、可度量的具体失败模式，再配一张 Figure 1 式的二选一小图把挑战具象化——我们在写 C2（设备关系与方向含糊）与 C3（局部支持不成图）时可直接复用这个手法：不要停在"不确定"，而要给出一个两条边都说得通的具体情形；(b) 明确区分"输出根因"与"输出诊断过程"，并把后者作为可解释性卖点——我们的 DAG 正是"过程"而非"答案"，这条论证可直接引用；(c) 用 JudgeAgent 把"该停就停"变成显式机制——对应我们必须处理的 abstention / fallback 与"失败必须计入分母"的问题。

**不能迁移的前提**：(i) 他们能在同一套系统上反复注入故障并取得**确定的根因标签**；我们没有真实事件、没有注入平台、标签还有争议；(ii) 他们的 SOP 来自工程师撰写或自动抽取——我们**没有现场调研记录**，不可写作前提；(iii) 他们有完整多模态监控栈（Prometheus/Elastic/DeepFlow/Jaeger）。三者都不具备。

**潜在重合与差异**：SOP 约束 LLM 与我们的 **P0 确定性证据规范化**在做同一件事——用外部结构化知识压制模型自由度。差异在约束的硬度与来源：他们的 SOP 是人工/半自动的**软约束**（作为 prompt 提示 MainAgent 大致遵循，§2.3 明言"soft constraints"、不强制严格工作流），我们的 P0 是**可检查的硬约束**（每条边必须存在于 raw task_topo、未知关系必须掩码、距离规则严格递增）。我们更强，但也因此承担"规则可能排除已标注边"的风险（与 CLAUDE.md 中对 P0 建模局限的说明一致）。另一处重合：SOP 的层级式"先网络后网络分区"（§2.3.1，PDF p.5）与我们的分层定位思路相似。最大差异点是**输出**：他们是"位置 + 类型"两个标签，我们是图；这既是我们的贡献空间，也是我们要自证比它更难的地方。

## 8. Reviewer 视角

- **去掉 Web 术语，论证完全成立**。且因本篇为 Industry/Companion 论文，**只能作为写作参考，不能作为 Research Track 接受该 framing 的证据**——这是本卡最重要的限定。
- **最可能被质疑**：① 单系统、90 条注入、主干模型 GPT-3.5-Turbo；② 摘要 "real-world" 的用词强于实际证据；③ 步数上限 20、根因数上限 3 对 LLM 方法有利；④ 无生产部署、无 SLO/MTTR 收益测量。
- **值得我们避免**：(i) 引言用宏观产业损失（阿里云）制造紧迫感，正文却只有单套 demo 系统的注入实验——动机与证据的规模不匹配，这是本项目最容易重犯的错误（我们的 CLAUDE.md 已明确禁止编造生产案例与 SLO/MTTR 收益）；(ii) 抄它 "meeting the accuracy requirements for RCA in real-world" 这类**无出处的标准声明**；(iii) 在摘要里报一个正文只在别处出现过的数字组合（35.50%/64.01% vs 23%/28%）。

## 9. 原文定位索引

- 引言：PDF p.1–3（P1–约 P20）；Web 关联首句 p.1 P1；阿里云案例 p.2 P2；两条传统方法缺陷 p.2 P3；Challenge 1 p.2 P3；Challenge 2 与 Figure 1 p.2 P4；方案概述 p.2 P5；四条贡献 p.3 P6（贡献条列于 PDF p.3）
- §2 系统设计：§2.1 知识库（SOP 知识 / 历史事件）PDF p.3；§2.2 工具三类 PDF p.3–4；Table 1 SOP flow 工具描述 PDF p.4；§2.3 SOP flow 四个子流程 PDF p.4–6（§2.3.1 层级 SOP、§2.3.2 SOP→代码、§2.3.3 run_sop、§2.3.4 match_observation）；§2.4 动作集与 MAS PDF p.6
- §3 评测：§3.1.1 数据集（GoogleOnlineBoutique、ChaosMesh、9 类故障、90 条事件）PDF p.6；§3.1.2 指标（LA / TA / APL，最多 3 个根因）PDF p.6；§3.2 RQ1 与 Table 3 PDF p.7；§3.3 RQ2 动作集大小 PDF p.7；§3.4 消融与 Table 4 PDF p.8
- 图/表：Figure 1（p.2 挑战示例）、Figure 2（p.3 多模态采集）、Figure 3（p.3 ReAct 与 FoA 对比）、Figure 4（p.5 运行示例）、Figure 5（p.5 SOP flow prompt）、Figure 6（p.5 自动生成的 SOP）、Figure 7（p.7 动作集大小与准确率）、Table 1（p.4）、Table 2（p.6 故障类型）、Table 3（p.7）、Table 4（p.8）
- 附录 A 多模态数据采集：PDF p.9（Prometheus 架构级指标、DeepFlow 业务级指标、规则法异常检测）
- 未找到：独立的 Related Work 节（按 "related work" 检索无命中）；Table 3 表体数值；代码仓库链接；"real-world accuracy requirement" 的任何出处
