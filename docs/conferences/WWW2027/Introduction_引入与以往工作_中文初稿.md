# Introduction：引入与以往工作（中文初稿）

日期：2026-09-16。范围：六部分 Introduction 中的前两部分连续正文；后四部分见[中文大纲](./Introduction_提纲_讨论稿.md)，完整英文提纲见[English outline](./Introduction_Outline_EN.md)。最新方案与页码对照见[同步说明](./2026-09-16_最新方案与文档同步说明.md)。本稿采用单设备起点任务边界；PPT 案例是示意，旧 `DEMO_001` 仅作历史合成观测示例。

## 1. 引入

考虑一次 Web 服务依赖的数据中心网络出现端到端异常后的诊断场景。Pingmesh 可以作为异常探测入口，但探测到丢包并不会自动告诉工程师哪些设备异常、哪些异常之间存在直接影响，或哪些恢复动作仍然必要。PPT《pingmesh治理》的 A/B/C/D 示意把这个缺口表达为一条可能的 A→B→{C,D} 关系，并给出排名 A、C、D、B。由于 A 已经排在第一位，传播图的潜在价值不在于把 A 排到第一，而在于帮助组织检查/恢复顺序并判断何时可以停止。“4 devices inspected → 2 devices handled”只作示意计数，不是 50% 效率或 MTTR 结果。

A 修复后 B 是否仍需处理、C/D 的 `Established` 状态是否异常、状态刷新和自动恢复延迟、动作权限与停止规则，PPT 均未给出，不能擅自写成确定的恢复序列。即使候选设备相同，局部证据不足或方向冲突也会产生不同解释；时间先后、状态标签和拓扑上游不能单独证明传播方向。工程师需要保留竞争关系和未知，并把能够共同成立的关系组织为可检查的整体解释。

这一任务发生在支撑 Web 服务的数据中心网络运维中。分布式服务依赖服务器之间的通信，Pingmesh 等端到端测量为网络异常分析提供观测入口。[Pingmesh，§1–2](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/11/pingmesh_sigcomm2015.pdf)。本文关注由此触发的后续诊断：给定异常端点、故障窗口内的设备告警与日志和原始物理拓扑，恢复与当前 incident 对应的设备级有向影响图，并提供逐边可核查的证据及未决关系。该图可作为恢复决策的解释输入，但业务端影响、人工动作收益和冗余检查减少仍需单独验证，不能由示意图推出。

## 2. 以往工作

已有网络故障诊断研究已从不同角度利用路径测量、网络拓扑、设备告警、事件依赖和运行知识缩小故障范围并定位根因。Pingmesh、deTector、NetBouncer 与 TraceRCA 依赖端点、可控路径或分布式 trace 约束故障位置；COLA 与 SkyNet 组织时空相关告警、拓扑或层次结构；BiAn、RCACopilot 等方法辅助信息采集、根因分类、设备排名和解释。另一方面，NetEventCause 已以告警实例为节点恢复传播 DAG，NetCause 与 Hawkeye 也分别在异构网络上下文或专门遥测下建模传播/溯源结构。因此，本文不声称已有工作“只有排名”或“没有图”，而是区分事件、设备和流/端口粒度，以及各自可用的观测和评价对象。本文关注的是在 Pingmesh 触发、缺少完整路径或专门遥测的条件下，利用设备告警、日志和原始物理拓扑恢复当前 incident 的设备级有向影响结构。


## 参考文献与核对说明（不进入正文）

