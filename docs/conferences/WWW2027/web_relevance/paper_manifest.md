# WWW 2024–2026 网络相关论文清单（候选、去重、筛选与阅读状态）

> 调研执行：2026-09-11。范围：**The ACM Web Conference / WWW 2024、2025、2026**，
> 不含同名的 *World Wide Web* 期刊。本文件记录检索入口、筛选理由、轨道核验、
> 下载与抽取状态。**只列经过核验的事实；未能核验的一律标注 UNKNOWN。**

## 0. 阅读本文件的三个层次

| 集合 | 定义 | 篇数 |
|---|---|---|
| **核心集** | 实际研究通信网络（DCN、骨干/WAN、传输、拥塞控制、流量工程、网络测量） | 见 §2 |
| **相邻集** | 微服务／容器／云运维诊断（研究对象不是网络本身，但任务形态最接近本项目） | 见 §3 |
| **对照集** | Web 生态测量（CDN、DNS、移动接入），Web 关联方式值得对照 | 见 §4 |

三个集合**不得混同统计**。Industry / Companion 轨道与 Research 轨道分开标注，
Industry 论文只作写作参考，**不能作为 Research Track 的录用先例证据**。

---

## 1. 逐年检索记录

### 1.1 检索入口与可达性

| 年份 | 入口 | 本次结果 | 备注 |
|---|---|---|---|
| 2024 | `https://www2024.thewebconf.org/accepted/research-tracks/` | **200**，解析出 405 条 | Research Track 正式录用目录 |
| 2024 | `https://www2024.thewebconf.org/accepted/industry/` | **200**，解析出 51 条 | Industry Track 正式目录 |
| 2025 | `https://archives.iw3c2.org/www2025/www2025-proceedings.pdf` | **200**，6 574 225 字节，112 页 | IW3C2 官方存档论文集前置部分，含完整 TOC（443 条题录 + DOI + 页码） |
| 2025 | `https://www2025.thewebconf.org/...` | **不可达** | 服务端 TLS 握手失败（`ssl3_read_n:unexpected eof`），换 TLS 版本、HTTP/1.1 均失败；改用 IW3C2 存档 |
| 2026 | `https://www2026.thewebconf.org/accepted/research-tracks.html` | **200**，解析出 676 条，按 track 分组 | Research Track 正式目录 |
| 2026 | `https://www2026.thewebconf.org/accepted/industry.html` | **200**，解析出 57 条 | Industry Track 正式目录 |
| 2027 | `https://www2027.thewebconf.org/research-track-papers/` | **200** | Research Track CFP，见 [cfp_www2027.md](cfp_www2027.md) |

**访问失败的检索入口（记录在案，未绕过）**

| 入口 | 状态 | 处置 |
|---|---|---|
| `dl.acm.org` / `dlnext.acm.org` | 自动化请求 **403**（Cloudflare 机器人校验） | 不绕过；改查作者稿／arXiv／机构仓库；仍失败的记入 §6 |
| `dblp.org` / `dblp.uni-trier.de` | **Anubis 工作量证明挑战** | 不编写求解器绕过；改用会议官方目录与 IW3C2 存档 |
| `openreview.net`（`/pdf`、`/attachment`、`api2`） | **403**（应用层错误页） | 不绕过；改查 arXiv 与作者稿 |
| `*.github.io` | **DNS 不解析**（本网络） | 改用 `raw.githubusercontent.com/<user>/<repo>/...` 取同一文件 |
| `web.archive.org` / `archive.org` / `core.ac.uk` / `scholar.archive.org` | 连接超时或 403 | 放弃该路线 |
| `zenodo.org` API | 403（"unusual traffic"） | 放弃 |

### 1.2 检索词

按年份分别以会议名 + 以下词组合检索，再人工排除歧义：
`datacenter`、`data center network`、`backbone`、`WAN`、`inter-datacenter`、
`network measurement`、`transport`、`congestion control`、`routing`、`traffic engineering`、
`fault diagnosis`、`packet`、`RDMA`、`QUIC`、`DNS`、`CDN`、`satellite/LEO`、
`microservice`、`Kubernetes`、`cloud`、`root cause`、`alert`、`anomaly`、`reliability`、`SRE`。

**歧义排除规则**：`network` 一词在 WWW 大量出现于图神经网络、社交网络、道路交通网络、
影响力传播等语境，凡研究对象不是通信网络的，一律排除，不计入核心集。

### 1.3 检索记录的已知局限

- 三年目录**均已逐条解析**（2024: 405+51；2025: 443 条 TOC；2026: 676+57），
  但**未做穷尽式全文核验**：核心集与相邻集之外的条目只看题名与作者。
