# T008 检索日志（实际执行记录）

任务：T008 — 相关工作全面检索与可核验文献目录
执行：Claude Code　|　执行日：**2026-09-15**　|　检索截止日：**2026-09-15**
范围：2015-01-01 至截止日，向前回溯必要的奠基论文。

> **本文件只记录真实执行过的动作。** 未执行的检索不在此列；
> 访问失败的域名与被拒的查询在下文单列，不记为「已查无结果」。
> 覆盖缺口与停止依据见 [coverage_report.md](coverage_report.md)。

---

## 1. 执行环境与可达性（2026-09-15 实测）

| 域 / 端点 | 实测结果 | 处置 |
|---|---|---|
| `api.crossref.org` | **可用**，无配额限制 | 主检索与核验通道 |
| `api.openalex.org` | **可用但配额耗尽**：当日两次触顶，返回 `Insufficient budget ... Resets at midnight UTC` | 用于补摘要；配额耗尽后全面回落 Crossref |
| `arxiv.org/abs/<id>` | **可用**（curl，带浏览器 UA） | 预印本身份与摘要 |
| `www.usenix.org` 会议页 | **可用**，`citation_*` 元数据完整 | NSDI/ATC/OSDI 身份核验 |
| `doi.org` 重定向 | **可用** | 但通常落到被墙的出版社页 |
| `dl.acm.org`（`/doi/`、`/doi/pdf/`） | **403** | 不绕过；改用 Crossref DOI 记录 |
| `dblp.org` | **Anubis 工作量证明挑战** | 不编写求解器绕过；改用 Crossref/OpenAlex |
| 所有 `*.github.io` | **DNS 不可解析** | 改用 `raw.githubusercontent.com` |
| `api.semanticscholar.org` | **429 限流** | 未使用 |
| `export.arxiv.org` API | **Rate exceeded** | 改用 `arxiv.org/abs` 页面 |
| Python `urllib` 对 usenix/arxiv/期刊站 | **TLS 握手失败**（`UNEXPECTED_EOF_WHILE_READ`） | 全流程改用 `curl` |
| `proceedings.mlr.press` / `proceedings.neurips.cc` / `jmlr.org` / `ijcai.org` | 可用 | PMLR/NeurIPS/JMLR/IJCAI 不在 Crossref 覆盖内，改从这些官方页核验 |
| 中文期刊站（`c114.com.cn`、`opticsjournal.net`、`xb.sut.edu.cn`） | 502 / 超时 | 记录为受限，未绕过 |

**方法论后果（重要）**：Crossref **不索引** USENIX（NSDI/ATC/OSDI）、PMLR（AISTATS/UAI）、
NeurIPS、JMLR、IJCAI。因此「Crossref 查无」**不能**作为该文献不存在的证据，
也不能作为身份可疑的信号。本目录对这些来源一律要求**出版方页面**作为一手依据。

---

## 2. P1 种子与检索矩阵

### 2.1 种子来源（均为仓库既有材料，仅作线索）

| 来源 | 用途 |
|---|---|
| [Related_Work与Baseline选型.md](../Related_Work与Baseline选型.md) | 四类分类、baseline 候选、简称↔全称对应 |
| [Challenge设计](../Challenge设计：从普通根因定位转向故障图恢复.md) | C1/C2/C3 的对手工作（BiAn、NetEventCause） |
| [T007 sources.md](../graph_metrics_literature/sources.md) | 指标类与方法基础线索 + 已核验定位 |
| [web_relevance/paper_manifest.md](../web_relevance/paper_manifest.md) | WWW 近三年网络/相邻集条目 |
| `docs/papers/` 历史文件名（48 项，工作区已删除） | 题名线索（**未恢复内容**，仅读文件名） |
| [T007 验收 R1–R7](../../../../.ai/T007_acceptance.md) | 必须带入本轮的更正项 |

### 2.2 稳定编号

候选 ID 形如 `C0001`，在**合并去重前**分配，仅用于流水线内部追踪。
正式 `paper_id`（`RW0001`… / 待核实 `RX0001`…）在**建表时按
（层次 → 主题 → 年份 → 题名）确定性排序分配**，此后不随排序变化。
`catalog.csv` 保留 `候选ID` 列以便回溯。

### 2.3 覆盖矩阵（主题 × 场景 × 来源 × 年份）

