# RPG-Recon 相关工作文献索引（按层次与主题）

检索截止日 **2026-09-15**。主表 **306** 条；待核实 **13** 条（[screening.csv](screening.csv)）。

完整字段见 [catalog.csv](catalog.csv) / [catalog.xlsx](catalog.xlsx)；逐条身份来源与等级出处见 [evidence.md](evidence.md)。

> **引用前必读**：`内容阅读深度` 列逐条标明读到哪一层。标为「仅元数据」的条目**未读摘要**，其`论文自身输出对象` 与 `与本文关系` 只是检索线索，不是原文事实。


## L1 核心近邻（195 条）


### 测量与路径约束定位（47 条）

| paper_id | 题名 | 简称 | venue | 等级 | 年份 | 链接 | 全文 | 阅读深度 |
|---|---|---|---|---|---|---|---|---|
| RW0149 | Detection and Localization of Network Black Holes | — | IEEE INFOCOM 2007 - 26th IEEE International  | A | 2007 | [DOI](https://doi.org/10.1109/infcom.2007.252) | — | 仅元数据 |
| RW0150 | Packet-Level Telemetry in Large Datacenter Networks | Everflow | Proceedings of the 2015 ACM Conference on Sp | A | 2015 | [DOI](https://doi.org/10.1145/2785956.2787483) | — | 仅元数据 |
| RW0151 | Pingmesh: A Large-Scale System for Data Center Network Latency Measurement and Analysis | Pingmesh | Proceedings of the 2015 ACM Conference on Sp | A | 2015 | [DOI](https://doi.org/10.1145/2785956.2787496) | — | 仅元数据 |
| RW0153 | Taking the Blame Game out of Data Centers Operations with NetPoirot | — | Proceedings of the 2016 ACM SIGCOMM Conferen | A | 2016 | [DOI](https://doi.org/10.1145/2934872.2934884) | — | 仅元数据 |
| RW0154 | Gray Failure: The Achilles' Heel of Cloud-Scale Systems | — | Proceedings of the 16th Workshop on Hot Topi | 未收录 | 2017 | [DOI](https://doi.org/10.1145/3102980.3103005) | — | 仅元数据 |
| RW0155 | Network Capability in Localizing Node Failures via End-to-End Path Measurements | — | IEEE/ACM Transactions on Networking | A | 2017 | [DOI](https://doi.org/10.1109/tnet.2016.2584544) | — | 仅元数据 |
| RW0156 | Pinpointing delay and forwarding anomalies using large-scale traceroute measurements | — | Proceedings of the 2017 Internet Measurement | B | 2017 | [DOI](https://doi.org/10.1145/3131365.3131384) | — | 仅元数据 |
| RW0159 | Distributed Link Anomaly Detection via Partial Network Tomography | — | ACM SIGMETRICS Performance Evaluation Review | 待核实 | 2018 | [DOI](https://doi.org/10.1145/3199524.3199532) | — | 仅元数据 |
| RW0160 | Fault Localization in Large-Scale Network Policy Deployment | Scout | 2018 IEEE 38th International Conference on D | B | 2018 | [DOI](https://doi.org/10.1109/icdcs.2018.00016) | — | 仅元数据 |
| RW0161 | Down the Black Hole | — | Proceedings of the Internet Measurement Conf | B | 2019 | [DOI](https://doi.org/10.1145/3355369.3355593) | — | 仅元数据 |
| RW0162 | Understanding the Limits of Passive Realtime Datacenter Fault Detection and Localization | — | IEEE/ACM Transactions on Networking | A | 2019 | [DOI](https://doi.org/10.1109/tnet.2019.2938228) | — | 仅元数据 |
| RW0164 | Rapid Detection and Localization of Gray Failures in Data Centers via In-band Network Te | — | NOMS 2020 - 2020 IEEE/IFIP Network Operation | 未收录 | 2020 | [DOI](https://doi.org/10.1109/noms47738.2020.9110326) | — | 仅元数据 |
| RW0170 | dDrops: Detecting silent packet drops on programmable data plane | — | Computer Networks | B | 2022 | [DOI](https://doi.org/10.1016/j.comnet.2022.109171) | — | 仅元数据 |
| RW0171 | FAst in-network <i>GraY</i> failure detection for ISPs | — | Proceedings of the ACM SIGCOMM 2022 Conferen | A | 2022 | [DOI](https://doi.org/10.1145/3544216.3544242) | — | 仅元数据 |
| RW0172 | Brownfield Measurement: A Practical Grey Failure Identification and Localization Method  | — | 2023 IEEE 29th International Conference on P | C | 2023 | [DOI](https://doi.org/10.1109/icpads60453.2023.00320) | — | 仅元数据 |
| RW0173 | Efficient end-to-end failure probing matrix construction in data center networks | — | Journal of Communications and Networks | C | 2023 | [DOI](https://doi.org/10.23919/jcn.2023.000029) | — | 仅元数据 |
| RW0174 | Flock: Accurate Network Fault Localization at Scale | Flock | Proceedings of the ACM on Networking | 待核实 | 2023 | [DOI](https://doi.org/10.1145/3595289) | — | 摘要已读 |
| RW0176 | MARS: Fault Localization in Programmable Networking Systems with Low-cost In-Band Networ | MARS | Proceedings of the 52nd International Confer | B | 2023 | [DOI](https://doi.org/10.1145/3605573.3605622) | — | 仅元数据 |
| RW0177 | Poster: COPA -- Parsing Outputs of CLI Commands for Failure Diagnosis of Network Devices | — | Proceedings of the 2023 ACM on Internet Meas | B | 2023 | [DOI](https://doi.org/10.1145/3618257.3624998) | — | 仅元数据 |
| RW0180 | R-Pingmesh: A Service-Aware RoCE Network Monitoring and Diagnostic System | R-Pingmesh | Proceedings of the ACM SIGCOMM 2024 Conferen | A | 2024 | [DOI](https://doi.org/10.1145/3651890.3672264) | — | 仅元数据 |
| RW0181 | Themis: A passive-active hybrid framework with in-network intelligence for lightweight f | Themis | Computer Networks | B | 2024 | [DOI](https://doi.org/10.1016/j.comnet.2024.110836) | — | 仅元数据 |
| RW0184 | FlowPulse: Catching Network Failures in ML Clusters | FlowPulse | Proceedings of the 24th ACM Workshop on Hot  | 不适用（非正式论文轨道） | 2025 | [DOI](https://doi.org/10.1145/3772356.3772384) | — | 仅元数据 |
| RW0185 | Hawkeye: Diagnosing RDMA Network Performance Anomalies with PFC Provenance | Hawkeye | Proceedings of the ACM SIGCOMM 2025 Conferen | A | 2025 | [DOI](https://doi.org/10.1145/3718958.3750490) | — | 仅元数据 |
| RW0186 | Raha: A General Tool to Analyze WAN Degradation | Raha | Proceedings of the ACM SIGCOMM 2025 Conferen | A | 2025 | [DOI](https://doi.org/10.1145/3718958.3754348) | — | 仅元数据 |
| RW0187 | RCA Copilot: Transforming Network Data into Actionable Insights via Large Language Model | — | ICC 2025 - IEEE International Conference on  | C | 2025 | [DOI](https://doi.org/10.1109/icc52391.2025.11161714) | — | 仅元数据 |
| RW0188 | SkeletonHunter: Diagnosing and Localizing Network Failures in Containerized Large Model  | SkeletonHunter | Proceedings of the ACM SIGCOMM 2025 Conferen | A | 2025 | [DOI](https://doi.org/10.1145/3718958.3750513) | — | 仅元数据 |
| RW0189 | SkyNet: Analyzing Alert Flooding from Severe Network Failures in Large Cloud Infrastruct | SkyNet | Proceedings of the ACM SIGCOMM 2025 Conferen | A | 2025 | [DOI](https://doi.org/10.1145/3718958.3750536) | — | 仅元数据 |
| RW0191 | Towards LLM-Based Failure Localization in Production-Scale Networks | BiAn | Proceedings of the ACM SIGCOMM 2025 Conferen | A | 2025 | [DOI](https://doi.org/10.1145/3718958.3750505) | — | 仅元数据 |
| RW0192 | Canary: Detecting and Localizing Faults in Data Center Networks With Partial Traffic Mon | Canary | IEEE Transactions on Networking | A | 2026 | [DOI](https://doi.org/10.1109/ton.2025.3597359) | — | 仅元数据 |
| RW0194 | LinkSonar: A General and Fine-Grained Approach for Failure Identification in Data Center | LinkSonar | IEEE Transactions on Networking | A | 2026 | [DOI](https://doi.org/10.1109/ton.2026.3696241) | — | 仅元数据 |
| RW0158 | 007: Democratically Finding the Cause of Packet Drops | — | 15th USENIX Symposium on Networked Systems D | A |  | [链接](https://www.usenix.org/conference/nsdi18/presentation/arzani) | [全文](https://www.usenix.org/conference/nsdi18/presentation/arzani) | 仅元数据 |
| RW0178 | AAsclepius: Monitoring, Diagnosing, and Detouring at the Internet Peering Edge | AAsclepius | 2023 USENIX Annual Technical Conference (USE | A |  | [链接](https://www.usenix.org/conference/atc23/presentation/yang-kaicheng) | [全文](https://www.usenix.org/conference/atc23/presentation/yang-kaicheng) | 仅元数据 |
| RW0168 | Closed-loop Network Performance Monitoring and Diagnosis with SpiderMon | — | 19th USENIX Symposium on Networked Systems D | A |  | [链接](https://www.usenix.org/conference/nsdi22/presentation/wang-weitao-spidermon) | [全文](https://www.usenix.org/conference/nsdi22/presentation/wang-weitao-spidermon) | 仅元数据 |
| RW0169 | Collie: Finding Performance Anomalies in RDMA Subsystems | Collie | 19th USENIX Symposium on Networked Systems D | A |  | [链接](https://www.usenix.org/conference/nsdi22/presentation/kong) | [全文](https://www.usenix.org/conference/nsdi22/presentation/kong) | 仅元数据 |
| RW0166 | Debugging Transient Faults in Data Centers using Synchronized Network-wide Packet Histor | — | 18th USENIX Symposium on Networked Systems D | A |  | [链接](https://www.usenix.org/conference/nsdi21/presentation/kannan) | [全文](https://www.usenix.org/conference/nsdi21/presentation/kannan) | 仅元数据 |
| RW0157 | deTector: a Topology-aware Monitoring System for Data Center Networks | — | 2017 USENIX Annual Technical Conference (USE | A |  | [链接](https://www.usenix.org/conference/atc17/technical-sessions/presentation/peng) | [全文](https://www.usenix.org/conference/atc17/technical-sessions/presentation/peng) | 仅元数据 |
| RW0179 | Diagnosing Application-network Anomalies for Millions of IPs in Production Clouds | — | 2024 USENIX Annual Technical Conference (USE | A |  | [链接](https://www.usenix.org/conference/atc24/presentation/wang-zhe) | [全文](https://www.usenix.org/conference/atc24/presentation/wang-zhe) | 仅元数据 |
| RW0183 | Enhancing Network Failure Mitigation with Performance-Aware Ranking | — | 22nd USENIX Symposium on Networked Systems D | A |  | [链接](https://www.usenix.org/conference/nsdi25/presentation/namyar) | [全文](https://www.usenix.org/conference/nsdi25/presentation/namyar) | 仅元数据 |
| RW0193 | Glint: Localization of Gray Violations in Untrusted and Unreliable SRv6 Networks | Glint | IEEE Transactions on Information Forensics a | A |  | [DOI](https://doi.org/10.1109/tifs.2025.3649962) | — | 仅元数据 |
| RW0175 | Hostping: Diagnosing Intra-host Network Bottlenecks in RDMA Servers | Hostping | 20th USENIX Symposium on Networked Systems D | A |  | [链接](https://www.usenix.org/conference/nsdi23/presentation/liu-kefei) | [全文](https://www.usenix.org/conference/nsdi23/presentation/liu-kefei) | 仅元数据 |
| RW0182 | NetAssistant: Dialogue Based Network Diagnosis in Data Center Networks | NetAssistant | 21st USENIX Symposium on Networked Systems D | A |  | [链接](https://www.usenix.org/conference/nsdi24/presentation/wang-haopei) | [全文](https://www.usenix.org/conference/nsdi24/presentation/wang-haopei) | 仅元数据 |
| RW0163 | NetBouncer: Active Device and Link Failure Localization in Data Center Networks | NetBouncer | 16th USENIX Symposium on Networked Systems D | A |  | [链接](https://www.usenix.org/conference/nsdi19/presentation/tan) | [全文](https://www.usenix.org/conference/nsdi19/presentation/tan) | 仅元数据 |
| RW0152 | Simplifying Datacenter Network Debugging with PathDump | — | 12th USENIX Symposium on Operating Systems D | A |  | [链接](https://www.usenix.org/conference/osdi16/technical-sessions/presentation/tammana) | [全文](https://www.usenix.org/conference/osdi16/technical-sessions/presentation/tammana) | 仅元数据 |
| RW0195 | SprayCheck: Finding Gray Failures in Adaptive Routing Networks | SprayCheck | arXiv preprint | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2605.03702) | [全文](https://arxiv.org/abs/2605.03702) | 摘要已读 |
| RW0167 | Static and Dynamic Failure Localization through Progressive Network Tomography | — | arXiv preprint | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2103.17221) | [全文](https://arxiv.org/abs/2103.17221) | 摘要已读 |
| RW0190 | Topology-Awareness Fault-Tolerant Migration for Node Cascading Failures in Data Center N | — | IEEE Transactions on Networking | A |  | [DOI](https://doi.org/10.1109/ton.2025.3583935) | — | 仅元数据 |
| RW0165 | Understanding, Detecting and Localizing Partial Failures in Large System Software (FIRM) | — | 17th USENIX Symposium on Networked Systems D | A |  | [链接](https://www.usenix.org/conference/nsdi20/presentation/lou) | [全文](https://www.usenix.org/conference/nsdi20/presentation/lou) | 仅元数据 |

### 事件依赖与传播建模（42 条）

| paper_id | 题名 | 简称 | venue | 等级 | 年份 | 链接 | 全文 | 阅读深度 |
|---|---|---|---|---|---|---|---|---|
| RW0067 | Secure network provenance | — | Proceedings of the Twenty-Third ACM Symposiu | A | 2011 | [DOI](https://doi.org/10.1145/2043556.2043584) | — | 仅元数据 |
| RW0068 | Differential Provenance | — | Proceedings of the 14th ACM Workshop on Hot  | 不适用（非正式论文轨道） | 2015 | [DOI](https://doi.org/10.1145/2834050.2834111) | — | 仅元数据 |
| RW0069 | SMT-Based Validation of Timed Failure Propagation Graphs | — | Proceedings of the AAAI Conference on Artifi | A | 2015 | [DOI](https://doi.org/10.1609/aaai.v29i1.9753) | — | 仅元数据 |
| RW0070 | The Good, the Bad, and the Differences | — | Proceedings of the 2016 ACM SIGCOMM Conferen | A | 2016 | [DOI](https://doi.org/10.1145/2934872.2934910) | — | 仅元数据 |
| RW0071 | Microscope: Pinpoint Performance Issues with Causal Graphs in Micro-service Environments | Microscope | Lecture Notes in Computer Science | 未收录 | 2018 | [DOI](https://doi.org/10.1007/978-3-030-03596-9_1) | — | 仅元数据 |
| RW0072 | Mining Subgraphs from Propagation Networks through Temporal Dynamic Analysis | — | 2018 19th IEEE International Conference on M | C | 2018 | [DOI](https://doi.org/10.1109/mdm.2018.00023) | — | 仅元数据 |
| RW0073 | NoDoze: Combatting Threat Alert Fatigue with Automated Provenance Triage | NoDoze | Proceedings 2019 Network and Distributed Sys | A | 2019 | [DOI](https://doi.org/10.14722/ndss.2019.23349) | — | 仅元数据 |
| RW0074 | Causal network construction based on convergent cross mapping (CCM) for alarm system roo | — | IFAC-PapersOnLine | 未收录 | 2020 | [DOI](https://doi.org/10.1016/j.ifacol.2020.12.858) | — | 仅元数据 |
| RW0075 | MicroRCA: Root Cause Localization of Performance Issues in Microservices | MicroRCA | NOMS 2020 - 2020 IEEE/IFIP Network Operation | 未收录 | 2020 | [DOI](https://doi.org/10.1109/noms47738.2020.9110353) | — | 仅元数据 |
| RW0076 | Root Cause Analysis of Concurrent Alarms Based on Random Walk over Anomaly Propagation G | — | 2020 IEEE International Conference on Networ | C | 2020 | [DOI](https://doi.org/10.1109/icnsc48988.2020.9238084) | — | 仅元数据 |
| RW0077 | Fault Analysis and Debugging of Microservice Systems: Industrial Survey, Benchmark Syste | — | IEEE Transactions on Software Engineering | A | 2021 | [DOI](https://doi.org/10.1109/tse.2018.2887384) | — | 仅元数据 |
| RW0078 | Groot: An Event-graph-based Approach for Root Cause Analysis in Industrial Settings | Groot | 2021 36th IEEE/ACM International Conference  | A | 2021 | [DOI](https://doi.org/10.1109/ase51524.2021.9678708) | — | 仅元数据 |
| RW0079 | HALO: Hierarchy-aware Fault Localization for Cloud Systems | HALO | Proceedings of the 27th ACM SIGKDD Conferenc | A | 2021 | [DOI](https://doi.org/10.1145/3447548.3467190) | — | 仅元数据 |
| RW0080 | Insights into Multi-Layered Fault Propagation and Analysis in a Cloud Stack | — | 2021 IEEE 14th International Conference on C | C | 2021 | [DOI](https://doi.org/10.1109/cloud53861.2021.00092) | — | 仅元数据 |
| RW0081 | Locating Datacenter Link Faults with a Directed Graph Convolutional Neural Network | — | Proceedings of the 10th International Confer | C | 2021 | [DOI](https://doi.org/10.5220/0010301403120320) | — | 仅元数据 |
| RW0082 | MicroHECL: High-Efficient Root Cause Localization in Large-Scale Microservice Systems | MicroHECL | 2021 IEEE/ACM 43rd International Conference  | 不适用（非正式论文轨道） | 2021 | [DOI](https://doi.org/10.1109/icse-seip52600.2021.00043) | — | 仅元数据 |
| RW0083 | Timed failure propagation graph construction with supremal language guided Tree-LSTM and | — | Applied Intelligence | C | 2022 | [DOI](https://doi.org/10.1007/s10489-021-03107-6) | — | 仅元数据 |
| RW0084 | Causal Generative Model for Root-Cause Diagnosis and Fault Propagation Analysis in Indus | — | IEEE Transactions on Instrumentation and Mea | 未收录 | 2023 | [DOI](https://doi.org/10.1109/tim.2023.3273686) | — | 仅元数据 |
| RW0085 | CausIL: Causal Graph for Instance Level Microservice Data | CausIL | Proceedings of the ACM Web Conference 2023 | A | 2023 | [DOI](https://doi.org/10.1145/3543507.3583274) | — | 仅元数据 |
| RW0086 | FRL-MFPG: Propagation-aware fault root cause location for microservice intelligent opera | FRL-MFPG | Information and Software Technology | B | 2023 | [DOI](https://doi.org/10.1016/j.infsof.2022.107083) | — | 仅元数据 |
| RW0087 | Hierarchical Causal Graph-Based Fault Root Cause Diagnosis and Propagation Path Identifi | — | IEEE Transactions on Instrumentation and Mea | 未收录 | 2023 | [DOI](https://doi.org/10.1109/tim.2023.3268464) | — | 仅元数据 |
| RW0088 | ImpactTracer: Root Cause Localization in Microservices Based on Fault Propagation Modeli | ImpactTracer | 2023 Design, Automation &amp; Test in Europe | B | 2023 | [DOI](https://doi.org/10.23919/date56975.2023.10137078) | — | 仅元数据 |
| RW0089 | Incremental Causal Graph Learning for Online Root Cause Analysis | CORAL | Proceedings of the 29th ACM SIGKDD Conferenc | A | 2023 | [DOI](https://doi.org/10.1145/3580305.3599392) | — | 仅元数据 |
| RW0090 | Nezha: Interpretable Fine-Grained Root Causes Analysis for Microservices on Multi-modal  | Nezha | Proceedings of the 31st ACM Joint European S | A | 2023 | [DOI](https://doi.org/10.1145/3611643.3616249) | — | 仅元数据 |
| RW0091 | Chain-of-Event: Interpretable Root Cause Analysis for Microservices through Automaticall | Chain-of-Event | Companion Proceedings of the 32nd ACM Intern | 不适用（非正式论文轨道） | 2024 | [DOI](https://doi.org/10.1145/3663529.3663827) | — | 仅元数据 |
| RW0092 | Cluster-Aware Causal Discovery Framework for Root Cause Analysis of Base Station Alarms | — | 2024 IEEE Globecom Workshops (GC Wkshps) | 不适用（非正式论文轨道） | 2024 | [DOI](https://doi.org/10.1109/gcwkshp64532.2024.11101284) | — | 仅元数据 |
| RW0093 | Dependency Aware Incident Linking in Large Cloud Systems | — | Companion Proceedings of the ACM Web Confere | 不适用（非正式论文轨道） | 2024 | [DOI](https://doi.org/10.1145/3589335.3648311) | — | 仅元数据 |
| RW0094 | FaultInsight: Interpreting Hyperscale Data Center Host Faults | FaultInsight | Proceedings of the 30th ACM SIGKDD Conferenc | A | 2024 | [DOI](https://doi.org/10.1145/3637528.3672051) | — | 仅元数据 |
| RW0095 | MULAN: Multi-modal Causal Structure Learning and Root Cause Analysis for Microservice Sy | MULAN | Proceedings of the ACM Web Conference 2024 | A | 2024 | [DOI](https://doi.org/10.1145/3589334.3645442) | — | 仅元数据 |
| RW0096 | R-CAID: Embedding Root Cause Analysis within Provenance-based Intrusion Detection | R-CAID | 2024 IEEE Symposium on Security and Privacy  | A | 2024 | [DOI](https://doi.org/10.1109/sp54263.2024.00253) | — | 仅元数据 |
| RW0097 | Root Cause Analysis for Microservice System based on Causal Inference: How Far Are We? | — | Proceedings of the 39th IEEE/ACM Internation | A | 2024 | [DOI](https://doi.org/10.1145/3691620.3695065) | — | 仅元数据 |
| RW0098 | Root Cause Analysis in Microservice Using Neural Granger Causal Discovery | — | Proceedings of the AAAI Conference on Artifi | A | 2024 | [DOI](https://doi.org/10.1609/aaai.v38i1.27772) | — | 仅元数据 |
| RW0099 | Classifying Host-Side RDMA Pingmesh Results to Efficiently Identify Transport Faults in  | — | 2025 IEEE 31th International Conference on P | C | 2025 | [DOI](https://doi.org/10.1109/icpads67057.2025.11322964) | — | 仅元数据 |
| RW0100 | ErrorPrism: Reconstructing Error Propagation Paths in Cloud Service Systems | ErrorPrism | 2025 40th IEEE/ACM International Conference  | A | 2025 | [DOI](https://doi.org/10.1109/ase63991.2025.00292) | — | 仅元数据 |
| RW0101 | Failure Propagation Graphs for Studying Cascading Failure Propagation in Power Networks | — | IEEE Systems Journal | 未收录 | 2025 | [DOI](https://doi.org/10.1109/jsyst.2024.3524246) | — | 仅元数据 |
| RW0102 | Interpretable Failure Localization for Microservice Systems Based on Graph Autoencoder | — | ACM Transactions on Software Engineering and | A | 2025 | [DOI](https://doi.org/10.1145/3695999) | — | 仅元数据 |
| RW0107 | Rethinking the Evaluation of Microservice RCA with a Fault Propagation-Aware Benchmark | — | Proceedings of the ACM on Software Engineeri | 待核实 | 2026 | [DOI](https://doi.org/10.1145/3797100) | — | 摘要已读 |
| RW0108 | Topo-MFP: Topology-aware multimodal propagation learning for fault detection and root ca | Topo-MFP | Journal of King Saud University Computer and | B | 2026 | [DOI](https://doi.org/10.1007/s44443-026-01193-5) | — | 仅元数据 |
| RW0104 | EvoCause: LLM-Guided Evolution of Causal Graphs for Root Cause Analysis | EvoCause | arXiv preprint | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2607.27290) | [全文](https://arxiv.org/abs/2607.27290) | 摘要已读 |
| RW0105 | NetCause: Counterfactual Learning for Root Cause Analysis in Large-Scale Networks | NetCause | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2606.13543) | [全文](https://arxiv.org/abs/2606.13543) | 摘要已读 |
| RW0103 | NetEventCause: Event-Driven Root Cause Analysis for Large Network System Without Topolog | NetEventCause | IEEE Transactions on Neural Networks and Lea | B |  | [DOI](https://doi.org/10.1109/tnnls.2025.3574316) | — | 仅元数据 |
| RW0106 | PropLLM: Propagation-Aware Scene Reconstruction for Network Fault Diagnosis | PropLLM | arXiv preprint | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2606.00582) | [全文](https://arxiv.org/abs/2606.00582) | 摘要已读 |

### LLM/知识辅助网络诊断（41 条）

| paper_id | 题名 | 简称 | venue | 等级 | 年份 | 链接 | 全文 | 阅读深度 |
|---|---|---|---|---|---|---|---|---|
| RW0003 | Automated Root Causing of Cloud Incidents using In-Context Learning with GPT-4 | — | Companion Proceedings of the 32nd ACM Intern | 不适用（非正式论文轨道） | 2024 | [DOI](https://doi.org/10.1145/3663529.3663846) | — | 仅元数据 |
| RW0005 | Exploring LLM-Based Agents for Root Cause Analysis | — | Companion Proceedings of the 32nd ACM Intern | 不适用（非正式论文轨道） | 2024 | [DOI](https://doi.org/10.1145/3663529.3663841) | — | 仅元数据 |
| RW0006 | NetConfEval: Can LLMs Facilitate Network Configuration? | NetConfEval | Proceedings of the ACM on Networking | 待核实 | 2024 | [DOI](https://doi.org/10.1145/3656296) | — | 仅元数据 |
| RW0007 | NetLLM: Adapting Large Language Models for Networking | NetLLM | Proceedings of the ACM SIGCOMM 2024 Conferen | A | 2024 | [DOI](https://doi.org/10.1145/3651890.3672268) | — | 仅元数据 |
| RW0010 | A Survey of AIOps in the Era of Large Language Models | — | ACM Computing Surveys | 待核实 | 2025 | [DOI](https://doi.org/10.1145/3746635) | — | 仅元数据 |
| RW0011 | AIOpsLab in Action: An Open Platform for AIOps Research | — | Proceedings of the 33rd ACM International Co | A | 2025 | [DOI](https://doi.org/10.1145/3696630.3728619) | — | 仅元数据 |
| RW0012 | Between Promise and Pain: The Reality of Automating Failure Analysis in Microservices wi | — | Proceedings of the 16th ACM SIGOPS Asia-Paci | 未收录 | 2025 | [DOI](https://doi.org/10.1145/3725783.3764388) | — | 仅元数据 |
| RW0013 | Flow-of-Action: SOP Enhanced LLM-Based Multi-Agent System for Root Cause Analysis | Flow-of-Action | Companion Proceedings of the ACM on Web Conf | 不适用（非正式论文轨道） | 2025 | [DOI](https://doi.org/10.1145/3701716.3715225) | — | 仅元数据 |
| RW0014 | FlowXpert: Expertizing Troubleshooting Workflow Orchestration with Knowledge Base and Mu | FlowXpert | Proceedings of the 31st ACM SIGKDD Conferenc | A | 2025 | [DOI](https://doi.org/10.1145/3711896.3737221) | — | 仅元数据 |
| RW0018 | LogEval: A comprehensive benchmark suite for LLMs in log analysis | LogEval | Empirical Software Engineering | B | 2025 | [DOI](https://doi.org/10.1007/s10664-025-10701-6) | — | 仅元数据 |
| RW0019 | Multi Source Alarm Root Cause Localization and Self Generated Work Order Method Based on | — | 2025 IEEE 7th Advanced Information Managemen | C | 2025 | [DOI](https://doi.org/10.1109/imcec66174.2025.11332057) | — | 仅元数据 |
| RW0021 | OpsEval: A Comprehensive Benchmark Suite for Evaluating Large Language Models’ Capabilit | OpsEval | Proceedings of the 33rd ACM International Co | A | 2025 | [DOI](https://doi.org/10.1145/3696630.3728572) | — | 仅元数据 |
| RW0022 | TAMO:Fine-Grained Root Cause Analysis via Tool-Assisted LLM Agent With Multi-Modality Ob | — | IEEE Transactions on Services Computing | A | 2025 | [DOI](https://doi.org/10.1109/tsc.2025.3629066) | — | 仅元数据 |
| RW0024 | Towards a Playground to Democratize Experimentation and Benchmarking of AI Agents for Ne | — | Proceedings of the 1st Workshop on Next-Gene | 未收录 | 2025 | [DOI](https://doi.org/10.1145/3748496.3748990) | — | 仅元数据 |
| RW0025 | A Survey on Applications of Large Language Model-Driven Digital Twins for Intelligent Ne | — | IEEE Communications Surveys &amp; Tutorials | 未收录 | 2026 | [DOI](https://doi.org/10.1109/comst.2025.3568637) | — | 仅元数据 |
| RW0027 | An LLM-Based Autonomous Agent for Network Diagnosis and Recovery on a Digital Twin | — | 2026 35th International Conference on Comput | C | 2026 | [DOI](https://doi.org/10.1109/icccn69946.2026.11662660) | — | 仅元数据 |
| RW0032 | Hypothesize-Then-Verify: Speculative Root Cause Analysis for Microservices with Pathwise | — | Proceedings of the IEEE/ACM 48th Internation | A | 2026 | [DOI](https://doi.org/10.1145/3786582.3786803) | — | 仅元数据 |
| RW0035 | LLM-Enhanced Failure Localization in Microservices: Integrating Multi-Modal Data and Exp | — | IEEE Transactions on Services Computing | A | 2026 | [DOI](https://doi.org/10.1109/tsc.2026.3676262) | — | 仅元数据 |
| RW0041 | Stalled, Biased, and Confused: Uncovering Reasoning Failures in LLMs for Cloud-Based Roo | — | Proceedings of the 2026 IEEE/ACM Third Inter | 待核实 | 2026 | [DOI](https://doi.org/10.1145/3793655.3793732) | — | 仅元数据 |
| RW0009 | A Network Arena for Benchmarking AI Agents on Network Troubleshooting | — | arXiv preprint | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2512.16381) | [全文](https://arxiv.org/abs/2512.16381) | 摘要已读 |
| RW0026 | Agent-Native Telemetry: Verifiable State-Delta Evidence for Autonomous Operations | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2608.16178) | [全文](https://arxiv.org/abs/2608.16178) | 摘要已读 |
| RW0002 | An Empirical Study of NetOps Capability of Pre-Trained Large Language Models | — | — | 待核实 |  | [链接](https://arxiv.org/abs/2309.05557) | [全文](https://arxiv.org/abs/2309.05557) | 摘要已读 |
| RW0004 | Automatic Root Cause Analysis via Large Language Models for Cloud Incidents | — | Proceedings of the Nineteenth European Confe | A |  | [DOI](https://doi.org/10.1145/3627703.3629553) | — | 仅元数据 |
| RW0028 | Benchmarking LLM-Driven Network Configuration Repair | — | — | 待核实 |  | [链接](https://arxiv.org/abs/2604.22513) | [全文](https://arxiv.org/abs/2604.22513) | 摘要已读 |
| RW0029 | FaulT-Bench: Towards Benchmarking Network Troubleshooting LLM Agents under Unreliable Us | FaulT-Bench | arXiv preprint | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2608.27021) | [全文](https://arxiv.org/abs/2608.27021) | 摘要已读 |
| RW0015 | GALA: Can Graph-Augmented Large Language Model Agentic Workflows Elevate Root Cause Anal | GALA | arXiv preprint | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2508.12472) | [全文](https://arxiv.org/abs/2508.12472) | 摘要已读 |
| RW0030 | GALA: Graph-Augmented LLM Agents for Root Cause Analysis and Incident Response in Micros | GALA | arXiv preprint | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2608.08968) | [全文](https://arxiv.org/abs/2608.08968) | 摘要已读 |
| RW0031 | How Far Can Root Cause Analysis Go on Real-World Telemetry Data? | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2607.13548) | [全文](https://arxiv.org/abs/2607.13548) | 摘要已读 |
| RW0016 | Intent-Driven Network Management with Multi-Agent LLMs: The Confucius Framework | — | Proceedings of the ACM SIGCOMM 2025 Conferen | A |  | [DOI](https://doi.org/10.1145/3718958.3750537) | — | 仅元数据 |
| RW0033 | JustDiag!: A Diagnostic Justification Engine for Accountable Root Cause Analysis | — | arXiv preprint | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2606.19407) | [全文](https://arxiv.org/abs/2606.19407) | 摘要已读 |
| RW0034 | Large Language Models for Agentic NetOps and AIOps: Architectures, Evaluation, and Safet | — | arXiv preprint | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2605.12729) | [全文](https://arxiv.org/abs/2605.12729) | 摘要已读 |
| RW0017 | Large Language Models for Networking: Workflow, Advances, and Challenges | — | IEEE Network | 未收录 |  | [DOI](https://doi.org/10.1109/mnet.2024.3510936) | — | 仅元数据 |
| RW0001 | Netrca: An Effective Network Fault Cause Localization Algorithm | Netrca | ICASSP 2022 - 2022 IEEE International Confer | B |  | [DOI](https://doi.org/10.1109/icassp43922.2022.9747882) | — | 仅元数据 |
| RW0020 | OFCnetLLM: Large Language Model for Network Monitoring and Alertness | OFCnetLLM | arXiv preprint | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2507.22711) | [全文](https://arxiv.org/abs/2507.22711) | 摘要已读 |
| RW0036 | OpenRCA 2.0: From Outcome Labels to Causal Process Supervision | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2606.27154) | [全文](https://arxiv.org/abs/2606.27154) | 摘要已读 |
| RW0037 | ORCA-bench: How Ready Are Language Model Agents for Oncall? | ORCA-bench | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2607.28545) | [全文](https://arxiv.org/abs/2607.28545) | 摘要已读 |
| RW0038 | Pooled Leaderboards Hide System-Specific Winners: A Reporting-Protocol Audit of Offline  | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2606.29159) | [全文](https://arxiv.org/abs/2606.29159) | 摘要已读 |
| RW0039 | Praxis: Integrating Program Analysis with Observability for Root-Cause Analysis | Praxis | 2026 56th Annual IEEE International Conferen | B |  | [DOI](https://doi.org/10.1109/dsn69566.2026.00021) | — | 仅元数据 |
| RW0008 | Retrieval Augmented Generation-Based Incident Resolution Recommendation System for IT Su | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2409.13707) | [全文](https://arxiv.org/abs/2409.13707) | 摘要已读 |
| RW0040 | SiriusHelper: An LLM Agent-Based Operations Assistant for Big Data Platforms | SiriusHelper | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2605.00043) | [全文](https://arxiv.org/abs/2605.00043) | 摘要已读 |
| RW0023 | TN-AutoRCA: Benchmark Construction and Agentic Framework for Self-Improving Alarm-Based  | TN-AutoRCA | arXiv preprint | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2507.18190) | [全文](https://arxiv.org/abs/2507.18190) | 摘要已读 |

### 告警关联与故障范围（40 条）

| paper_id | 题名 | 简称 | venue | 等级 | 年份 | 链接 | 全文 | 阅读深度 |
|---|---|---|---|---|---|---|---|---|
| RW0109 | Pattern matching of alarm flood sequences by a modified Smith–Waterman algorithm | — | Chemical Engineering Research and Design | 未收录 | 2013 | [DOI](https://doi.org/10.1016/j.cherd.2012.11.001) | — | 仅元数据 |
| RW0110 | Similarity Analysis of Industrial Alarm Flood Data | — | IEEE Transactions on Automation Science and  | B | 2013 | [DOI](https://doi.org/10.1109/tase.2012.2230627) | — | 仅元数据 |
| RW0111 | Log clustering based problem identification for online service systems | — | Proceedings of the 38th International Confer | 不适用（非正式论文轨道） | 2016 | [DOI](https://doi.org/10.1145/2889160.2889232) | — | 仅元数据 |
| RW0112 | Structure learning methods for Bayesian networks to reduce alarm floods by identifying t | — | 2017 22nd IEEE International Conference on E | 未收录 | 2017 | [DOI](https://doi.org/10.1109/etfa.2017.8247692) | — | 仅元数据 |
| RW0113 | Alarm Compression Based on Machine Learning and Association Rules Mining in Optical Netw | — | 2018 23rd Opto-Electronics and Communication | 未收录 | 2018 | [DOI](https://doi.org/10.1109/oecc.2018.8730111) | — | 仅元数据 |
| RW0114 | Alarm Correlation in Mobile Telecommunications Networks based on k-means Cluster Analysi | — | Journal of Telecommunications and Informatio | 未收录 | 2018 | [DOI](https://doi.org/10.26636/jtit.2018.124518) | — | 仅元数据 |
| RW0115 | Detection of Frequent Alarm Patterns in Industrial Alarm Floods Using Itemset Mining Met | — | IEEE Transactions on Industrial Electronics | 未收录 | 2018 | [DOI](https://doi.org/10.1109/tie.2018.2795573) | — | 仅元数据 |
| RW0116 | Network Alarm Flood Pattern Mining Algorithm Based on Multi-dimensional Association | — | Proceedings of the 21st ACM International Co | C | 2018 | [DOI](https://doi.org/10.1145/3242102.3242130) | — | 仅元数据 |
| RW0117 | Continuous Incident Triage for Large-Scale Online Service Systems | — | 2019 34th IEEE/ACM International Conference  | A | 2019 | [DOI](https://doi.org/10.1109/ase.2019.00042) | — | 仅元数据 |
| RW0118 | Understanding and handling alert storm for online service systems | — | Proceedings of the ACM/IEEE 42nd Internation | 不适用（非正式论文轨道） | 2020 | [DOI](https://doi.org/10.1145/3377813.3381363) | — | 仅元数据 |
| RW0119 | An Influence-Based Approach for Root Cause Alarm Discovery in Telecom Networks | — | Lecture Notes in Computer Science | 未收录 | 2021 | [DOI](https://doi.org/10.1007/978-3-030-76352-7_16) | — | 仅元数据 |
| RW0120 | Discovering Alarm Correlation Rules for Network Fault Management | — | Lecture Notes in Computer Science | 未收录 | 2021 | [DOI](https://doi.org/10.1007/978-3-030-76352-7_24) | — | 仅元数据 |
| RW0121 | Fault Localization based on Knowledge Graph in Software-Defined Optical Networks | — | Journal of Lightwave Technology | 未收录 | 2021 | [DOI](https://doi.org/10.1109/jlt.2021.3071868) | — | 仅元数据 |
| RW0122 | Graph-based Incident Aggregation for Large-Scale Online Service Systems | — | 2021 36th IEEE/ACM International Conference  | A | 2021 | [DOI](https://doi.org/10.1109/ase51524.2021.9678746) | — | 仅元数据 |
| RW0123 | Network root fault location based on network topology and alarm | — | 2021 2nd Asia Service Sciences and Software  | 未收录 | 2021 | [DOI](https://doi.org/10.1145/3456126.3456138) | — | 仅元数据 |
| RW0124 | Transformer-based Alarm Context-Vectorization Representation for Reliable Alarm Root Cau | — | 2021 European Conference on Optical Communic | 未收录 | 2021 | [DOI](https://doi.org/10.1109/ecoc52684.2021.9606141) | — | 仅元数据 |
| RW0125 | Alarm Correlation Method Using Bayesian Network in Telecommunications Networks | — | 2022 23rd Asia-Pacific Network Operations an | C | 2022 | [DOI](https://doi.org/10.23919/apnoms56106.2022.9919924) | — | 仅元数据 |
| RW0126 | Dealing with Security Alert Flooding: Using Machine Learning for Domain-independent Aler | — | ACM Transactions on Privacy and Security | B | 2022 | [DOI](https://doi.org/10.1145/3510581) | — | 仅元数据 |
| RW0127 | A-RCL: An Adaptive Incident Prediction and Automated Root Cause Localization System for  | A-RCL | NOMS 2023-2023 IEEE/IFIP Network Operations  | 未收录 | 2023 | [DOI](https://doi.org/10.1109/noms56928.2023.10154309) | — | 仅元数据 |
| RW0128 | ACTOR: Alarm Correlation and Ticketing for Open ROADM | ACTOR | NOMS 2023-2023 IEEE/IFIP Network Operations  | 未收录 | 2023 | [DOI](https://doi.org/10.1109/noms56928.2023.10154414) | — | 仅元数据 |
| RW0129 | Alarm reduction and root cause inference based on association mining in communication ne | — | Frontiers in Computer Science | 未收录 | 2023 | [DOI](https://doi.org/10.3389/fcomp.2023.1211739) | — | 仅元数据 |
| RW0130 | APGNN: Alarm Propagation Graph Neural Network for fault detection and alarm root cause a | APGNN | Computer Networks | B | 2023 | [DOI](https://doi.org/10.1016/j.comnet.2022.109485) | — | 仅元数据 |
| RW0131 | Incident-aware Duplicate Ticket Aggregation for Cloud Systems | iPACK | 2023 IEEE/ACM 45th International Conference  | A | 2023 | [DOI](https://doi.org/10.1109/icse48619.2023.00193) | — | 仅元数据 |
| RW0132 | Recommending Root-Cause and Mitigation Steps for Cloud Incidents using Large Language Mo | — | 2023 IEEE/ACM 45th International Conference  | A | 2023 | [DOI](https://doi.org/10.1109/icse48619.2023.00149) | — | 仅元数据 |
| RW0133 | AlarmGPT: an intelligent alarm analyzer for optical networks using a generative pre-trai | AlarmGPT | Journal of Optical Communications and Networ | C | 2024 | [DOI](https://doi.org/10.1364/jocn.521913) | — | 仅元数据 |
| RW0134 | Causality Enhanced Graph Representation Learning for Alert-Based Root Cause Analysis | — | 2024 IEEE 24th International Symposium on Cl | C | 2024 | [DOI](https://doi.org/10.1109/ccgrid59990.2024.00018) | — | 仅元数据 |
| RW0136 | Improving Fault Device Identification Method using Alarm Clustering Approach | — | 2024 20th International Conference on Networ | 未收录 | 2024 | [DOI](https://doi.org/10.23919/cnsm62983.2024.10814367) | — | 仅元数据 |
| RW0137 | Knowledge-aware Alert Aggregation in Large-scale Cloud Systems: a Hybrid Approach | COLA | Proceedings of the 46th International Confer | 不适用（非正式论文轨道） | 2024 | [DOI](https://doi.org/10.1145/3639477.3639745) | — | 仅元数据 |
| RW0138 | Leveraging Large Language Models for Efficient Alert Aggregation in AIOPs | — | Electronics | C | 2024 | [DOI](https://doi.org/10.3390/electronics13224425) | — | 仅元数据 |
| RW0139 | Alert Summarization for Online Service Systems by Validating Propagation Paths of Faults | — | Proceedings of the ACM on Software Engineeri | 待核实 | 2025 | [DOI](https://doi.org/10.1145/3729367) | — | 摘要已读 |
| RW0141 | Graph Structure-Enhanced Large Language Model for Optical Network Fault Diagnosis: An Ex | — | IEEE Internet of Things Journal | C | 2025 | [DOI](https://doi.org/10.1109/jiot.2025.3573056) | — | 仅元数据 |
| RW0142 | HyperLAC: Hypergraph-based Large-scale Alert Classification with spatial-temporal contex | HyperLAC | Knowledge-Based Systems | C | 2025 | [DOI](https://doi.org/10.1016/j.knosys.2025.114712) | — | 仅元数据 |
| RW0143 | Multi-modal Data Fusion with Knowledge Graph for Alarm Root Cause Analysis in Optical Ne | — | 2025 30th OptoElectronics and Communications | 未收录 | 2025 | [DOI](https://doi.org/10.23919/oecc/psc62146.2025.11109870) | — | 仅元数据 |
| RW0144 | Network Device Alarm Reduction based on Root Cause Analysis | — | 2025 International Conference on Computer, I | 未收录 | 2025 | [DOI](https://doi.org/10.1109/ciotsc67482.2025.11413218) | — | 仅元数据 |
| RW0145 | Rule-Based Root Cause Analysis of Site Outages in Mobile Networks: A Deterministic Appro | — | 2025 12th International Conference on Electr | 未收录 | 2025 | [DOI](https://doi.org/10.1109/iceee67194.2025.11261920) | — | 仅元数据 |
| RW0146 | Alarm Correlation Method for Large-Scale Carrier Network Considering Topology Error Prob | — | ICC 2026 - IEEE International Conference on  | C | 2026 | [DOI](https://doi.org/10.1109/icc59461.2026.11587858) | — | 仅元数据 |
| RW0147 | FedSTGAT: Federated Spatio-Temporal Graph Attention Network for Root Alarm Identificatio | FedSTGAT | IEEE Transactions on Cognitive Communication | C | 2026 | [DOI](https://doi.org/10.1109/tccn.2026.3694892) | — | 仅元数据 |
| RW0140 | AmocRCA: At Most One Change Segmentation and Relative Correlation Ranking for Root Cause | AmocRCA | Proceedings of the 33rd ACM International Co | A |  | [DOI](https://doi.org/10.1145/3696630.3731612) | — | 仅元数据 |
| RW0135 | Dynamic Alert Suppression Policy for Noise Reduction in AIOps | — | Proceedings of the 46th International Confer | 不适用（非正式论文轨道） |  | [DOI](https://doi.org/10.1145/3639477.3639752) | — | 仅元数据 |
| RW0148 | LLM-Guided Graph Structure Learning for Alert Convergence in AIOps | — | Computers | C |  | [DOI](https://doi.org/10.3390/computers15070412) | — | 仅元数据 |

### RDMA/PFC 与可编程网络机制溯源（25 条）

| paper_id | 题名 | 简称 | venue | 等级 | 年份 | 链接 | 全文 | 阅读深度 |
|---|---|---|---|---|---|---|---|---|
| RW0042 | Congestion Control for Large-Scale RDMA Deployments | — | Proceedings of the 2015 ACM Conference on Sp | A | 2015 | [DOI](https://doi.org/10.1145/2785956.2787484) | — | 仅元数据 |
| RW0043 | Deadlocks in Datacenter Networks | — | Proceedings of the 15th ACM Workshop on Hot  | 不适用（非正式论文轨道） | 2016 | [DOI](https://doi.org/10.1145/3005745.3005760) | — | 仅元数据 |
| RW0044 | Closing the Network Diagnostics Gap with Vigil | — | Proceedings of the SIGCOMM Posters and Demos | 不适用（非正式论文轨道） | 2017 | [DOI](https://doi.org/10.1145/3123878.3131979) | — | 仅元数据 |
| RW0045 | Revisiting network support for RDMA | — | Proceedings of the 2018 Conference of the AC | A | 2018 | [DOI](https://doi.org/10.1145/3230543.3230557) | — | 仅元数据 |
| RW0046 | Fault diagnosis based on dial-test data in datacenter networks | — | Journal of Systems Engineering and Electroni | 未收录 | 2019 | [DOI](https://doi.org/10.21629/jsee.2019.05.19) | — | 仅元数据 |
| RW0047 | Flow Event Telemetry on Programmable Data Plane | — | Proceedings of the Annual conference of the  | A | 2020 | [DOI](https://doi.org/10.1145/3387514.3406214) | — | 仅元数据 |
| RW0048 | PINT: Probabilistic In-band Network Telemetry | PINT | Proceedings of the Annual conference of the  | A | 2020 | [DOI](https://doi.org/10.1145/3387514.3405894) | — | 仅元数据 |
| RW0049 | VTrace: Automatic Diagnostic System for Transient Network Problems in Datacenters | VTrace | Proceedings of the Annual conference of the  | A | 2020 | [DOI](https://doi.org/10.1145/3387514.3405851) | — | 仅元数据 |
| RW0050 | ITSY: Initial Trigger-Based PFC Deadlock Detection in the Data Plane | ITSY | IEEE INFOCOM 2021 - IEEE Conference on Compu | 不适用（非正式论文轨道） | 2021 | [DOI](https://doi.org/10.1109/infocomwkshps51825.2021.9484601) | — | 仅元数据 |
| RW0051 | Diagnosing End-Host Network Bottlenecks in RDMA Servers | — | IEEE/ACM Transactions on Networking | A | 2024 | [DOI](https://doi.org/10.1109/tnet.2024.3416419) | — | 仅元数据 |
| RW0052 | Hostmesh: Monitor and Diagnose Networks in Rail-optimized RoCE Clusters | Hostmesh | Proceedings of the 8th Asia-Pacific Workshop | 不适用（非正式论文轨道） | 2024 | [DOI](https://doi.org/10.1145/3663408.3663426) | — | 仅元数据 |
| RW0053 | INSERT: In-Network Stateful End-to-End RDMA Telemetry | INSERT | IEEE INFOCOM 2024 - IEEE Conference on Compu | A | 2024 | [DOI](https://doi.org/10.1109/infocom52122.2024.10621203) | — | 仅元数据 |
| RW0054 | OFC: An Original Congestion-Based Fine-grained Priority Flow Control | OFC | 2024 21st Annual IEEE International Conferen | B | 2024 | [DOI](https://doi.org/10.1109/secon64284.2024.10934869) | — | 仅元数据 |
| RW0055 | POSTER: RDMA Network Performance Anomalies Diagnosis with Hawkeye | — | Proceedings of the ACM SIGCOMM 2024 Conferen | 不适用（非正式论文轨道） | 2024 | [DOI](https://doi.org/10.1145/3672202.3673711) | — | 仅元数据 |
| RW0056 | Roundabout: Solving PFC Deadlocks With Distributed Detection and Buffer Collaboration | Roundabout | 2024 IEEE 32nd International Conference on N | B | 2024 | [DOI](https://doi.org/10.1109/icnp61940.2024.10858514) | — | 仅元数据 |
| RW0057 | ByteTracker: An Agentless and Real-time Path-aware Network Probing System | ByteTracker | Proceedings of the ACM SIGCOMM 2025 Conferen | A | 2025 | [DOI](https://doi.org/10.1145/3718958.3750515) | — | 仅元数据 |
| RW0058 | Congestion Patterns in a Large-scale RDMA Datacenter | — | Proceedings of the 2025 ACM Internet Measure | B | 2025 | [DOI](https://doi.org/10.1145/3730567.3764494) | — | 仅元数据 |
| RW0059 | NetScope: Fault Localization in Programmable Networking Systems With Low-Cost In-Band Ne | NetScope | IEEE Transactions on Networking | A | 2025 | [DOI](https://doi.org/10.1109/ton.2025.3590034) | — | 仅元数据 |
| RW0060 | Argus: Scalable and Deterministic Network Fault Localization for AI Training Clusters | Argus | Proceedings of the 10th Asia-Pacific Worksho | 不适用（非正式论文轨道） | 2026 | [DOI](https://doi.org/10.1145/3820441.3820449) | — | 仅元数据 |
| RW0061 | CCL-D: A High-Precision Diagnostic System for Slow and Hang Anomalies in Large-Scale Mod | CCL-D | Proceedings of the 31st ACM SIGPLAN Annual S | A | 2026 | [DOI](https://doi.org/10.1145/3774934.3786429) | — | 仅元数据 |
| RW0062 | Fine-grained and Non-intrusive LLM Training Monitoring via Microsecond-level Traffic Mea | — | Proceedings of the 31st ACM International Co | A | 2026 | [DOI](https://doi.org/10.1145/3779212.3790163) | — | 仅元数据 |
| RW0063 | PRISM: Workload-Aware Autonomous Network Fault Recovery for Hyperscale AI Training Fabri | PRISM | 2026 IEEE 19th International Conference on C | C | 2026 | [DOI](https://doi.org/10.1109/cloud72782.2026.00045) | — | 仅元数据 |
| RW0064 | RDMATracer: A scalable eBPF-based framework for tracing RDMA syscalls | RDMATracer | Proceedings of the ACM SIGCOMM 2026 Conferen | A | 2026 | [DOI](https://doi.org/10.1145/3789240.3828742) | — | 仅元数据 |
| RW0065 | Vedrfolnir: RDMA Network Performance Anomalies Diagnosis in Collective Communications | Vedrfolnir | IEEE INFOCOM 2026 - IEEE Conference on Compu | A | 2026 | [DOI](https://doi.org/10.1109/infocom59046.2026.11571395) | — | 仅元数据 |
| RW0066 | FLARE: Anomaly Diagnostics for Divergent LLM Training in GPU Clusters of Thousand-Plus S | FLARE | 23rd USENIX Symposium on Networked Systems D | A |  | [链接](https://www.usenix.org/conference/nsdi26/presentation/cui) | [全文](https://www.usenix.org/conference/nsdi26/presentation/cui) | 仅元数据 |

## L2 相邻场景（64 条）


### 微服务/云 RCA（38 条）

| paper_id | 题名 | 简称 | venue | 等级 | 年份 | 链接 | 全文 | 阅读深度 |
|---|---|---|---|---|---|---|---|---|
| RW0222 | Canopy: End-to-End Performance Tracing And Analysis | Canopy | Proceedings of the 26th Symposium on Operati | A | 2017 | [DOI](https://doi.org/10.1145/3132747.3132749) | — | 仅元数据 |
| RW0223 | Localizing Failure Root Causes in a Microservice through Causality Inference (MicroCause | — | 2020 IEEE/ACM 28th International Symposium o | B | 2020 | [DOI](https://doi.org/10.1109/iwqos49365.2020.9213058) | — | 仅元数据 |
| RW0224 | Fast Outage Analysis of Large-Scale Production Clouds with Service Correlation Mining | — | 2021 IEEE/ACM 43rd International Conference  | A | 2021 | [DOI](https://doi.org/10.1109/icse43902.2021.00085) | — | 仅元数据 |
| RW0225 | Horus: Non-Intrusive Causal Analysis of Distributed Systems Logs | Horus | 2021 51st Annual IEEE/IFIP International Con | B | 2021 | [DOI](https://doi.org/10.1109/dsn48987.2021.00035) | — | 仅元数据 |
| RW0226 | Identifying Root-Cause Metrics for Incident Diagnosis in Online Service Systems | — | 2021 IEEE 32nd International Symposium on So | B | 2021 | [DOI](https://doi.org/10.1109/issre52982.2021.00022) | — | 仅元数据 |
| RW0227 | MicroRank: End-to-End Latency Issue Localization with Extended Spectrum Analysis in Micr | MicroRank | Proceedings of the Web Conference 2021 | A | 2021 | [DOI](https://doi.org/10.1145/3442381.3449905) | — | 仅元数据 |
| RW0229 | Anomaly Detection and Failure Root Cause Analysis in (Micro) Service-Based Cloud Applica | — | ACM Computing Surveys | 待核实 | 2022 | [DOI](https://doi.org/10.1145/3501297) | — | 仅元数据 |
| RW0230 | Causal Inference-Based Root Cause Analysis for Online Service Systems with Intervention  | — | Proceedings of the 28th ACM SIGKDD Conferenc | A | 2022 | [DOI](https://doi.org/10.1145/3534678.3539041) | — | 仅元数据 |
| RW0231 | Graph based Incident Extraction and Diagnosis in Large-Scale Online Systems | — | Proceedings of the 37th IEEE/ACM Internation | A | 2022 | [DOI](https://doi.org/10.1145/3551349.3556904) | — | 仅元数据 |
| RW0232 | Mining root cause knowledge from cloud service incident investigations for AIOps | — | Proceedings of the 44th International Confer | 不适用（非正式论文轨道） | 2022 | [DOI](https://doi.org/10.1145/3510457.3513030) | — | 仅元数据 |
| RW0233 | Root Cause Analysis of Failures in Microservices Through Causal Discovery | RCD | Advances in Neural Information Processing Sy | A | 2022 | [DOI](https://doi.org/10.52202/068431-2259) | — | 仅元数据 |
| RW0234 | CausalRCA: Causal inference based precise fine-grained root cause localization for micro | CausalRCA | Journal of Systems and Software | B | 2023 | [DOI](https://doi.org/10.1016/j.jss.2023.111724) | — | 仅元数据 |
| RW0235 | Eadro: An End-to-End Troubleshooting Framework for Microservices on Multi-source Data | Eadro | 2023 IEEE/ACM 45th International Conference  | A | 2023 | [DOI](https://doi.org/10.1109/icse48619.2023.00150) | — | 仅元数据 |
| RW0236 | Fault Injection Based Interventional Causal Learning for Distributed Applications | — | Proceedings of the AAAI Conference on Artifi | A | 2023 | [DOI](https://doi.org/10.1609/aaai.v37i13.26868) | — | 仅元数据 |
| RW0237 | Interdependent Causal Networks for Root Cause Localization | REASON | Proceedings of the 29th ACM SIGKDD Conferenc | A | 2023 | [DOI](https://doi.org/10.1145/3580305.3599849) | — | 仅元数据 |
| RW0238 | Sleuth: A Trace-Based Root Cause Analysis System for Large-Scale Microservices with Grap | Sleuth | Proceedings of the 28th ACM International Co | A | 2023 | [DOI](https://doi.org/10.1145/3623278.3624758) | — | 仅元数据 |
| RW0240 | TraceArk: Towards Actionable Performance Anomaly Alerting for Online Service Systems | TraceArk | 2023 IEEE/ACM 45th International Conference  | 不适用（非正式论文轨道） | 2023 | [DOI](https://doi.org/10.1109/icse-seip58684.2023.00029) | — | 仅元数据 |
| RW0241 | TraceDiag: Adaptive, Interpretable, and Efficient Root Cause Analysis on Large-Scale Mic | TraceDiag | Proceedings of the 31st ACM Joint European S | A | 2023 | [DOI](https://doi.org/10.1145/3611643.3613864) | — | 仅元数据 |
| RW0242 | TrinityRCL: Multi-Granular and Code-Level Root Cause Localization Using Multiple Types o | TrinityRCL | IEEE Transactions on Software Engineering | A | 2023 | [DOI](https://doi.org/10.1109/tse.2023.3241299) | — | 仅元数据 |
| RW0243 | BARO: Robust Root Cause Analysis for Microservices via Multivariate Bayesian Online Chan | BARO | Proceedings of the ACM on Software Engineeri | 待核实 | 2024 | [DOI](https://doi.org/10.1145/3660805) | — | 仅元数据 |
| RW0244 | Diagnosing Performance Issues for Large-Scale Microservice Systems With Heterogeneous Gr | — | IEEE Transactions on Services Computing | A | 2024 | [DOI](https://doi.org/10.1109/tsc.2024.3402172) | — | 仅元数据 |
| RW0245 | GAMMA: Graph Neural Network-Based Multi-Bottleneck Localization for Microservices Applic | GAMMA | Proceedings of the ACM Web Conference 2024 | A | 2024 | [DOI](https://doi.org/10.1145/3589334.3645665) | — | 仅元数据 |
| RW0246 | Holistic Root Cause Analysis for Failures in Cloud-Native Systems Through Observability  | — | IEEE Transactions on Services Computing | A | 2024 | [DOI](https://doi.org/10.1109/tsc.2024.3478759) | — | 仅元数据 |
| RW0247 | MicroFI: Non-Intrusive and Prioritized Request-Level Fault Injection for Microservice Ap | MicroFI | IEEE Transactions on Dependable and Secure C | A | 2024 | [DOI](https://doi.org/10.1109/tdsc.2024.3363902) | — | 仅元数据 |
| RW0248 | Microservice Root Cause Analysis With Limited Observability Through Intervention Recogni | — | Proceedings of the 30th ACM SIGKDD Conferenc | A | 2024 | [DOI](https://doi.org/10.1145/3637528.3671530) | — | 仅元数据 |
| RW0249 | Systemizing and Mitigating Topological Inconsistencies in Alibaba's Microservice Call-gr | — | Proceedings of the 15th ACM/SPEC Internation | B | 2024 | [DOI](https://doi.org/10.1145/3629526.3645043) | — | 仅元数据 |
| RW0250 | Trace-based Multi-Dimensional Root Cause Localization of Performance Issues in Microserv | — | Proceedings of the IEEE/ACM 46th Internation | A | 2024 | [DOI](https://doi.org/10.1145/3597503.3639088) | — | 仅元数据 |
| RW0251 | Failure Diagnosis in Microservice Systems: A Comprehensive Survey and Analysis | — | ACM Transactions on Software Engineering and | A | 2025 | [DOI](https://doi.org/10.1145/3715005) | — | 仅元数据 |
| RW0252 | Intelligent Root Cause Localization in MicroService Systems: A Survey and New Perspectiv | — | ACM Computing Surveys | 待核实 | 2025 | [DOI](https://doi.org/10.1145/3736755) | — | 仅元数据 |
| RW0253 | RCAEval: A Benchmark for Root Cause Analysis of Microservice Systems with Telemetry Data | RCAEval | Companion Proceedings of the ACM on Web Conf | 不适用（非正式论文轨道） | 2025 | [DOI](https://doi.org/10.1145/3701716.3715290) | — | 仅元数据 |
| RW0254 | AnoMod: A Dataset for Anomaly Detection and Root Cause Analysis in Microservice System | AnoMod | Proceedings of the 23rd International Confer | C | 2026 | [DOI](https://doi.org/10.1145/3793302.3793324) | — | 仅元数据 |
| RW0255 | CARE: Context Aware Root Cause Identification Using Distributed Traces and Profiling Met | CARE | IEEE Transactions on Software Engineering | A | 2026 | [DOI](https://doi.org/10.1109/tse.2025.3645143) | — | 仅元数据 |
| RW0257 | TORAI: Multi-source Root Cause Analysis for Blind Spots in Microservice Service Call Gra | TORAI | Proceedings of the ACM on Software Engineeri | 待核实 | 2026 | [DOI](https://doi.org/10.1145/3808137) | — | 仅元数据 |
| RW0258 | TrainTicketTrace: A Multi-Fault Distributed Dataset for Microservice Fault Detection and | — | 2026 IEEE International Conference on Softwa | 不适用（非正式论文轨道） | 2026 | [DOI](https://doi.org/10.1109/saner-c67878.2026.00051) | — | 仅元数据 |
| RW0259 | TVDiag: A Task-oriented and View-invariant Failure Diagnosis Framework for Microservice- | TVDiag | ACM Transactions on Software Engineering and | A | 2026 | [DOI](https://doi.org/10.1145/3734868) | — | 仅元数据 |
| RW0228 | Practical Root Cause Localization for Microservice Systems via Trace Analysis | — | 2021 IEEE/ACM 29th International Symposium o | B |  | [DOI](https://doi.org/10.1109/iwqos52092.2021.9521340) | — | 仅元数据 |
| RW0256 | Semi-Supervised and Disentangled Causal Discovery for Analyzing Fault Propagation in Mic | — | IEEE Access | 未收录 |  | [DOI](https://doi.org/10.1109/access.2026.3667143) | — | 仅元数据 |
| RW0239 | The PetShop Dataset -- Finding Causes of Performance Issues across Microservices | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2311.04806) | [全文](https://arxiv.org/abs/2311.04806) | 摘要已读 |

### 依赖推断、故障注入与参考图构造（26 条）

| paper_id | 题名 | 简称 | venue | 等级 | 年份 | 链接 | 全文 | 阅读深度 |
|---|---|---|---|---|---|---|---|---|
| RW0197 | Request extraction in Magpie | — | Proceedings of the 11th workshop on ACM SIGO | 未收录 | 2004 | [DOI](https://doi.org/10.1145/1133572.1133608) | — | 仅元数据 |
| RW0198 | Towards highly reliable enterprise network services via inference of multi-level depende | — | Proceedings of the 2007 conference on Applic | C | 2007 | [DOI](https://doi.org/10.1145/1282380.1282383) | — | 仅元数据 |
| RW0200 | Detailed diagnosis in enterprise networks | NetMedic | Proceedings of the ACM SIGCOMM 2009 conferen | A | 2009 | [DOI](https://doi.org/10.1145/1592568.1592597) | — | 仅元数据 |
| RW0202 | Experimentation in Software Engineering | — | — | 待核实 | 2012 | [DOI](https://doi.org/10.1007/978-3-642-29044-2) | — | 仅元数据 |
| RW0203 | A Platform for Automating Chaos Experiments | — | 2016 IEEE International Symposium on Softwar | 不适用（非正式论文轨道） | 2016 | [DOI](https://doi.org/10.1109/issrew.2016.52) | — | 仅元数据 |
| RW0204 | “Automated Debugging Considered Harmful” Considered Harmful: A User Study Revisiting the | — | 2016 IEEE International Conference on Softwa | B | 2016 | [DOI](https://doi.org/10.1109/icsme.2016.67) | — | 仅元数据 |
| RW0205 | What Can We Learn from Four Years of Data Center Hardware Failures? | — | 2017 47th Annual IEEE/IFIP International Con | B | 2017 | [DOI](https://doi.org/10.1109/dsn.2017.26) | — | 仅元数据 |
| RW0206 | Fail-Slow at Scale: Evidence of Hardware Performance Faults in Large Production Systems | — | ACM Transactions on Storage | A | 2018 | [DOI](https://doi.org/10.1145/3242086) | — | 仅元数据 |
| RW0207 | Open-World Knowledge Graph Completion | — | Proceedings of the AAAI Conference on Artifi | A | 2018 | [DOI](https://doi.org/10.1609/aaai.v32i1.11535) | — | 仅元数据 |
| RW0208 | An Open-Source Benchmark Suite for Microservices and Their Hardware-Software Implication | — | Proceedings of the Twenty-Fourth Internation | A | 2019 | [DOI](https://doi.org/10.1145/3297858.3304013) | — | 仅元数据 |
| RW0209 | Automating Chaos Experiments in Production | — | 2019 IEEE/ACM 41st International Conference  | 不适用（非正式论文轨道） | 2019 | [DOI](https://doi.org/10.1109/icse-seip.2019.00012) | — | 仅元数据 |
| RW0210 | Debugging Incidents in Google’s Distributed Systems | — | Queue | 未收录 | 2020 | [DOI](https://doi.org/10.1145/3400899.3404974) | — | 仅元数据 |
| RW0211 | Characterizing Microservice Dependency and Performance: Alibaba Trace Analysis | — | Proceedings of the ACM Symposium on Cloud Co | B | 2021 | [DOI](https://doi.org/10.1145/3472883.3487003) | — | 仅元数据 |
| RW0212 | Frisbee: A Suite for Benchmarking Systems Recovery | Frisbee | Proceedings of the 1st Workshop on High Avai | 未收录 | 2021 | [DOI](https://doi.org/10.1145/3447851.3458738) | — | 仅元数据 |
| RW0213 | Understanding the use of spectrum‐based fault localization | — | Journal of Software: Evolution and Process | 未收录 | 2023 | [DOI](https://doi.org/10.1002/smr.2622) | — | 仅元数据 |
| RW0219 | Sifting Truth from Coincidences: A Two-Stage Positive and Unlabeled Learning Model for C | — | 2025 40th IEEE/ACM International Conference  | A | 2025 | [DOI](https://doi.org/10.1109/ase63991.2025.00127) | — | 仅元数据 |
| RW0220 | An Empirical Evaluation of Kubernetes Resilience in Cloud–Edge Deployments Using Failure | — | Proceedings of the 2026 Australasian Compute | 未收录 | 2026 | [DOI](https://doi.org/10.1145/3793811.3793823) | — | 仅元数据 |
| RW0221 | Chaos experiments in microservice architectures: A systematic literature review | — | Computer Standards &amp; Interfaces | 未收录 | 2026 | [DOI](https://doi.org/10.1016/j.csi.2025.104116) | — | 仅元数据 |
| RW0201 | Application dependency discovery using matrix factorization | — | 2012 IEEE 20th International Workshop on Qua | 不适用（非正式论文轨道） |  | [DOI](https://doi.org/10.1109/iwqos.2012.6245965) | — | 仅元数据 |
| RW0215 | Chaos Engineering in the Wild: Findings from GitHub | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2505.13654) | [全文](https://arxiv.org/abs/2505.13654) | 摘要已读 |
| RW0214 | Chaos Engineering: A Multi-Vocal Literature Review | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2412.01416) | [全文](https://arxiv.org/abs/2412.01416) | 摘要已读 |
| RW0216 | Complexity at Scale: A Quantitative Analysis of an Alibaba Microservice Deployment | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2504.13141) | [全文](https://arxiv.org/abs/2504.13141) | 摘要已读 |
| RW0217 | OpenRCA: Can Large Language Models Locate the Root Cause of Software Failures? | OpenRCA | International Conference on Learning Represe | A |  | [链接](https://github.com/microsoft/OpenRCA) | — | 仅元数据 |
| RW0196 | Pinpoint: problem determination in large, dynamic Internet services | Pinpoint | Proceedings International Conference on Depe | B |  | [DOI](https://doi.org/10.1109/dsn.2002.1029005) | — | 仅元数据 |
| RW0218 | Retrofitting Service Dependency Discovery in Distributed Systems | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2510.15490) | [全文](https://arxiv.org/abs/2510.15490) | 摘要已读 |
| RW0199 | X-Trace: A Pervasive Network Tracing Framework | X-Trace | 4th USENIX Symposium on Networked Systems De | A |  | [链接](https://www.usenix.org/conference/nsdi-07/x-trace-pervasive-network-tracing-framework) | [全文](https://www.usenix.org/conference/nsdi-07/x-trace-pervasive-network-tracing-framework) | 仅元数据 |

## L3 方法基础（47 条）


### 方法基础（43 条）

| paper_id | 题名 | 简称 | venue | 等级 | 年份 | 链接 | 全文 | 阅读深度 |
|---|---|---|---|---|---|---|---|---|
| RW0264 | Investigating Causal Relations by Econometric Models and Cross-spectral Methods | — | Econometrica | 未收录 | 1969 | [DOI](https://doi.org/10.2307/1912791) | — | 仅元数据 |
| RW0265 | Spectra of some self-exciting and mutually exciting point processes | — | Biometrika | 未收录 | 1971 | [DOI](https://doi.org/10.1093/biomet/58.1.83) | — | 仅元数据 |
| RW0266 | An Algorithm for Fast Recovery of Sparse Causal Graphs | — | Social Science Computer Review | 未收录 | 1991 | [DOI](https://doi.org/10.1177/089443939100900106) | — | 仅元数据 |
| RW0267 | Causation, Prediction, and Search | — | — | 待核实 | 2001 | [DOI](https://doi.org/10.7551/mitpress/1754.001.0001) | — | 仅元数据 |
| RW0269 | The max-min hill-climbing Bayesian network structure learning algorithm | — | Machine Learning | B | 2006 | [DOI](https://doi.org/10.1007/s10994-006-6889-7) | — | 仅元数据 |
| RW0270 | A survey of graph edit distance | — | Pattern Analysis and Applications | C | 2009 | [DOI](https://doi.org/10.1007/s10044-008-0141-y) | — | 仅元数据 |
| RW0275 | Structural Intervention Distance for Evaluating Causal Graphs | — | Neural Computation | B | 2015 | [DOI](https://doi.org/10.1162/neco_a_00708) | — | 仅元数据 |
| RW0276 | The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary C | — | PLOS ONE | 未收录 | 2015 | [DOI](https://doi.org/10.1371/journal.pone.0118432) | — | 仅元数据 |
| RW0277 | Recurrent Marked Temporal Point Processes | — | Proceedings of the 22nd ACM SIGKDD Internati | A | 2016 | [DOI](https://doi.org/10.1145/2939672.2939875) | — | 仅元数据 |
| RW0280 | Causal network reconstruction from time series: From theoretical assumptions to practica | — | Chaos: An Interdisciplinary Journal of Nonli | 未收录 | 2018 | [DOI](https://doi.org/10.1063/1.5025050) | — | 仅元数据 |
| RW0285 | Detecting and quantifying causal associations in large nonlinear time series datasets | — | Science Advances | 未收录 | 2019 | [DOI](https://doi.org/10.1126/sciadv.aau4996) | — | 仅元数据 |
| RW0286 | Review of Causal Discovery Methods Based on Graphical Models | — | Frontiers in Genetics | 未收录 | 2019 | [DOI](https://doi.org/10.3389/fgene.2019.00524) | — | 仅元数据 |
| RW0291 | Causal inference for time series analysis: problems, methods and evaluation | — | Knowledge and Information Systems | B | 2021 | [DOI](https://doi.org/10.1007/s10115-021-01621-0) | — | 仅元数据 |
| RW0292 | Neural Granger Causality | — | IEEE Transactions on Pattern Analysis and Ma | A | 2021 | [DOI](https://doi.org/10.1109/tpami.2021.3065601) | — | 仅元数据 |
| RW0295 | A Survey on Causal Discovery: Theory and Practice | — | International Journal of Approximate Reasoni | B | 2022 | [DOI](https://doi.org/10.1016/j.ijar.2022.09.004) | — | 仅元数据 |
| RW0296 | Causal Discovery in Hawkes Processes by Minimum Description Length | — | Proceedings of the AAAI Conference on Artifi | A | 2022 | [DOI](https://doi.org/10.1609/aaai.v36i6.20656) | — | 仅元数据 |
| RW0303 | Causal Discovery Evaluation Framework in the Absence of Ground-Truth Causal Graph | — | IEEE Access | 未收录 | 2024 | [DOI](https://doi.org/10.1109/access.2024.3456233) | — | 仅元数据 |
| RW0306 | A large-scale benchmark for network inference from single-cell perturbation data | — | Communications Biology | 未收录 | 2025 | [DOI](https://doi.org/10.1038/s42003-025-07764-y) | — | 仅元数据 |
| RW0279 | Causal Discovery from Nonstationary/Heterogeneous Data: Skeleton Estimation and Orientat | — | — | 待核实 |  | [链接](https://www.ijcai.org/proceedings/2017/187) | [全文](https://www.ijcai.org/proceedings/2017/187) | 仅元数据 |
| RW0299 | Causal Discovery from Temporal Data: An Overview and New Perspectives | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2303.10112) | [全文](https://arxiv.org/abs/2303.10112) | 摘要已读 |
| RW0283 | Causal Discovery with Attention-Based Convolutional Neural Networks | — | Machine Learning and Knowledge Extraction | B |  | [DOI](https://doi.org/10.3390/make1010019) | — | 仅元数据 |
| RW0284 | Causal Discovery with Reinforcement Learning | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/1906.04477) | [全文](https://arxiv.org/abs/1906.04477) | 摘要已读 |
| RW0287 | CAUSE: Learning Granger Causality from Event Sequences using Attribution Methods | CAUSE | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2002.07906) | [全文](https://arxiv.org/abs/2002.07906) | 摘要已读 |
| RW0281 | Conditional independence testing based on a nearest-neighbor estimator of conditional mu | — | International Conference on Artificial Intel | C |  | [链接](http://proceedings.mlr.press/v84/runge18a.html) | [全文](http://proceedings.mlr.press/v84/runge18a.html) | 摘要已读 |
| RW0300 | CUTS: Neural Causal Discovery from Irregular Time-Series Data | CUTS | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2302.07458) | [全文](https://arxiv.org/abs/2302.07458) | 摘要已读 |
| RW0282 | DAGs with NO TEARS: Continuous Optimization for Structure Learning | — | Advances in Neural Information Processing Sy | A |  | [链接](https://neurips.cc/virtual/2018/poster/11901) | — | 摘要已读 |
| RW0288 | Discovering contemporaneous and lagged causal relations in autocorrelated nonlinear time | — | Conference on Uncertainty in Artificial Inte | B |  | [链接](https://proceedings.mlr.press/v124/runge20a.html) | [全文](https://proceedings.mlr.press/v124/runge20a.html) | 摘要已读 |
| RW0289 | DYNOTEARS: Structure Learning from Time-Series Data | DYNOTEARS | International Conference on Artificial Intel | C |  | [链接](https://proceedings.mlr.press/v108/pamfil20a.html) | [全文](https://proceedings.mlr.press/v108/pamfil20a.html) | 摘要已读 |
| RW0271 | Estimation of a Structural Vector Autoregression Model Using Non-Gaussianity | — | Journal of Machine Learning Research | A |  | [链接](https://www.jmlr.org/papers/v11/hyvarinen10a.html) | [全文](https://www.jmlr.org/papers/v11/hyvarinen10a.html) | 仅元数据 |
| RW0297 | Gradient-Based Neural DAG Learning | — | arXiv preprint | 不适用（预印本） |  | [链接](https://doi.org/10.1017/9781009023405.009) | — | 仅元数据 |
| RW0290 | High-recall causal discovery for autocorrelated time series with latent confounders | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2007.01884) | [全文](https://arxiv.org/abs/2007.01884) | 摘要已读 |
| RW0298 | Learning granger causality for non-stationary Hawkes processes | — | Neurocomputing | C |  | [DOI](https://doi.org/10.1016/j.neucom.2021.10.030) | — | 仅元数据 |
| RW0304 | Learning Granger Causality from Instance-wise Self-attentive Hawkes Processes | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2402.03726) | [全文](https://arxiv.org/abs/2402.03726) | 摘要已读 |
| RW0273 | Learning high-dimensional directed acyclic graphs with latent and selection variables | — | The Annals of Statistics | C |  | [DOI](https://doi.org/10.1214/11-aos940) | — | 仅元数据 |
| RW0293 | Neural Temporal Point Processes: A Review | — | Proceedings of the Thirtieth International J | B |  | [DOI](https://doi.org/10.24963/ijcai.2021/623) | — | 仅元数据 |
| RW0272 | On causal discovery from time series data using FCI | — | 5th European Workshop on Probabilistic Graph | 不适用（非正式论文轨道） |  | [链接](https://researchportal.helsinki.fi/en/publications/on-causal-discovery-from-time-series-data-using-fci/) | — | 仅元数据 |
| RW0268 | Optimal Structure Identification With Greedy Search | — | Journal of Machine Learning Research | A |  | [链接](https://www.jmlr.org/papers/v3/chickering02b.html) | [全文](https://www.jmlr.org/papers/v3/chickering02b.html) | 仅元数据 |
| RW0274 | Rate-Agnostic (Causal) Structure Learning | — | Advances in Neural Information Processing Sy | A |  | [链接](https://proceedings.neurips.cc/paper_files/paper/2015/hash/e0ab531ec312161511493b002f9be2ee-Abstract.html) | [全文](https://proceedings.neurips.cc/paper_files/paper/2015/hash/e0ab531ec312161511493b002f9be2ee-Abstract.html) | 仅元数据 |
| RW0301 | Self-Compatibility: Evaluating Causal Discovery without Ground Truth | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2307.09552) | [全文](https://arxiv.org/abs/2307.09552) | 摘要已读 |
| RW0305 | Separation-based distance measures for causal graphs | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2402.04952) | [全文](https://arxiv.org/abs/2402.04952) | 摘要已读 |
| RW0302 | Shapley-PC: Constraint-based Causal Structure Learning with a Shapley Inspired Framework | Shapley-PC | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/2312.11582) | [全文](https://arxiv.org/abs/2312.11582) | 摘要已读 |
| RW0278 | The Neural Hawkes Process: A Neurally Self-Modulating Multivariate Point Process | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/1612.09328) | [全文](https://arxiv.org/abs/1612.09328) | 摘要已读 |
| RW0294 | Universal Transformer Hawkes process | — | 2021 International Joint Conference on Neura | C |  | [DOI](https://doi.org/10.1109/ijcnn52387.2021.9533810) | — | 摘要已读 |

### 图评价度量（3 条）

| paper_id | 题名 | 简称 | venue | 等级 | 年份 | 链接 | 全文 | 阅读深度 |
|---|---|---|---|---|---|---|---|---|
| RW0262 | A Ladder of Causal Distances | — | Proceedings of the Thirtieth International J | B |  | [DOI](https://doi.org/10.24963/ijcai.2021/277) | — | 仅元数据 |
| RW0263 | Precision/Recall on Imbalanced Test Data | — | International Conference on Artificial Intel | C |  | [链接](https://proceedings.mlr.press/v206/shang23a.html) | [全文](https://proceedings.mlr.press/v206/shang23a.html) | 摘要已读 |
| RW0261 | Structural Intervention Distance (SID) for Evaluating Causal Graphs | — | arXiv.org | 不适用（预印本） |  | [链接](https://arxiv.org/abs/1306.1043) | [全文](https://arxiv.org/abs/1306.1043) | 摘要已读 |

### 图结构学习（1 条）

| paper_id | 题名 | 简称 | venue | 等级 | 年份 | 链接 | 全文 | 阅读深度 |
|---|---|---|---|---|---|---|---|---|
| RW0260 | Sub-Local Constraint-Based Learning of Bayesian Networks Using A Joint Dependence Criter | — | Journal of Machine Learning Research | A |  | [链接](https://jmlr.org/papers/v14/mahdi13a.html) | [全文](https://jmlr.org/papers/v14/mahdi13a.html) | 仅元数据 |
