# WWW 近三年网络相关论文检索与投稿契合分析

> 调研日期：2026-09-10。范围：The ACM Web Conference（WWW）2024、2025、2026 论文，不含同名 *World Wide Web* 期刊。本文服务于 Pingmesh 故障传播图重构的投稿定位，不是系统性综述或穷尽目录。

## 1. 结论与投稿决策

**网络、云基础设施与运维诊断可以进入 WWW Research Track。最有说服力的结合方式，是把基础设施上的技术问题与它支撑的 Web 服务要求连起来，并让实验测到这条关系。**

本次核验到的研究论文包括传输协议 WiseStart、网内聚合 InArt、跨 Kubernetes 集群通信 X-ClusterLink、网络测量 adNPM、Web 服务 IP 归属 IPdb，以及微服务/容器诊断 MULAN、MetaKube。它们的对象并不限于网页前端，也不要求算法本身必须专用于 HTTP。下文逐篇说明其输入、产出及 Web 关联的具体落点。

对本项目，建议维持 **WWW 2027 Research Track → Web Infrastructure and Agentic Systems**，以“支撑 Web 服务的共享数据中心网络中，面向工程师诊断的单次故障传播图恢复”为主线。这个判断来自正式征稿范围与论文先例的交叉核验，**不是录用概率预测**。

目前最需要补的是“实际支撑哪些 Web 服务、异常探测端点对应什么服务依赖、图恢复怎样改变工程师的判断”三项证据。如果数据只包含 Pingmesh 丢包、拓扑与设备告警，应先准确写成 Web 云基础设施的网络诊断；不能把探测丢包直接称为 HTTP 请求失败、用户体验下降或 SLO 违约。

## 2. 2027 正式要求：已更新，不应再沿用早期 Coming Soon 快照