- 2025 年的 track 归属来自会议官方 front matter，但该存档只提供**会话（Session）分组**
  而非 10 个投稿 track 的分组；本文件对 2025 论文统一标注为
  "2025 主论文集（Research Track，DOI 前缀 `10.1145/3696410`）"。
- 2026 年 DOI 前缀区分：主论文集 `10.1145/3774904`，Companion `10.1145/3774905`。
- **不报告"近三年网络论文总数"或主题占比**：未检出不等于不存在，目录解析也不等于全文核验。

---

## 2. 核心集：实际研究通信网络的论文

### 2.1 已深读（具备 PDF、全文抽取、Introduction 与抽取 QA）

| paper_id | 题名 | 年 / 轨道 | DOI | 来源与版本 | 分析卡 |
|---|---|---|---|---|---|
| `www24-wise-start` | Cold Start or Hot Start? Robust Slow Start in Congestion Control with A Priori Knowledge for Mobile Web Services | 2024 Research | 10.1145/3589334.3645393 | 作者稿（raw.githubusercontent），ACM 排版 | [卡](papers/www24-wise-start/analysis.md) |
| `www24-inart` | InArt: In-Network Aggregation with Route Selection for Accelerating Distributed Training | 2024 Research | 10.1145/3589334.3645394 | 作者稿（fangjin.site） | [卡](papers/www24-inart/analysis.md) |
| `www24-quic-fast` | QUIC is not Quick Enough over Fast Internet | 2024 Research | 印为 10.1145/3589334.3645323（**未独立核实**） | arXiv 2310.09423 | [卡](papers/www24-quic-fast/analysis.md) |
| `www24-starlink-multi` | A Multifaceted Look at Starlink Performance | 2024 Research | 10.1145/3589334.3645328 | arXiv 2310.09242 | [卡](papers/www24-starlink-multi/analysis.md) |
| `www25-adnpm` | Unveiling Network Performance in the Wild: An Ad-Driven Analysis of Mobile Download Speeds | 2025 Research | 10.1145/3696410.3714761 | 作者稿（ix.cs.uoregon.edu） | [卡](papers/www25-adnpm/analysis.md) |
| `www25-odns` | ODNS Clustering: Unveiling Client-Side Dependency in Open DNS Infrastructure | 2025 Research | 10.1145/3696410.3714834 | 作者 camera-ready（raw.githubusercontent） | [卡](papers/www25-odns/analysis.md) |
| `www26-starlink-cd` | Investigating Web Content Delivery Performance over Starlink | 2026 Research（`Systems and Infrastructure for Web, Mobile, and Web of Things`，rfp1111） | 10.1145/3774904.3792227 | arXiv 2510.13710v1 | [卡](papers/www26-starlink-cd/analysis.md) |
| `www26-jittersketch` | JitterSketch: Finding Jittery Flows in Network Streams | 2026 Research（`Web Mining and Content Analysis`，DOI 10.1145/3774904.3792328） | 10.1145/3774904.3792328 | 作者项目页（wenjunli.com） | [卡](papers/www26-jittersketch/analysis.md) |

### 2.2 已核实身份、**未能取得全文**（见 §6 原因）

以下论文经 Crossref / OpenAlex / Unpaywall 核实为 **gold open access (CC-BY)**，
但每一篇的被索引公开全文位置**都只有 `dl.acm.org`**，该站对本机自动化请求返回 403，
且不存在 arXiv 预印本、作者主页副本或机构仓库副本。**未绕过访问控制。**

