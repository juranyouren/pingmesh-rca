# 文献调研补充：信任门控与 LLM 在 RCA 中的角色

## 1. 为什么需要补充这一块

本文当前方案的核心不只是“拓扑 + 时序 + LLM”，而是：

> 先由确定性拓扑-时序排序器产生候选，再由 Trust-Tree Gate 判断是否自动接受、调用 LLM 仲裁，或交给人工复核。

因此，相关工作不能只写“LLM for RCA”，还需要补上两条文献线索：

1. **选择性预测 / 拒识 / 低置信转人工**：为 Trust-Tree Gate 提供机器学习层面的理论支撑。
2. **LLM 在 RCA 中的有限角色**：说明 LLM 适合语义理解、证据整合和工具调用，但不适合无约束地替代确定性 RCA 算法。

## 2. Trust-Tree Gate 的文献定位

### 2.1 选择性预测：模型不确定时应拒绝输出

Selective Classification / Selective Prediction 研究的是：模型在低置信样本上可以拒绝预测，从而在覆盖率和错误率之间做权衡。Geifman 和 El-Yaniv 的工作将该思想引入深度神经网络，强调“risk-coverage tradeoff”：不是所有样本都必须自动输出，模型可以用覆盖率换取更低风险。

与本文的对应关系：

| 选择性预测概念 | 本文对应设计 |
| --- | --- |
| prediction with reject option | `operator_review` 或 `invoke_llm` |
| selective risk | 自动接受 case 的错误率 |
| coverage | 自动接受 case 占比 |
| confidence function | topo/temporal trust-tree 状态 |

本文的 Trust-Tree Gate 可以解释为一个面向 RCA 的选择性预测器：高置信 case 自动输出，冲突 case 调用 LLM，弱信号 case 拒绝自动诊断并交给人工。

可引用文献：

- Geifman and El-Yaniv, *Selective Classification for Deep Neural Networks*, NeurIPS 2017.
- Geifman and El-Yaniv, *SelectiveNet: A Deep Neural Network with an Integrated Reject Option*, ICML 2019.

### 2.2 LLM abstention：大模型也需要知道自己何时不应回答

LLM abstention 研究关注大模型何时应该拒答或表达不确定，以减少幻觉和错误输出。近期综述将 abstention 看作 LLM 安全性和可靠性的重要机制，尤其适用于高风险任务。

与本文的对应关系：

| LLM abstention | 本文对应设计 |
| --- | --- |
| refuse to answer when uncertain | weak-signal case 不让 LLM 强行给 IP |
| mitigate hallucination | 避免 LLM 在证据不足时编造根因 |
| human-value perspective | operator review 保留人工判断 |

本文与普通 LLM abstention 的区别在于：不是让 LLM 自己判断是否拒答，而是先由可解释的拓扑/时序信任树决定是否让 LLM 介入。

可引用文献：

- Wen et al., *Know Your Limits: A Survey of Abstention in Large Language Models*, 2024.
- Geng et al., *A Survey of Confidence Estimation and Calibration in Large Language Models*, 2024.

### 2.3 RCA confidence estimation：给根因推荐打置信分

LM-PACE 明确把 confidence estimation 用到云故障 RCA 中：它为模型生成的根因推荐分配校准置信度，帮助 on-call engineer 判断是否采用推荐结果。该方向与本文的 gate 很接近，但本文不直接依赖 LLM 自评置信度，而是用确定性证据树做路由。

对比：

| 方向 | 核心机制 | 风险 |
| --- | --- | --- |
| LM-PACE | LLM/RAG 生成根因推荐置信度 | 置信度可能受 LLM 校准误差影响 |
| 本文 Trust-Tree Gate | topo/temporal 规则树判断可接受性 | 规则需要通过实验验证覆盖率与错误率 |

可引用文献：

- Zhang et al., *LM-PACE: Confidence Estimation by Large Language Models for Effective Root Causing of Cloud Incidents*, FSE 2024 Industry Track.

### 2.4 混合统计-LLM gate：COLA 是最接近的直接类比

COLA 是告警聚合领域中非常重要的类比工作。它先用统计相关挖掘处理大部分告警对，只把低置信、不确定的告警对送入 LLM reasoning 模块。该设计直接支撑本文的“确定性算法优先、LLM 只处理不确定 case”。

与本文的对应关系：