[WWW 2027 Research Track CFP](https://www2027.thewebconf.org/research-track-papers/) 当前明确：

- 研究范围包含理解、评价和改进作为技术基础设施的 Web。
- 每篇投稿必须在**第一页**说明与 Web 及所选 track 的关系。
- 仅使用 Web 数据、API 等材料，未回答具体 Web 科学问题，不满足范围要求。
- 正式轨道列表中包括 **Web Infrastructure and Agentic Systems**。

轨道名中的 Agentic Systems 不意味着必须添加 LLM 或 agent。当前 P0 确定性证据归一化与结构约束方案，可以围绕 Web infrastructure 提交；为贴题而临时增加 agent 并不能补上服务关联证据。这里属于我们的投稿解释，CFP 并未承诺任何具体算法或行业场景必然录用。

## 3. 检索范围、路径与证据等级

### 3.1 检索方法

先检查会议研究轨道录用目录及正式论文集，再用论文完整标题查找作者稿、机构页面和代码。使用的关键词组合包括 `network / datacenter / cloud / congestion control / packet / microservice / fault / root cause / trace / Kubernetes` 与 `WWW 2024 / 2025 / 2026`。关键词召回后人工排除纯神经网络、社交网络、道路交通网络等歧义。

主要目录入口：

| 年份 | 一手入口 | 本次使用情况 |
|---|---|---|
| 2024 | [Research Track 录用目录](https://www2024.thewebconf.org/accepted/research-tracks/) | 核验 WiseStart、InArt、MULAN 均在研究轨道 |
| 2025 | [IW3C2 官方存档论文集目录](https://archives.iw3c2.org/www2025/www2025-proceedings.pdf) | 原会议主页本次访问失败，以官方存档和带正式书目信息的作者稿核对；IPdb 作者海报进一步明示 Research Track |
| 2026 | [Research 录用目录](https://www2026.thewebconf.org/accepted/research-tracks.html)、[Industry 录用目录](https://www2026.thewebconf.org/accepted/industry.html) | 核验 MetaKube、TraceLLM、Meteor、BeeQoS 与 Smart Eye 的轨道归属 |

以正式发表年份计入三年窗口；预印本最早上传年份、PDF 沿用的原会议日期和实际会议日程不混用。全文可得性及搜索引擎索引均有限，因此不报告“近三年全部网络论文数”或主题占比，也不由未检出推断某年不接受某方向。

### 3.2 证据等级

- **A：目录/正式书目与作者全文均核验。** 可分析实际问题、方法与 Web 叙事。
- **B：已核验正式归属，并有作者摘要、海报、仓库等。** 可分析已见内容，未读的实验不补写。
- **C：仅确认录用归属及题名。** 作为补充线索，不能据此推断其第一页论证或效果。

**出版载体和投稿轨道是两个字段。** Industry 论文可能收入主 Proceedings，Research 论文也可能以 poster 形式展示；不能仅凭 DOI 前缀、页数或“poster”字样推断轨道。Flow-of-Action 是 Industry Track、收入 2025 Companion；Smart Eye 是 Industry Track、收入 2026 Proceedings，二者都不能替代 Research Track 先例。

## 4. 已完成内容核验的 Research 论文矩阵

下表的“借鉴点”是本项目分析；“Web 结合方式”依据相应一手资料。不同问题的指标不能直接横比。

| 年份、论文与证据 | 输入 → 方法/产出 | Web 结合方式 | 对 Pingmesh 的借鉴与边界 |
|---|---|---|---|
| **2024 WiseStart**：*Cold Start or Hot Start? Robust Slow Start in Congestion Control with A Priori Knowledge for Mobile Web Services*；Research，A。[作者全文](https://joycezhangjia.github.io/wisestart_www24.pdf)，[DOI](https://doi.org/10.1145/3589334.3645393) | 移动传输的先验信息与运行反馈 → 更稳健的慢启动行为 | 第一页直接把慢启动和移动 Web **首屏可见内容加载时间（first AFT）**相连；技术问题与用户可感知量有明确对应 | 最强的“网络指标为何影响 Web”模板。本项目也应给出探测异常与实际服务依赖的映射；没有业务遥测时不能照搬用户时延收益 |
| **2024 InArt**：*In-Network Aggregation with Route Selection for Accelerating Distributed Training*；Research，A。[作者全文](https://www.fangjin.site/pdf/inart.pdf)，[DOI](https://doi.org/10.1145/3589334.3645394) | 分布式训练梯度、拓扑及交换机能力 → 网内聚合与路由选择，降低通信开销 | 引言从电商、社交媒体、在线广告依赖深度学习出发，再落到分布式训练的通信瓶颈 | 证明“底层网络支撑 Web 工作负载”是可用路径。但要交代真实工作负载/依赖，不能将任意数据中心任务都重命名为 Web |
| **2024 MULAN**：*Multi-modal Causal Structure Learning and Root Cause Analysis for Microservice Systems*；Research，A。[作者全文](https://zhengzhangchen.github.io/publication/MULAN_WWW24.pdf)，[DOI](https://doi.org/10.1145/3589334.3645442) | 日志、指标与 KPI → 多模态结构学习，随机游走产生根因排序 | 微服务故障影响用户体验；诊断服务于恢复可靠运行，CCS 包含 Web log analysis | 与本项目最直接的 WWW RCA 先例，也说明“多源数据 + 图 + 根因定位”不足以独占新意。需区别其用于根因回溯的学习图，与我们需要逐条核验的 incident 设备传播 DAG |
| **2025 X-ClusterLink**：*An Efficient Cross-Cluster Communication Framework in Multi-Kubernetes Clusters*；Research/main proceedings，A。[公开投稿稿](https://openreview.net/pdf?id=l5zRaRSBn0)，[作者机构正式摘要](https://scholars.uky.edu/es/publications/x-clusterlink-an-efficient-cross-cluster-communication-framework-)，[DOI](https://doi.org/10.1145/3696410.3714846) | 跨集群同步和转发流量 → broker、聚合网关、XDP 与容错转发 | Kubernetes 托管 Web 服务；服务规模扩大导致跨集群通信要求。引言将低时延、吞吐和故障切换分别连接服务场景 | 最接近云/DCN 基础设施定位。借鉴“服务要求 → 网络瓶颈 → 设计与测量”；其目标是改善通信，不能当传播图重构 baseline。公开 PDF 是投稿版，正式书目/摘要另行核验 |
| **2025 adNPM**：*Unveiling Network Performance in the Wild: An Ad-Driven Analysis of Mobile Download Speeds*；Research/main proceedings，A。[作者全文](https://ix.cs.uoregon.edu/~ram/papers/WWW-2025.pdf)，[DOI](https://doi.org/10.1145/3696410.3714761) | 浏览器/移动应用广告中运行的下载测量 → 带宽估计及地域/用户群体分析 | 广告生态构成测量部署方式，下载速度又影响用户可访问的 Web/视频服务；用实验室验证及 15 国部署闭合证据 | 借鉴“测量机制与应用体验都相关”的双重联系。Pingmesh 属于内部主动探测，不应冒充真实 HTTP 请求测量 |
| **2025 IPdb**：*A High-precision IP Level Industry Categorization of Web Services*；Research（Web mining and content analysis），B。[作者 Research 海报](https://helinhl.github.io/assets/pdf/poster-ipdb-www2025.pdf)，[公开投稿稿](https://openreview.net/pdf?id=wzeZ2kp7jS)，[作者代码](https://github.com/IPLevelIndustryDB/IPdb)，[DOI](https://doi.org/10.1145/3696410.3714669) | IP、域名、组织信息及文本 → Web 服务的 IP 粒度行业归属数据库 | 研究对象就是 Web 服务部署的实际归属；AS 级归属无法准确替代 IP/服务粒度 | 重要启发是**实体粒度要匹配主张**：设备异常不能自动等于租户或 Web 服务异常。公开投稿稿含占位会议格式，正式题名/轨道据正式目录及作者海报核验 |
| **2026 MetaKube**：*An Experience-Aware LLM Framework for Kubernetes Failure Diagnosis*；Research，A。[作者全文](https://arxiv.org/html/2603.23580v1)，[DOI](https://doi.org/10.1145/3774904.3792631) | 故障描述、运维知识与历史处理经验 → 检索/推理和诊断建议 | 将 Kubernetes 定位为全球云部署基础设施，强调容器依赖、分散遥测和工程师难以追踪故障；关联主要通过云基础设施建立 | 说明运维诊断可在 Research 出现；但第一页对具体 Web 工作负载的关联较 WiseStart 间接。可借鉴场景限制、数据隐私和本地部署论证，不应把它当作缺少服务证据也能录用的保证 |

这组先例显示四种成立的连接：**用户体验/应用性能、支撑 Web 的云通信、Web 系统可观测性与可靠性、Web 生态的网络测量**。对当前项目最自然的是第二、第三种；若补到业务依赖和服务指标，可进一步连接第一种。

## 5. 与任务高度相关，但必须单列的 Industry / Companion 论文

| 年份、论文及轨道 | 输入 → 产出 | 可借鉴内容与引用边界 |
|---|---|---|
| **2025 Flow-of-Action**：*SOP Enhanced LLM-Based Multi-Agent System for Root Cause Analysis*；**Industry Track，Companion**。[作者声明与摘要](https://arxiv.org/abs/2502.08224)，[作者全文](https://arxiv.org/html/2502.08224v1) | 事件信息、诊断工具与 SRE 标准操作规程 → 受流程约束的工具调用和根因结论 | 最适合支持“工程师已有诊断流程，需要逐步缩小排查空间”的引入。它把 SOP 显式纳入诊断，能支持流程重要性，**不能证明我们的工程师已经手绘传播树，或某次事故用了多少分钟** |
| **2025 RCAEval**：*A Benchmark for Root Cause Analysis of Microservice Systems with Telemetry Data*；**Companion，4 页 benchmark 论文**；本次不进一步断言 demo/short 子轨道。[正式版 PDF](https://openreview.net/pdf?id=qHaowcDTzP)，[DOI](https://doi.org/10.1145/3701716.3715290)，[作者代码](https://github.com/phamquiluan/RCAEval) | 微服务故障案例及 metrics/logs/traces → RCA baseline 排名和效率评价 | 为 Web 应用后端 RCA 提供可复现评价。论文包含资源、网络和代码故障，但主要目标仍是根因排序；不能把其根因标签视作设备传播边标签。仓库持续更新，当前数据集组织方式不宜倒填到 2025 正文 |
| **2026 Smart Eye**：*LLM-Guided Proposer-Verifier Framework for Industrial-Scale Log Anomaly Detection*；**Industry Track**，官方编号 ind0103。[官方 Industry 目录](https://www2026.thewebconf.org/accepted/industry.html)，[DOI](https://doi.org/10.1145/3774904.3792804) | 云系统原始日志 → 离线规则提出与验证、在线异常检测 | 本仓库已有[详细拆解](./SmartEye_WWW2026案例拆解.md)，可借鉴 Web 服务可靠性—SRE 日志—部署开销的叙事。本次重新核验的是轨道和书目；未重新获得全文，因此不将旧文档中的规模、精度数字当作本次复核结果 |

特别说明：本次访问 NetMan 论文列表时，Smart Eye 对应的 Paper 链接实际打开 **ViTs** PDF。不要把这个链接继续当作 Smart Eye 全文来源，也不要把第三方搜索页面混排的其他论文摘要当作 Smart Eye 摘要。

## 6. 2026 的额外网络/运维先例：已核验录用，保留阅读边界

下面三篇均在 [2026 Research 目录](https://www2026.thewebconf.org/accepted/research-tracks.html)；它们加强“该会议确实接收基础设施网络工作”的证据。本次不据题名补写完整方法、Web 叙事或实测收益。

| 论文 | 已验证内容 | 下一步阅读价值 |
|---|---|---|
| *Meteor: High-Performance Control Message Delivery for Large-Scale Clouds*，rfp0542；[DOI](https://doi.org/10.1145/3774904.3792135)，[作者论文列表](https://gmzhao-ustc.github.io/) | 云控制消息传递；Research 归属；本次未得到可读作者全文，C | 核对控制面故障、网络状态与 Web 云服务可用性如何关联；不可现在就推断其故障收益指标 |
| *BeeQoS: A Cloud-Native QoS System for Adaptive and Scalable Multi-Priority Bandwidth Guarantees*，rfp2587；[DOI](https://doi.org/10.1145/3774904.3792487)，[作者代码](https://github.com/IIC-SIG-MLsys/BeeQos) | Kubernetes 内的带宽/QoS 管理；仓库有实现、部署与实验脚本，B | 借鉴网络系统复现物的组织；其具体 Web 工作负载和性能数字仍需正文核验 |
| *TraceLLM: Evaluating and Exploring Large Language Models on Trace Analysis in Microservice-based Web Applications*，rfp0705；[DOI](https://doi.org/10.1145/3774904.3792164)，[作者论文列表](https://zchenxi.github.io/publications/) | 微服务 Web 应用的 trace 分析；Research 归属；本次未得到可读作者全文，C | 可进一步检查 trace 解释和工程师任务设计；不要与同名需求追踪论文、以太坊论文或软件包混用 |

## 7. 本项目怎样形成自己的 Web relevance 闭环

### 7.1 推荐主张与方法对应

推荐研究问题：

> 在支撑 Web 服务的共享云网络中，当异常主要表现为端点间探测失败，而内部设备遥测不完整、不同步且存在歧义时，如何恢复工程师能够核验的单次故障设备传播图，并保留无法区分的解释？

这比“数据中心网络规模大，所以根因定位很难”更接近当前任务。根因候选是恢复图的条件之一，而工程师需要的产物包括内部传播关系、受影响分支、支持证据和替代假设。它仍需文献比较与实验支持，不能先行声称已有 RCA 方法从不输出图或从不考虑不确定性。

| 论证环节 | 当前能够描述的对象 | 需要提供的证据 |
|---|---|---|
| Web 依赖 | Web/云应用组件依赖共享 DCN 连通性 | 所属业务类型、服务—端点—设备依赖说明；可用脱敏聚合统计 |
| 事件触发 | Pingmesh 发现一组异常端点对，工程师转查拓扑、告警和日志 | 一次真实 incident 的可核对时间线；探测协议和异常定义 |
| 人工负担 | 工程师需要拼接故障假设与受影响分支 | 工单/访谈/诊断记录，或明确标为示意的工作流；不能将重建示意写成观察事实 |
| 科学缺口 | 同一根因可能对应不同传播结构，未知关系无法简单视作负例 | 多解释 case、oracle-root 下仍存在的图恢复误差、缺失/抖动实验 |
| 方法响应 | PC-STGR 提出 Top-K 根；P0 在原始拓扑上做根条件传播 DAG 解码 | 固定根、预测根、联合选择的分离评价；每条边对应原始拓扑与证据 |
| 价值证明 | 图帮助核查、缩小检查集合、判断不确定分支 | 工程师接受率/检查量/任务时间；只有实际测量后才声称效率或 MTTR 收益 |

### 7.2 第一页应出现的四个元素

1. **一个具体 incident**：工程师收到什么异常、最初看不到什么、怎样查拓扑和设备记录。
2. **明确依赖关系**：这些端点/设备在何种 Web 云服务环境中；用可证实的层级描述。
3. **人工中间产物与所需输出**：排障树组织检查行动，传播 DAG 组织设备影响假设。两者有关，但不是同一种图，不能直接互当标签。
4. **图恢复特有问题**：根因排序相同仍可能得出不同路径；物理邻接与时间先后都不足以唯一决定传播方向，所以要允许替代解释和未知。

### 7.3 可用于引言的英文定位句

下列句子是待结合实际部署证据采用的作者写作建议，不是文献原句：

> Web services depend on shared cloud networks, where a single incident can generate connectivity anomalies across multiple endpoint pairs. We study how to reconstruct an auditable device-level propagation graph from these symptoms, raw topology, and partial operational evidence. Rather than treating root identification as the final output, our system retains candidate origins and evaluates the propagation explanations that each origin supports.

若无法验证第一句对应当前数据的部署背景，应先补依赖说明，或将其降为一般背景并立即明确数据边界。禁止把 `can generate` 改成未测量的业务失败数量或 SLA 损失。

## 8. 引用优先级与下一步证据安排

正文无需为证明“能投 WWW”堆砌所有 WWW 论文。建议按论证用途选择：

- **Web 与网络联系**：优先 WiseStart、X-ClusterLink；若讨论 AI Web 工作负载基础设施，再加 InArt。
- **已有根因定位工作的能力边界**：优先 MULAN，配合本项目已调研的其他会议 RCA 工作，比较实际输入/输出与评测目标。
- **工程师操作流程**：Flow-of-Action 可支持 SOP 的作用；当前 case 的实际操作必须由自身记录支持。
- **评价可复现性**：RCAEval 用于说明统一故障数据、baseline 和根因评价的重要性；传播图主指标需另行调研并建立图标签。
- **工业叙事**：Smart Eye 用于借鉴结构，引用时明确 Industry Track；不引用本次尚未复核的数值。
- **扩展阅读**：MetaKube、TraceLLM、Meteor、BeeQoS 用于检查最新邻近工作；后三篇补到正文后再做精细能力比较。

本轮已完成年份覆盖、网络歧义过滤、Research/Industry/Companion 区分及可行定位。后续应按下面顺序推进实际论文，而不是继续无界扩展检索：

| 顺序 | 产物 | 完成标准 |
|---|---|---|
| 1 | 可公开的部署依赖说明 | 明确哪些服务/组件依赖哪些探测端点；不能只写“云很重要” |
| 2 | 一次 case 的证据链与工程师操作图 | 区分观察事实、人工回忆、示意流程；图中物理、观察、传播关系分开 |
| 3 | 图恢复挑战与标签协议 | 明确未知边、替代图、根条件化和方向定义；不把拓扑合法率当准确率 |
| 4 | 主张对应实验 | 根因、图、工程师任务三层评价；若暂无服务指标，限制业务收益措辞 |

**证据缺口是具体的数据和评价缺口，不是换一个 Web 关键词即可解决的写作缺口。** 本项目已有清楚的方法主线；论文应把这条主线落到 Web 基础设施的真实依赖与诊断决策上。