| paper_id | 题名 | 年 / 轨道 | DOI |
|---|---|---|---|
| `www24-ares` | ARES: Predictable Traffic Engineering under Controller Failures in SD-WANs | 2024 Research | 10.1145/3589334.3645321 |
| `www24-satguard` | SatGuard: Concealing Endless and Bursty Packet Losses in LEO Satellite Networks for Delay-Sensitive Web Applications | 2024 Research | 10.1145/3589334.3645639 |
| `www25-x-clusterlink` | X-ClusterLink: An Efficient Cross-Cluster Communication Framework in Multi-Kubernetes Clusters | 2025 Research | 10.1145/3696410.3714846 |
| `www25-miresga` | Miresga: Accelerating Layer-7 Load Balancing with Programmable Switches | 2025 Research | 10.1145/3696410.3714809 |
| `www25-merkury` | MerKury: Adaptive Resource Allocation to Enhance the Kubernetes Performance for Large-Scale Clusters | 2025 Research | 10.1145/3696410.3714844 |
| `www26-meteor` | Meteor: High-Performance Control Message Delivery for Large-Scale Clouds | 2026 Research（`Systems and Infrastructure…`，rfp0542） | 10.1145/3774904.3792135 |
| `www26-beeqos` | BeeQoS: A Cloud-Native QoS System for Adaptive and Scalable Multi-Priority Bandwidth Guarantees | 2026 Research（rfp2587） | 10.1145/3774904.3792487 |
| `www26-wiseswap` | Wiseswap: Elastic Datacenter Network-Aware Disaggregated Memory for Multi-Tenant Cloud | 2026 Research（`Systems and Infrastructure…`） | 10.1145/3774904.3792309 |
| `www26-starlink-dns` | Starlink in the Wild: Multi-Perspective Measurements via DNS | 2026 Research（rfp1813） | 10.1145/3774904.3792366 |
| `www26-dc-forecast` | Macro-Micro Collaborative Learning for Logical Data Center Microservice Indicators Forecasting | 2026 Research（`Systems and Infrastructure…`） | 10.1145/3774904.3792125 |

> **注意**：`www25-miresga` 存在期刊扩展版 *Miresga: Achieving High-Performance and Reliable
> Layer-7 Load Balancing with Programmable Switches*, IEEE Trans. Computers 75(10):3683–3697 (2026),
> DOI 10.1109/TC.2026.3715854，同样未取得。若引用其性能数字，须先核对以哪一版为准。

### 2.3 已核实录用、本次未深读

| 题名 | 年 / 轨道 | 处置 |
|---|---|---|
| A Worldwide View on the Reachability of Encrypted DNS Services | 2024 Research | 已深读，见 §4.3 |
| Discovering and Measuring CDNs Prone to Domain Fronting | 2024 Research | 已深读，见 §4.3 |
| DirectFaaS: A Clean-Slate Network Architecture for Efficient Serverless Chain Communications | 2024 Research | 核心集候选，未深读（题名已核验） |
| Meet Challenges of RTT Jitter, A Hybrid Internet Congestion Control Algorithm | 2024 Research | 核心集候选，未深读（题名已核验） |
| Proteus: Towards Accurate and Low-overhead In-Network Malicious Traffic Detection | 2026 Research | 未深读 |
| SemFuzz: A Semantics-Aware Fuzzing Framework for Network Protocol Implementations | 2026 Research | 未深读 |
| Helios: Learning and Adaptation of Matching Rules for Continual In-Network Malicious Traffic Detection | 2025 Research | 未深读 |
| Tracking the Stray Sheep: Understanding DNS Response Manipulation in the Wild | 2026 Research | 未深读 |
| Eclipse Attacks on Ethereum's Peer-to-Peer Network | 2026 Research | 未深读 |

---

## 3. 相邻集：微服务 / 容器 / 云运维诊断

纳入理由：**研究对象不是通信网络**，因此不属于核心集；但其任务形态（多源遥测 → 故障定位）
与本项目最接近，必须单独比较，不能用它们的 Web relevance 论证直接支持我们的定位。
**必须防止的误用**：把这些论文的输出当作"图"，或把故障注入数据的可信度当作真实事件证据。

| paper_id | 题名 | 年 / 轨道 | DOI | 分析卡 |
|---|---|---|---|---|
| `www24-mulan` | MULAN: Multi-modal Causal Structure Learning and Root Cause Analysis for Microservice Systems | 2024 Research | 10.1145/3589334.3645442 | [卡](papers/www24-mulan/analysis.md) |
| `www24-gamma` | GAMMA: Graph Neural Network-Based Multi-Bottleneck Localization for Microservices Applications | 2024 Research | 10.1145/3589334.3645665 | [卡](papers/www24-gamma/analysis.md) |
| `www26-metakube` | MetaKube: An Experience-Aware LLM Framework for Kubernetes Failure Diagnosis | 2026 Research | 10.1145/3774904.3792631 | [卡](papers/www26-metakube/analysis.md) |
| `comp25-flow-of-action` | Flow-of-Action: SOP Enhanced LLM-Based Multi-Agent System for Root Cause Analysis | 2025 **Industry / Companion**（DOI 前缀 `10.1145/3701716`） | 见卡片（论文首页印有 DOI） | [卡](papers/comp25-flow-of-action/analysis.md) |