| COLA | 本文 |
| --- | --- |
| correlation mining | topo + temporal deterministic rankers |
| uncertain pairs | ranker disagreement / weak evidence case |
| LLM reasoning | LLM arbitration |
| alert aggregation | root-cause device ranking |

COLA 的意义在于证明：在大规模运维场景中，LLM 不应全量接管任务，而应作为高成本语义推理模块，只处理统计方法低置信的部分。

可引用文献：

- Kuang et al., *Knowledge-aware Alert Aggregation in Large-scale Cloud Systems: a Hybrid Approach*, ICSE 2024.

## 3. LLM 在 RCA 中的角色分类

### 3.1 角色一：Incident 文本理解与根因/修复建议生成

早期 LLM for incident management 工作主要把 LLM 用于 incident report、日志、诊断材料的文本理解，并生成 root cause 和 mitigation 建议。

代表工作：

- Ahmed et al., *Recommending Root-Cause and Mitigation Steps for Cloud Incidents using Large Language Models*, ICSE 2023.
- Chen et al., *Automatic Root Cause Analysis via Large Language Models for Cloud Incidents / RCACopilot*, EuroSys 2024.

对本文的启发：

LLM 擅长把半结构化/非结构化运维信息转化为解释性文本，但这类方法通常输出 root-cause category 或 narrative，不一定能直接处理 DCN 设备级 Top-K 排序。

### 3.2 角色二：工具增强 Agent，负责收集和组织证据

RCAgent、TAMO 等工作把 LLM 放入 agent 框架，让 LLM 调用工具、收集指标、组织多模态证据，再输出 RCA 结果。

代表工作：

- Wang et al., *RCAgent: Cloud Root Cause Analysis by Autonomous Agents with Tool-Augmented Large Language Models*, 2023/2024.
- Wang et al., *TAMO: Fine-Grained Root Cause Analysis via Tool-Assisted LLM Agent with Multi-Modality Observation Data*, 2025.

对本文的启发：

LLM 不应直接读原始海量遥测，而应通过工具获得结构化证据。本文中的 topo ranker、temporal ranker、node summarizer 可以视为专用 RCA 工具，LLM 只消费压缩后的 evidence table。

### 3.3 角色三：生产网络故障定位中的辅助诊断器

BiAn 是最贴近本文网络场景的工作。它面向生产级网络故障定位，使用多阶段 LLM agent 从监控数据中生成设备排名和解释，并在生产环境中辅助运维人员缩短定位时间。

代表工作：

- Wang et al., *Towards LLM-Based Failure Localization in Production-Scale Networks*, SIGCOMM 2025.

与本文的区别：

| BiAn | 本文 |
| --- | --- |
| LLM agent 是主分析路径 | deterministic ranker 是主路径 |
| LLM 生成设备排名和解释 | LLM 只仲裁冲突/低置信 case |
| 面向生产网络多源监控 | 面向 Pingmesh-triggered DCN case |
| 强调 operator assistance | 强调 gate-controlled automation |

本文可以把 BiAn 作为直接 baseline 或最重要的相关工作：同样使用 LLM 辅助网络故障定位，但本文更强调算法排序可信时不调用 LLM。

### 3.4 角色四：LLM RCA 能力边界的反证

OpenRCA 和 LLM reasoning failure 系列工作说明：LLM 在复杂 RCA 上仍然有明显局限，尤其是多跳因果、长上下文遥测、证据选择和信念更新。

代表工作：

- Xu et al., *OpenRCA: Can Large Language Models Locate the Root Cause of Software Failures?*, ICLR 2025.
- Riddell et al., *Stalled, Biased, and Confused: Uncovering Reasoning Failures in LLMs for Cloud-Based Root Cause Analysis*, 2026.
- Kim et al., *Why Do AI Agents Systematically Fail at Cloud Root Cause Analysis?*, 2026.

对本文的启发：

这些工作为“LLM 不应无约束主导 RCA”提供了反向证据。本文的 gate-controlled LLM arbitration 可以被写成对这些局限的工程回应：减少 LLM 处理范围、降低错误传播风险、用确定性证据约束其输出。

## 4. 本文相关工作中的推荐写法

建议在论文相关工作中新增一个小节：

### 2.x Trust-Gated and LLM-Assisted RCA

可以按如下逻辑写：