1. Guo et al. **Pingmesh: A Large-Scale System for Data Center Network Latency Measurement and Analysis.** SIGCOMM 2015. [作者全文](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/11/pingmesh_sigcomm2015.pdf)。已有定位/排障能力；端到端测量不自动提供 ECMP 的确切路径。
2. **deTector: A Topology-aware Monitoring System for Data Center Networks.** USENIX ATC 2017. [会议官方页与全文入口](https://www.usenix.org/conference/atc17/technical-sessions/presentation/peng)。核对主动路径设计、覆盖性及可辨识性条件。
3. **NetBouncer: Active Device and Link Failure Localization in Data Center Networks.** NSDI 2019. [会议官方页](https://www.usenix.org/conference/nsdi19/presentation/tan)、[全文](https://www.usenix.org/system/files/nsdi19-tan.pdf)。需要可控路径测量及路径收发结果，不把其输出误写为设备传播 DAG。
4. Li et al. **Practical Root Cause Localization for Microservice Systems via Trace Analysis（TraceRCA）.** IWQoS 2021. DOI: [10.1109/IWQOS52092.2021.9521340](https://doi.org/10.1109/IWQOS52092.2021.9521340)。[作者代码与论文信息](https://github.com/NetManAIOps/TraceRCA)。原始输入是分布式调用 trace；本地全文亦已核对，不将设备告警组冒充真实调用路径。
5. **Knowledge-aware Alert Aggregation in Large-scale Cloud Systems: a Hybrid Approach（COLA）.** ICSE-SEIP 2024. DOI: [10.1145/3639477.3639745](https://doi.org/10.1145/3639477.3639745)。[作者预印本](https://arxiv.org/abs/2403.06485)。时空/拓扑统计与 SOP 辅助推理共同作用，输出告警聚合。
6. Yang et al. **SkyNet: Analyzing Alert Flooding from Severe Network Failures in Large Cloud Infrastructures.** SIGCOMM 2025. DOI: [10.1145/3718958.3750536](https://doi.org/10.1145/3718958.3750536)。[作者全文](https://ennanzhai.github.io/pub/sigcomm25-skynet.pdf)。已核对层次告警树、故障范围/严重度、Section 7.1 的连接图及告警投票，不称其“没有图”。
7. Yuan et al. **NetEventCause: Event-Driven Root Cause Analysis for Large Network System Without Topology.** TNNLS 36(10), 2025. DOI: [10.1109/TNNLS.2025.3574316](https://doi.org/10.1109/TNNLS.2025.3574316)。[作者代码](https://github.com/yuanzhaolin/NetEventCause)、[出版信息](https://pubmed.ncbi.nlm.nih.gov/40471725/)。已核对本地原文 Section III–IV 的告警实例图、时间假设和神经点过程；不声称其只建静态类型图、无法映射设备或必然产生环。
8. Chraim et al. **NetCause: Counterfactual Learning for Root Cause Analysis in Large-Scale Networks.** arXiv:2606.13543v1, 2026，预印本。[全文](https://arxiv.org/html/2606.13543v1)。已包含事件子图、拓扑、时间和影响上下文；这些输入的融合本身不是本文独有新意。
9. Wang et al. **Hawkeye: Diagnosing RDMA Network Performance Anomalies with PFC Provenance.** SIGCOMM 2025. DOI: [10.1145/3718958.3750490](https://doi.org/10.1145/3718958.3750490)。[作者全文](https://zhangmenghao.github.io/papers/SIGCOMM2025-Hawkeye.pdf)。确实构造传播/溯源图，差异在专门 PFC 遥测和流—端口粒度。
10. Chen et al. **Automatic Root Cause Analysis via Large Language Models for Cloud Incidents（RCACopilot）.** EuroSys 2024；[作者预印本](https://arxiv.org/abs/2305.15778)。核对诊断处理器、运行时信息聚合、根因类别及解释输出。与其他同名“RCA Copilot”论文区分。
11. Wang et al. **Towards LLM-Based Failure Localization in Production-Scale Networks（BiAn）.** SIGCOMM 2025. DOI: [10.1145/3718958.3750505](https://doi.org/10.1145/3718958.3750505)。[作者全文](https://ennanzhai.github.io/pub/sigcomm25-bian.pdf)。原始 BiAn、旧 Pipeline1 与新 BiAnAdapt 三流程适配分别标识；实现及模型验收状态见 Baseline实现进度与验收.md。

本节保留 11 项文献供 Related Work 复用；正文按故障定位和传播建模压缩比较。详细输入、复现边界与公平对照见[相关工作与 Baseline 选型](./Related_Work与Baseline选型.md)。

本轮已将引入替换为合成工程案例。用户确认暂时没有现场记录；工程师操作是示意流程，业务侧影响与排障收益尚未实测。WWW 的近三年先例与范围判断见[投稿契合分析](./WWW近三年网络相关论文检索与投稿契合分析.md)。