未深读的相邻条目：`www24-industry` 的 *Dependency Aware Incident Linking in Large Cloud Systems*、
*SOIL: Score Conditioned Diffusion Model for Imbalanced Cloud Failure Prediction*（均 Industry Track）；
`www26` 的 *TraceLLM: Evaluating and Exploring Large Language Models on Trace Analysis in
Microservice-based Web Applications*（rfp0705）、*Smart Eye: LLM-Guided Proposer-Verifier Framework
for Industrial-Scale Log Anomaly Detection*（Industry，ind0103）。

> **Smart Eye 陷阱（已复核）**：`netman.aiops.org` 上标注为该文 "Paper" 的链接
> 指向的是同课题组另一篇 WWW 2026 论文 *ViTs: Teaching Machines to See Time Series
> Anomalies Like Human Experts*（7 632 909 字节，13 页，首页题名不符）。
> **不要用该链接作为 Smart Eye 的全文来源。**

---

## 4. 对照集：Web 生态测量

纳入理由：这些论文**测量对象本身就是 Web 交付栈**（CDN、DNS、移动接入、页面加载），
用于对照"Web 关联可以有多强"，以及"强关联需要什么数据前提"。
它们**不研究数据中心内部网络**，不能计入核心集。

| paper_id | 题名 | 年 / 轨道 | DOI | 分析卡 |
|---|---|---|---|---|
| `www24-cdn-fronting` | Discovering and Measuring CDNs Prone to Domain Fronting | 2024 Research | 10.1145/3589334.3645656 | [卡](papers/www24-cdn-fronting/analysis.md) |
| `www24-encdns` | A Worldwide View on the Reachability of Encrypted DNS Services | 2024 Research | 10.1145/3589334.3645539 | [卡](papers/www24-encdns/analysis.md) |
| `www25-odns` | ODNS Clustering: Unveiling Client-Side Dependency in Open DNS Infrastructure | 2025 Research | 10.1145/3696410.3714834 | [卡](papers/www25-odns/analysis.md) |
| `www25-adnpm` | Unveiling Network Performance in the Wild: An Ad-Driven Analysis of Mobile Download Speeds | 2025 Research | 10.1145/3696410.3714761 | [卡](papers/www25-adnpm/analysis.md) |
| `www26-starlink-cd` | Investigating Web Content Delivery Performance over Starlink | 2026 Research | 10.1145/3774904.3792227 | [卡](papers/www26-starlink-cd/analysis.md) |
| `www24-starlink-multi` | A Multifaceted Look at Starlink Performance | 2024 Research | 10.1145/3589334.3645328 | [卡](papers/www24-starlink-multi/analysis.md) |

---

## 5. 题名核验中发现的更正

| 对象 | 旧记录 | 核验后 | 依据 |
|---|---|---|---|
| `www25-ipdb` | "A High-precision IP Level Industry Categorization of Web Services" | 正式题名带系统名前缀：**"IPdb: A High-precision IP Level Industry Categorization of Web Services"** | 2025 IW3C2 官方 TOC |
| `www24-quic-fast` | 未见 DOI 记录 | 该 arXiv PDF 自带的 ACM Reference Format 印有 `10.1145/3589334.3645323`；**本任务未独立核实其可解析性** | 论文首页 ACM Reference Format 区块 |
| `www24-mulan` | — | arXiv 版首页题名**不带** "MULAN: … for Microservice Systems" 后缀；摘要中出现 MULAN，作者与录用信息一致 | arXiv 2402.02357 首页 |
| `www26-starlink-cd` | 前序自动调研称"关联仅出现在引言" | **更正**：Web 是它的**测量对象本身**（TTFB、整页取回、`CF-Cache-Status`、DNS 缓存命中），不是包装 | 分析卡 §2 |
| `comp25-flow-of-action` | 前序称未取得 DOI | **更正**：论文首页与 front matter 均印有 DOI | 分析卡 |

---

## 6. 下载、抽取与阅读状态对账

### 6.1 PDF 与全文抽取

| 项 | 数量 |
|---|---|
| 纳入深读的论文 | 14 |
| 取得 PDF 且通过 `%PDF` 头 + `%%EOF` + 首页题名核验 | **14** |
| 全文抽取成功、无需 OCR | **14** |
| 抽取 QA 发现问题的 | 见 6.3 |