1. 传统 selective prediction 研究表明，在高风险任务中，模型可以通过拒识低置信样本降低自动输出风险。
2. LLM abstention 和 confidence calibration 进一步说明，大模型在不确定时应表达不确定或转交人工。
3. RCA 领域已有 LM-PACE 等工作为根因推荐估计置信度，帮助工程师判断是否采纳。
4. COLA 在告警聚合中采用“统计挖掘优先，只把不确定样本交给 LLM”的混合范式，与本文方法最接近。
5. 现有 LLM RCA 系统如 RCACopilot、RCAgent、TAMO、BiAn 证明 LLM 可用于语义理解、证据整合和 operator assistance，但 OpenRCA 和 reasoning failure studies 揭示 LLM 在复杂 RCA 上仍不稳定。
6. 因此，本文提出 Trust-Tree Gate：用拓扑和时序确定性证据决定是否自动接受、调用 LLM 或人工复核，实现准确率、成本和可靠性的折中。

## 5. 与本文创新点的关系

| 文献线索 | 支撑本文哪一部分 | 本文差异 |
| --- | --- | --- |
| Selective Classification | 自动接受/拒识的理论基础 | 本文把 reject option 映射为 LLM 或人工复核 |
| LLM Abstention | LLM 不确定时不应强答 | 本文由外部 trust tree 控制介入，而非依赖 LLM 自评 |
| LM-PACE | RCA 推荐需要置信估计 | 本文用确定性拓扑/时序证据替代 LLM confidence |
| COLA | 统计方法 + LLM 复核的混合范式 | 本文从告警聚合扩展到设备级 Top-K RCA |
| RCACopilot/RCAgent/TAMO | LLM 可做证据整理、工具调用和解释生成 | 本文限制 LLM 为仲裁器，不让其全量主导排序 |
| BiAn | LLM 可辅助生产级网络故障定位 | 本文强调 Pingmesh 场景下的 gate-controlled LLM |
| OpenRCA / reasoning failure studies | LLM RCA 存在能力边界 | 本文用 gate 降低 LLM 失败影响面 |

## 6. 建议引用清单

1. Geifman, Y., and El-Yaniv, R. Selective Classification for Deep Neural Networks. NeurIPS 2017.
2. Geifman, Y., and El-Yaniv, R. SelectiveNet: A Deep Neural Network with an Integrated Reject Option. ICML 2019.
3. Wen, B. et al. Know Your Limits: A Survey of Abstention in Large Language Models. 2024.
4. Geng, J. et al. A Survey of Confidence Estimation and Calibration in Large Language Models. 2024.
5. Zhang, S. et al. LM-PACE: Confidence Estimation by Large Language Models for Effective Root Causing of Cloud Incidents. FSE 2024.
6. Kuang, J. et al. Knowledge-aware Alert Aggregation in Large-scale Cloud Systems: a Hybrid Approach. ICSE 2024.
7. Ahmed, T. et al. Recommending Root-Cause and Mitigation Steps for Cloud Incidents using Large Language Models. ICSE 2023.
8. Chen, Y. et al. Automatic Root Cause Analysis via Large Language Models for Cloud Incidents. EuroSys 2024.
9. Wang, Z. et al. RCAgent: Cloud Root Cause Analysis by Autonomous Agents with Tool-Augmented Large Language Models. 2023/2024.
10. Wang, Q. et al. TAMO: Fine-Grained Root Cause Analysis via Tool-Assisted LLM Agent with Multi-Modality Observation Data. 2025.
11. Wang, C. et al. Towards LLM-Based Failure Localization in Production-Scale Networks. SIGCOMM 2025.
12. Xu, H. et al. OpenRCA: Can Large Language Models Locate the Root Cause of Software Failures? ICLR 2025.
13. Riddell, E. et al. Stalled, Biased, and Confused: Uncovering Reasoning Failures in LLMs for Cloud-Based Root Cause Analysis. 2026.

## 7. 可直接放入论文的总结句

现有 LLM-based RCA 工作证明了大模型在运维文本理解、异构证据整合和工具调用方面的潜力，但也暴露出长上下文、多跳因果和证据选择上的不稳定性。与其让 LLM 无约束地替代 RCA 算法，本文采用 selective prediction 的思想，将确定性拓扑-时序排序结果作为主诊断路径，并通过 Trust-Tree Gate 仅在多源证据冲突或置信不足时调用 LLM 仲裁，从而在定位准确率、调用成本和工程可靠性之间取得平衡。