| 层次 | 主题 | 场景 | 主要来源通道 |
|---|---|---|---|
| L1 | 测量与路径约束定位 | DCN / 生产网络 | Crossref 题名与 container-title、USENIX 页面、arXiv |
| L1 | 告警关联与故障范围 | 云 / 网络运维 | Crossref、DOAJ、中文期刊页、WebSearch |
| L1 | 事件依赖与传播建模 | 网络 / 云 | OpenAlex、Crossref、arXiv HTML 引文 |
| L1 | LLM/知识辅助网络诊断 | 网络 / 云 | OpenAlex、arXiv abs、WebSearch |
| L1 | RDMA/PFC 与可编程网络 | DCN / HPC | Crossref、USENIX 页面、arXiv |
| L2 | 微服务/云 RCA | 微服务 | OpenAlex 引文扩展、Crossref、PMLR/NeurIPS 官方页 |
| L2 | 依赖推断与参考图构造 | 分布式系统 | WebSearch、Crossref、arXiv |
| L3 | 方法基础 | 跨领域 | Crossref、PMLR、NeurIPS、JMLR、IJCAI 官方页 |

---

## 3. P2 多源发现（实际执行）

分 8 个主题并行执行，每个主题独立检索并落盘一个 TSV。
**共产生 349 行候选**（含跨主题重复），合并去重后 **319 条**独立候选。

### 3.1 各主题实际使用的通道

| 主题 | 实际使用的通道 | 备注 |
|---|---|---|
| 网络故障定位 | Crossref `query.title`、Crossref `query.container-title`（SIGCOMM 2015–25、IMC、CoNEXT、SIGMETRICS、HotNets、INFOCOM）、USENIX 会议页、OpenAlex（前期） | Crossref 的 `container-title` 使用序数（"16th"）而非年份，按年份正则匹配会漏 |
| 告警关联 | Crossref `query.bibliographic`、**引文回溯**（取 COLA、iPACK、FSE'25 告警摘要三篇的参考文献表逐条解析）、DOAJ、中文期刊页、WebSearch（中英） | DOAJ 用于核验中文期刊记录 |
| 传播图恢复 | Crossref、**arXiv HTML 的 `ltx_bibitem` 引文**、WebSearch | arXiv HTML 引文通道产出最高（EvoCause 34 条、PropLLM 52 条参考文献） |
| LLM 网络诊断 | OpenAlex（约 25 组查询）、OpenAlex 前向引文、Crossref、arXiv abs（逐个核验 16 个 arXiv ID）、WebSearch | 2022 年起为主 |
| RDMA/可编程 | OpenAlex、Crossref + 直接 `/works/{doi}`、WebSearch、USENIX 页、arXiv abs | — |
| 微服务 RCA | OpenAlex 12 组查询 + 前向引文（MicroRCA 234、Microscope 186、MicroCause/MicroHECL 161）、Crossref | 约 80% 条目来自 OpenAlex |
| 依赖推断/参考图 | WebSearch（最高产）、Crossref、arXiv abs、USENIX 页 | 引文扩展为人工沿摘要中提到的文献推进 |
| 方法基础 | WebSearch（约 28 组，每个具名方法一组）、Crossref、PMLR/NeurIPS/JMLR/IJCAI 官方页 | 官方页核验因 Crossref 不索引这些来源 |

### 3.2 中文检索

用 WebSearch 以中文执行：告警关联、告警压缩、告警风暴、故障定位、根因分析、故障传播图。
实际纳入 4 条中文文献（电信科学 2024、沈阳工业大学学报 2026、邮电设计技术 2023、
光通信技术 2021），其中 1 条置信度较低并已在文件内标注。
**中文期刊的自动化核验通道不足**，是本次的明确缺口。

### 3.3 检索式示例（概念分组，实际按组合拆开运行）

- 场景：`network` / `datacenter` / `data center` / `cloud` / `microservice` / `distributed system` / `RDMA`
- 任务：`fault localization` / `failure diagnosis` / `root cause analysis` / `alarm correlation` / `alert aggregation`
- 输出：`fault propagation` / `failure propagation` / `causal graph` / `event dependency` / `provenance` / `propagation path` / `graph reconstruction`

**未使用单一长 AND 查询**，以避免召回被人为压缩。