**工具**：`tools/pdf_to_text.py`（双栏阅读顺序 + 段落重建 + 页码标记）、
`tools/extract_intro.py`（Introduction 定位 + P1…Pn 编号）、
`tools/parse_accepted_listings.py`（官方目录解析）。
复跑命令见 [README](README.md#复跑命令)。

**版本警告**：多篇使用 arXiv 预印本或作者稿，**其页码 ≠ ACM 正式版页码**。
每张分析卡的"原始 PDF"行均记录了版本；引用页码时须注明版本。

### 6.2 未能取得全文的论文（13 篇）

- `www24-ares`、`www24-satguard`
- `www25-x-clusterlink`、`www25-miresga`、`www25-ipdb`、`www25-merkury`
- `www26-starlink-dns`、`www26-meteor`、`www26-beeqos`、`www26-wiseswap`、
  `www26-tracellm`、`www26-dc-forecast`
- `ind26-smart-eye`

**失败原因（统一）**：Unpaywall / OpenAlex / Crossref / Semantic Scholar 四家一致报告
`gold OA (CC-BY)`，但 `locations[]` 中**每篇只有一条**，且均为 `dl.acm.org/doi/pdf/...`；
该站对本机返回 403。arXiv 按题名、系统名与作者名三路检索均无预印本。

**处置**：如实记为"身份已核验、全文未取得"，**不用摘要或第三方页面补成全文分析**。
这 13 篇**不进入** [synthesis.md](synthesis.md) 的横向矩阵，其对结论的影响在
[synthesis.md](synthesis.md) §5 明确说明。

### 6.3 抽取 QA 记录

| 项 | 结果 |
|---|---|
| 首页、Introduction 首尾、下一节边界 | 14 篇逐篇目视核对 |
| 跨栏阅读顺序 | 全部正确；双栏页自动识别（`two_column_pages`） |
| 需要 OCR 的页 | **0** |
| 已知噪声 | 部分 arXiv 版式的图形坐标轴标签、作者块会混入 Introduction 区域，已在 `extract_intro.py` 中按题注/邮箱/机构/脚注模式过滤；残余噪声在分析卡中按"非正文"处理 |
| 抽取文本含页码标记 | 是（`<<<PDFPAGE n>>>`），可逐段回查 PDF |
| Introduction 与原文的关系 | `papers/<id>/analysis.md` 的引用位置以 `<<<PDFPAGE n>>>` 为准；抽取原文不单独入库，避免与 ACM 版权冲突 |

---

## 7. 维护约定

- 新增论文时同时更新本文件 §2–§4、`papers/<id>/analysis.md` 与 [synthesis.md](synthesis.md)。
- 若日后取得 §6.2 的 13 篇全文，**不要覆盖**本节记录：新增行并注明取得日期与来源。
- 本文件中的 DOI 与页码以实际核验为准；UNKNOWN 项保持 UNKNOWN，不猜测填充。

---

# §T006 — 复用表与定向补取（2026-09-12，T006 执行）

> 本节由 T006 追加。**不覆盖** §1–§7 的任何记录：失败项、版本差异与 UNKNOWN 一律保留。
> 本轮的阅读结论见 [argument_chains.md](argument_chains.md)，
> 迁移判断见 [rpg_recon_argument_transfer.md](rpg_recon_argument_transfer.md)。

## T006.1 复用表

「与 DCN 的距离」指该论文的研究对象与"数据中心内部网络"的接近程度。
「本轮只需核对什么」是本轮**实际**投入的核对范围，不等于该篇已完成全面 QA。

### 第一优先：DCN / 云内部通信

| paper_id | 与 DCN 的距离 | 现有材料 | 已知错误 / 未决项 | 本轮只需核对什么 | 是否需补全文 |
| --- | --- | --- | --- | --- | --- |
| `www24-inart` | **DCN**（训练集群内网、可编程交换机） | PDF + 全文 + Intro + 卡 | Intro 记 P1–P15，实为 **P1–P6**（P7–P15 是 bullet 碎片）；卡 §2 "venue-driven"表述过宽 | 论证链的每一步承接；引言行业名与实验负载是否对应 | **否** |
| `www26-meteor` | 云内控制消息 | 仅身份（DOI/官方目录） | 全文未取得 | — | **是** |
| `www26-beeqos` | 云内多优先级带宽保障 | 仅身份 | 全文未取得 | — | **是** |
| `www26-wiseswap` | DCN 网络感知解耦内存 | 仅身份 | 全文未取得 | — | **是** |
| `www25-x-clusterlink` | 多 K8s 跨集群通信 | 仅身份 | 全文未取得 | — | **是** |
| `www25-miresga` | L7 负载均衡（可编程交换机） | 仅身份 | 全文未取得；另有 IEEE TC 75(10) 期刊扩展版，若引用须先定版本 | — | **是** |
| `www25-merkury` | 大规模集群资源分配 | 仅身份 | 全文未取得 | — | **是** |
| `www26-dc-forecast` | 数据中心微服务指标预测 | 仅身份 | 全文未取得 | — | 可选 |

### 第二优先：骨干网、WAN 与传输

| paper_id | 与 DCN 的距离 | 现有材料 | 已知错误 / 未决项 | 本轮只需核对什么 | 是否需补全文 |
| --- | --- | --- | --- | --- | --- |
| `www26-jittersketch` | 骨干网（核心交换机数据面） | PDF + 全文 + Intro + 卡 | Intro 记 P1–P39，实为 **P1–P19**（P20–P39 属 §2.1） | 三个 use case 各自的实验覆盖 | **否** |
| `www24-wise-start` | 传输层（移动 Web 接入） | PDF + 全文 + Intro + 卡 | Intro 记 P1–P20，实为 **P1、P3–P8 共 7 段**；生产 RCT 与仿真 First AFT 曾被并列 | 两个头条数字各自的评估环境 | **否** |
| `www24-quic-fast` | 传输层（HTTP/3 栈） | PDF + 全文 + Intro + 卡 | 未发现新增 | 协议栈位置如何充当 Web 关联 | **否** |
| `www24-ares` | SD-WAN 流量工程 | 仅身份 | 全文未取得；`download_batchA.tsv` 的 CLOSED/is_oa=false 与 manifest 的 gold OA 记录**冲突**，未解决 | — | **是** |
| `www24-satguard` | LEO 卫星（Web 应用定向） | 仅身份 | 全文未取得 | — | **是** |

### 对照集：Web 生态测量（Web 关联更强的层次，用于比较链条长度）

| paper_id | 与 DCN 的距离 | 现有材料 | 已知错误 / 未决项 | 本轮只需核对什么 | 是否需补全文 |
| --- | --- | --- | --- | --- | --- |
| `www26-starlink-cd` | 接入网 + CDN/DNS | PDF + 全文 + Intro + 卡 | 卡 §6 记"PoP 距离解释 50% 方差"无正文支撑，**本轮仍未找到** | 具名案例的论证链（B1 模板来源） | **否** |
| `www24-cdn-fronting` | CDN | PDF + 全文 + Intro + 卡 | 未发现新增 | "负担不起的前提 → 已有观测面"的重述写法 | **否** |
| `www24-encdns` / `www25-odns` | DNS | PDF + 全文 + Intro + 卡 | ODNS 的受控 ADNS + 唯一 A 记录是**测量设计**，不据此判定自证循环（T005 R6） | 是否只是"对象在 Web 栈上" | **否** |
| `www24-starlink-multi` / `www25-adnpm` | 接入网 | PDF + 全文 + Intro + 卡 | 未发现新增 | 具名应用/平台如何充当 Web 关联 | **否** |

### 相邻集：微服务与云运维诊断（任务形态最近、Web 论证最弱）

| paper_id | 与 DCN 的距离 | 现有材料 | 已知错误 / 未决项 | 本轮只需核对什么 | 是否需补全文 |
| --- | --- | --- | --- | --- | --- |
| `www24-mulan` | 微服务（非网络） | PDF + 全文 + Intro + 卡 | 卡 §2 "只剩会议归属"**已被本轮更正**：Web 联系由评测负载提供（Online Boutique 等） | 联系究竟由谁提供 | **否** |
| `www24-gamma` | 微服务（非网络） | PDF + 全文 + Intro + 卡 | 未发现新增 | 领域命名与业务后果措辞 | **否** |
| `www26-metakube` | 容器编排（非网络） | PDF + 全文 + Intro + 卡 | 未发现新增 | 正文是否含 Web 论证 | **否** |
| `comp25-flow-of-action` | 微服务（**Industry/Companion**） | PDF + 全文 + Intro + 卡 | 未发现新增；**不得作为 Research 先例** | 不引用为定位依据 | **否** |

> **去重口径**：`www25-odns`、`www25-adnpm`、`www26-starlink-cd`、`www24-starlink-multi`
> 同时出现在核心集与对照集，按 paper_id 去重后总数为 14（§6.1 的口径不变）。
> 本篇 §T006 的分类按**本轮用途**划分，不改变 §2–§4 的集合归属。

## T006.2 定向补取结果

**补取目标**（按对结论的改变潜力排序）：
① 云内部通信与控制消息（`www26-meteor`）；② 资源保障与负载均衡
（`www26-beeqos`、`www25-miresga`）；③ DCN 内的新形态（`www26-wiseswap`、
`www25-x-clusterlink`、`www25-merkury`）；④ 骨干/WAN（`www24-ares`、`www24-satguard`）。

**本轮的检索角度**（在 T005 已试过的"四家元数据 + arXiv 三路检索"之外新增）：
作者个人/课题组主页、机构仓库与预印本平台、元数据代理站、作者的 GitHub 仓库、
会议官方站点与 IW3C2 存档、厂商技术博客。
**未绕过任何访问控制**（未写 Anubis 求解器、未用无头浏览器穿透 Cloudflare、未使用 Sci-Hub 类站点）。

### T006.2.1 本轮**未取得任何新的全文**

**结论**：第一优先级与第二优先级的 8 篇目标论文，**本轮仍未取得全文**。
T005 记录的失败原因（唯一公开位置是 `dl.acm.org`，该站对自动化请求返回 403）
在本轮**没有被推翻**，只是被更细地定位了「哪一步失败」。

**本轮实际试过且返回真实结果（非 403）的入口**：

| 入口 | 结果 |
| --- | --- |
| `api.crossref.org` / `api.openalex.org`（DOI 直查） | 可用于身份核验；不提供全文位置 |
| `www.semanticscholar.org` 论文页 | **可达**，提供题名、作者、部分摘要；无 PDF |
| 机构仓库（如 `ir.nwpu.edu.cn`） | **本机无法抓取**（域名被网络策略拦截，非站点问题） |
| `dl.acm.org/doi/<DOI>`（摘要页） | **本次返回了页面**（与 T005 的"全线 403"不同），但仍需 Premium 才能读正文 |
| `openreview.net/forum?id=…`（Miresga） | 有论坛条目；该站对本机 `/pdf`、`api2` 仍 403 |
| `github.com/THUNAME/Miresga` | 可达（Miresga 的配套开源仓库） |

**仍然失败**：`dl.acm.org/doi/pdf/...` 直接取 PDF；`*.github.io`（DNS 不解析）；
`web.archive.org` / `core.ac.uk`（超时或 403）。

**未绕过访问控制**：未编写 Anubis 工作量证明求解器，未用无头浏览器穿透 Cloudflare，
未使用 Sci-Hub 类站点。检索结果中出现的带 `__cf_chl_tk=` 参数的 `dl.acm.org/doi/pdf/`
链接是 Cloudflare 挑战令牌，**没有尝试使用**。

### T006.2.2 本轮新发现的**可达页面**（仅身份级；**不是全文**）

下列页面在本轮可访问，可作为后续补全的入口。**这些页面上的描述未经原文核对，
不得用于论证链结论，其包含的任何性能数字一律视为未核实。**

| paper_id | 可核验的身份要素 | 可达页面 |
| --- | --- | --- |
| `www26-meteor` | 题名、DOI、11 页；作者含 USTC 与 **Huawei Technologies** 合作者 | [dl.acm.org 摘要页](https://dl.acm.org/doi/10.1145/3774904.3792135) |
| `www26-beeqos` | 题名、DOI、pp. 5515–5524；作者含山东大学 / 浪潮云 / 泉城实验室 | [Semantic Scholar](https://www.semanticscholar.org/paper/09ce11f1fabd1a407c6494f3989f51f88c6caeb2)、[dl.acm.org](https://dl.acm.org/doi/10.1145/3774904.3792487) |
| `www26-wiseswap` | 题名、DOI、pp. 5253–5262；作者与单位为西北工业大学 | [Semantic Scholar](https://www.semanticscholar.org/paper/bf4ca95232aa7326a55a4a53796be213706f128a)、[机构仓库条目](https://ir.nwpu.edu.cn/handle/39AN3IGR/437992) |
| `www25-x-clusterlink` | 题名、DOI、pp. 2402–2412；USTC + University of Kentucky | [Semantic Scholar](https://www.semanticscholar.org/paper/4513fb9d05abbf64e937599f4744b5f83ddc715b)、[UKY 学者页](https://scholars.uky.edu/es/publications/x-clusterlink-an-efficient-cross-cluster-communication-framework-/) |
| `www25-miresga` | 题名、DOI、pp. 2424–2434；清华大学 INSC | [Semantic Scholar](https://www.semanticscholar.org/paper/d93902cc1afe82abf90465c5c0d838222323697a)、[GitHub 仓库](https://github.com/THUNAME/Miresga)、[IEEE TC 扩展版](https://ieeexplore.ieee.org/document/11617301) |
| `www24-ares` / `www24-satguard` | 本轮**未做新的可达性核验**；T005 的失败记录与本节的 `download_batchA.tsv` 冲突**仍未解决** | — |

**下一步最可能成功的具体动作**（供后续任务使用，本轮**不执行**）：

1. `www26-wiseswap`：`ir.nwpu.edu.cn` 机构仓库条目**已定位**；本机因网络策略无法抓取，
   **在可访问该域的服务器环境重试**是当前最有希望的一条。
2. `www25-miresga`：`github.com/THUNAME/Miresga` 仓库可达，检查其是否附带论文 PDF
   （注意 `*.github.io` 不可达，须走 `github.com` 或 `raw.githubusercontent.com`）。
3. `www24-ares`：先解决 `download_batchA.tsv` 的 CLOSED/is_oa=false 与 gold OA 记录的冲突，
   再决定是否值得投入。
4. **USTC 作者的机构主页**：`www26-meteor`、`www25-x-clusterlink`、`www24-inart`
   的作者同属中国科学技术大学（InArt 的 PDF 当初就是从作者主页副本取得的）。
   本轮检索观察到 `staff.ustc.edu.cn` 的 PDF 走 **http://** 而非 https，
   未在 https 入口检索到——这是一条**尚未验证**的具体线索，后续可定向重试。
5. 其余各篇：用普通浏览器登录机构订阅下载后放入 `tmp/www-web-relevance/pdf/`，
   命名与 §6.2 的 `paper_id` 一致。

> **纪律重申**：「本次未找到」只记为**本次未找到**，不写成「不存在」；
> 上述可达页面上的摘要级描述**不进入** [argument_chains.md](argument_chains.md) 的分析，
> 也不改变 §T006.1 中"是否需补全文"的判断。

**处置**：与 §6.2 一致——身份已核验、全文未取得的，**不用摘要或第三方页面补成全文分析**。
「本次未找到」只记为**本次未找到**，不写成「不存在」。

## T006.3 本轮实际阅读投入

| 项 | 数量 |
| --- | --- |
| 复用现有 PDF/全文（不重复下载） | 14 篇全部保留可用 |
| 本轮**逐句还原论证链**的样例 | **4 篇**：`www24-inart`（DCN）、`www26-jittersketch`（骨干）、`www24-wise-start`（传输）、`www26-starlink-cd`（对照） |
| 本轮**有论证链 + 关键句承接对照表**（任务书 §核心工作一.2 的完整格式） | **5 篇**：上述 4 篇 + `www24-cdn-fronting`（表在 T006-R 补齐） |
| **只有论证链、没有句群表** | `www24-cdn-fronting`（T006 初稿）——T006-R 已补 |
| **只有工作负载摘要、不是句群分析** | `www24-mulan`——**如实记为摘要**，不称"逐句还原"（T006-R 更正，原 §T006.3 写"六篇逐句还原"不实） |
| 本轮**就地更正**的分析卡 | 4 篇：`www24-inart`、`www24-wise-start`、`www26-jittersketch`、`www24-mulan` |
| 未重做 | 三年全目录扫描、全部 14 篇的格式返工、T005-R 的 R2/R3/R6 |

**未运行**：训练、推理、重评分、项目测试套件、外部 LLM API 调用。
**本机运行的程序**：仅文档链接（325 条相对链接）与编码（UTF-8/BOM）检查，
属任务书 Acceptance #8 要求的文档校验，不是研究实验或 PDF 处理程序。

## T006.4 分析卡复核更正索引

| 分析卡 | 更正内容 | 位置 |
| --- | --- | --- |
| `papers/www24-inart/analysis.md` | Intro 段落号 P1–P6；"venue-driven"表述收窄为"Web 只在动机层承重"；CCS 与 KEYWORDS 两处自述不可只取其一 | §10 |
| `papers/www24-wise-start/analysis.md` | Intro 正文段落 P1、P3–P8 共 7 段；确认生产 RCT / 仿真 First AFT 的分离 | §10 |
| `papers/www26-jittersketch/analysis.md` | 确认 Intro 止于 P19；补充"拥塞检测用例亦无独立实验"；引用不得省略 "simulation" | §10 |
| `papers/www24-mulan/analysis.md` | **§2 "只剩会议归属"判断作废**（T005 R1）；改为三栏：作者表述无 / 工作负载联系有 / 业务验证无 | §2 顶部提示 + §10 |

**未在本索引中的篇目**：`www26-starlink-cd` 与 `www24-cdn-fronting` **本轮被引用，但不在上述四卡更正之列**
（T006 初稿误写"本轮未引用"，T006-R 更正）。它们的分析卡本轮**未做正文更正**，
旧卡问题保留未决状态；引用时以 [argument_chains.md](argument_chains.md)
§4.1–§4.2（含 T006-R 新增的 §4.1.1、§4.1.2、§4.2.1）为准。
其余未被引用的篇目，其旧卡问题同样保留未决，**不要求全面返工**。
