# Introduction：引入与以往工作（中文初稿）

日期：2026-09-10。范围：六部分 Introduction 中的前两部分连续正文；后四部分见[中文大纲](./Introduction_提纲_讨论稿.md)，完整英文提纲见[English outline](./Introduction_Outline_EN.md)。本稿采用单设备根因任务边界，配图位置和可直接使用的绘图 prompt 见中文大纲。

## 1. 引入

考虑一次端到端丢包告警触发后的排查场景。图 1 给出一个合成工程示例：H1 与 H2 之间的 Pingmesh 探测异常，交换设备 C 记录了面向 S 的接口 down 告警，S 记录了 BGP 会话回退，C 的日志还显示与 S 的邻居状态变化，而连接端点的 L1、L2 没有相应事件记录。面对这些信息，工程师可以先固定异常窗口，分别打开 C、S 的告警和日志，核对接口与邻居对应关系，再将“C 的异常影响 S”等假设展开为手工排障树，并为每一分支记录支持证据和仍需检查的项目。这里的工作尚未结束于找到一台可疑设备：还需要判断 C、S 在本次异常中的关系，以及现有证据能否将这一解释继续连接到其他设备。

即使候选设备相同，不同的起点和边方向仍会产生不同的故障解释。如果先把 S 固定为唯一根因，围绕 C 构造的传播结构就可能被提前排除；如果仅按告警顺序连接设备，又可能把相关现象误判为直接影响。沿物理拓扑把关系延伸至 L1、L2 同样缺少依据，因为没有记录既不证明设备正常，也不证明异常经过它们。工程师因而需要同时维护候选起点、核对设备对的局部证据，并把能够共同成立的关系组织为可检查的整体解释。

这一任务发生在支撑 Web 服务的数据中心网络运维中。搜索、在线存储等分布式服务依赖服务器之间的通信，Pingmesh 等端到端测量为网络异常分析提供观测入口。[Pingmesh，§1–2](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/11/pingmesh_sigcomm2015.pdf)。本文关注由此触发的后续诊断：给定异常端点、故障窗口内的设备告警与日志和原始物理拓扑，恢复与当前 incident 对应的设备级有向影响图，并提供逐边可核查的证据及未决关系。该图将起点假设、设备影响关系和解释缺口放入同一结构，服务于 Web 基础设施的故障核查与交接。业务端影响及人工排障收益需要另行验证，不能从本合成示例推算。

## 2. 以往工作

已有网络故障诊断研究已经从不同角度利用路径测量、网络拓扑、设备告警和运行知识缩小故障范围并定位根因。一类工作主要回答“故障在哪里”，通过路径观测、告警关联或跨设备推理识别故障范围及可疑设备；例如，BiAn 综合设备告警、拓扑、全局时间线和历史知识进行跨设备分析并生成根因设备排名 [11]。另一类工作开始回答“异常如何传播”，例如 NetEventCause 从历史告警中学习事件依赖关系，并以告警实例为节点恢复传播 DAG [7]。然而，根因设备排名并不能说明多个异常设备之间具体如何关联，而事件级传播关系也不能直接等同于设备级传播结构；此外，部分已有方法依赖完整调用路径、专门遥测或较完整的历史知识。本文关注的是另一种观测条件：在 Pingmesh 触发的端到端异常下，利用设备告警、日志和物理拓扑等不完整观测，进一步恢复故障相关设备之间具有方向性的影响关系，并将其组织为与当前故障实例对应的设备级传播图。


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