---

## 4. P3 引文扩展（实际执行）

| 轮次 | 起始对象 | 实际做法 | 结果 |
|---|---|---|---|
| R1 | COLA（ICSE-SEIP'24）、iPACK（ICSE'23）、ProAlert（FSE'25） | 取参考文献表逐条解析再回查 | 新增告警关联类候选多条 |
| R2 | EvoCause、PropLLM | 抓取 arXiv HTML 的 `ltx_bibitem` | 合计 86 条参考文献，新增 Chain-of-Event、Cluster-Aware Causal Discovery、CausIL、Neural Granger、MULAN、CORAL 等 |
| R3 | MicroRCA、Microscope、MicroCause/MicroHECL | OpenAlex 前向引文（`cites:`） | 新增 CIRCA、Interdependent Causal Networks、RCD 等 |
| R4 | PCMCI → CMIknn；NOTEARS → GES/MMHC/PC；Hawkes 1971 → RMTPP → Neural/Transformer Hawkes → CAUSE/ISAHP；FCI → RFCI/tsFCI | 方法基础的后向扩展 | 方法基础层成形 |
| R5 | Dapper ← X-Trace/Magpie/Pinpoint；Alibaba ICPE ← Complexity at Scale；RCAEval ← Rethinking-RCA | 人工沿摘要提到的文献推进 | 追踪/参考图构造类补充 |

**停止依据**：完成上述 5 轮后，L1 核心近邻不再出现新的直接挑战者；
最后一轮（R5）新增条目均为背景或方法基础，无新增 L1 核心。详见
[coverage_report.md](coverage_report.md) §5。

---

## 5. P4 核验（实际执行）

### 5.1 解析流水线（按强度排序，逐级回落）

| 路径 | 做法 | 通过数 |
|---|---|---|
| `doi` | 线索带 DOI → Crossref `/works/{doi}` 直取 | — |
| `doi`（存缴短题名） | Crossref 存缴题名较短时按**前缀匹配**接受，并记录差异 | 见 §5.2 |
| `title` | Crossref `query.bibliographic` 题名检索，相似度 ≥0.90 | — |
| `query.title` | Crossref `query.title`（字段限定，精度更高） | — |
| `page` / `arxiv` | 出版方页面 / arXiv abs 页的 `citation_*` 元数据 | — |
| 人工裁定 | 逐条读取一手记录后裁定，写明依据 | 8 |

**阈值**：≥0.90 记「已核实」；0.68–0.90 记「ambiguous」；<0.68 记「unresolved」。
后两类一律**不进入 Papers**，转入 `screening.csv`。

### 5.2 核验结果

| 项 | 数值 |
|---|---|
| 候选总数（去重后） | **319** |
| 身份已核实（Papers） | **306** |
| 身份待核实（Pending） | **13** |
| 含 DOI | 241 |
| 取得摘要 | 47 |
| 题名与线索不一致、已记录说明 | **19** |

### 5.3 发现并修正的线索错误（**本轮更正**）

以下为旧材料（仓库文档或前序自动检索）与一手记录冲突之处，均以一手记录为准：

| 对象 | 旧记录 | 一手记录 |
|---|---|---|
| **COLA** | 以「COLA」为名另列，另有「Knowledge-Aware Alert Aggregation」一条 | **两者是同一篇**：正式题名 *Knowledge-aware Alert Aggregation in Large-scale Cloud Systems: a Hybrid Approach*，ICSE-SEIP 2024。已合并为 RW0137 |
| **REASON** | *REASON: Reasoning about Root Causes of Performance Degradation in Cloud Systems* | KDD 2023 正式题名为 ***Interdependent Causal Networks for Root Cause Localization***（RW0237）。REASON 是系统名 |
| **CORAL** | *CORAL: Causal Graph based Root Cause Analysis for Online Service Systems* | KDD 2023 正式题名为 ***Incremental Causal Graph Learning for Online Root Cause Analysis***（RW0089）。CORAL 是系统名 |
| **NetCause** | 以简称「NetCause」记录，未给正式题名 | 正式题名 *NetCause: **Counterfactual Learning** for Root Cause Analysis in Large-Scale Networks*（RW0105） |
| **R-Pingmesh** | SIGCOMM **2023** | SIGCOMM **2024**，DOI 10.1145/3651890.3672264 |
| **ByteTracker** | *ByteTracker: Agentless Real-Time Path-Aware Network Probing* | 正式题名 *ByteTracker: **An Agentless and Real-time Path-aware Network Probing System***，SIGCOMM 2025 |
| **NetLLM** | *NetLLM: Empowering LLMs to Adapt to Dynamic Networking* | 正式题名 *NetLLM: **Adapting Large Language Models for Networking***，SIGCOMM 2024 |
| **Everflow** | *Everflow: A Large-Scale Production System for Network Troubleshooting* | SIGCOMM 2015 正式题名为 ***Packet-Level Telemetry in Large Datacenter Networks*** |
| **Pingmesh** | — | Crossref 存缴题名为短题名 *Pingmesh*；本表采用完整题名并记录差异 |
| **DeathStarBench** | 记作 SOSP | 实为 **ASPLOS 2019** |
| **GraN-DAG / CUTS** | 记作 AISTATS 2020 / AISTATS 2023 | 实为 **ICLR 2020 / ICLR 2023** |
| **B8（JMLR 2013）** | *A Comparison of the Ladder and Max-Min Hill-Climbing…*，作者 S. Mahdi, C. Meek | T007 R7 已更正为 *Sub-Local Constraint-Based Learning of Bayesian Networks Using A Joint Dependence Criterion*，JMLR 14(49)，作者 Rami Mahdi, Jason Mezey。本轮沿用该更正（RW0262） |
| **RCD 的 DOI** | — | Crossref 记录为 `10.52202/068431-2259`（NeurIPS 35 的 Proceedings.com 著录），**非 ACM/IEEE 常规 DOI**，引用时需注意 |

### 5.4 重名消歧（本轮实际处理）

- **RCA Copilot**：至少两条不同谱系。本目录收录网络侧的 *RCA Copilot: Transforming Network Data into Actionable Insights via LLMs*（ICC 2025），并在条目内标明与云端 RCACopilot 的区别。
- **GALA**：两篇不同论文（arXiv:2508.12472 与 arXiv:2608.08968），均已核验并列。
- **CausalRCA**：仅有 JSS 2023 一篇进入目录；其余同名工作未收录。
- **COLA**：优化领域的 *COLA: Decentralized Linear Learning* 与本条无关，已在卡中标注。
- **PRAXIS**：arXiv:2512.22113 的实际题名与检索摘要给出者不同，采用一手页面的题名。

### 5.5 摘要获取

| 通道 | 取得数 | 备注 |
|---|---|---|
| arXiv abs 页 | — | — |
| Crossref `abstract` 字段 | — | 仅部分 ACM/PACMSE 记录含摘要 |
| 已缓存出版方页面（严格题名匹配） | — | 页面自述题名需与条目题名 ≥0.92 才采用 |
| **合计** | **47 / 306** | 其余标注「仅元数据（本轮未取得摘要，未阅读正文）」 |

> **一次已修正的方法错误**：摘要抽取的初版以「条目题名出现在页面文本中」为判据，
> 导致多个条目共用同一页面的摘要。该判据不安全（列表页与参考文献会提及其他题名）。
> 已改为**以页面自述题名匹配 ≥0.92 且一页只服务一条**，并清除此前全部误配结果。
> 复核：47 条摘要中**无重复文本**。

---

## 6. 未执行的检索（不得记为「已查无结果」）

| 项 | 原因 |
|---|---|
| 中文期刊的系统性逐年检索 | 缺少可自动化的中文索引通道（CNKI 等不可达） |
| IEEE Xplore / ACM DL 全文批量检索 | 403 / 站点反爬；仅用元数据 |
| OpenAlex 按 source 的逐年出版量统计 | 当日配额耗尽（`Resets at midnight UTC`），未完成 |
| Hawkeye / APGNN / CausIL 等正文逐节阅读 | 本地全文缓存已从工作区删除，本轮未恢复；未重新下载 |
| 2026 年部分会议 proceedings 补查 | 部分尚未公开，记为「未公开」而非「无结果」 |
| 逐页视觉 QA（PDF 版面核对） | 本机无 `pdftoppm`；按既有约束此类操作在服务器执行 |

**具体未覆盖项与替代尝试**见 [coverage_report.md](coverage_report.md)。
