# WWW 2027 Research Track CFP：范围与 relevance 要求（官方原文核验）

> 检索日期：**2026-09-11**。来源：`https://www2027.thewebconf.org/research-track-papers/`
> （HTTP 200，112 226 字节，已留本地快照）。
> **本文件区分三类信息：官方要求 / 作者写法 / 我们的投稿解释。不得混用。**

## 1. 官方硬性要求（原文引用）

**Scope**（官方原文）：

> The scope of the conference is the Web and how it has crucially enabled new research and
> applications. […] A typical Web Conference paper should have an explicit focus on at least
> one of the following:
> - understanding, evaluating, and improving **the Web as a technical infrastructure;
>   including core Web technologies, standards, and platforms**
> - understanding, evaluating, and improving the Web as a socio-economic system;
> - understanding better the impact of the Web and Web technologies;
> - democratising access to Web content and technologies, […]
> `【官方要求】`

**Relevance**（官方原文，最关键的一段）：

> Every submission must clearly state how the work is relevant to the Web **and to the track
> in the first page**. Submissions that merely use a Web artifact e.g. a dataset or a Web
> Application Programmer Interface (API) or a social network – rather than answering a
> specific Web-related scientific research challenge, **are out of scope and will be
> desk-rejected**. `【官方要求】`

**Tracks**（官方原文节选，共 12 个）：

> Brave New Ideas for the Future of the Web / Web Economics and Digital Society /
> Graph Algorithms and Modeling for the Web / Responsible Web / Search, Recommendation, and
> Retrieval-Augmented AI / Security and Privacy / Semantics and Knowledge / Social Networks
> and Social Media / **Web Infrastructure and Agentic Systems** / User Modeling,
> Personalization and Agentic Web Users / Web Mining, Multimedia and Multilingual Content
> Analysis / Evaluation, Human Computation, and Resources `【官方要求】`

**其他已核验项**：

| 项 | 值 |
|---|---|
| 会议时间地点 | Dublin, Ireland, 2027-05-10 至 05-14 |
| 长文摘要截止 | 2026-10-18 |
| 长文全文截止 | **2026-10-25** |
| 结果通知 | 2027-01-04 |
| 评审系统 | OpenReview（所有作者须有 profile） |
| 短文截止 | 2026-11-16 |

## 2. 官方要求的三条推论

1. **relevance 必须写在第一页**，且必须同时对应"Web"与"所选 track"。这不是建议，是 desk-reject 条款。
2. **"只用了 Web 数据/API/社交网络"不构成 relevance**。判据是"是否回答了具体的 Web 相关科学问题"。
3. 官方范围明确包含 **"Web as a technical infrastructure"**，且 `Web Infrastructure and
   Agentic Systems` 是正式轨道之一。`【官方要求】`

## 3. 官方文本**没有**说的（防止过度解读）

- 官方**没有**要求算法必须处理 HTTP、页面或用户请求。`【官方要求】`（反证：2026 年
  `Web Mining and Content Analysis` 轨道录用了以 MAWI/CAIDA 骨干网流量为数据的
  *JitterSketch*，见 [分析卡](papers/www26-jittersketch/analysis.md)。）
- 官方**没有**承诺任何具体算法或行业场景必然录用。`【本次推断】`（官方文本中不存在此类表述）
- 官方**没有**定义"技术基础设施"的粒度边界。`【本次推断】`

## 4. 作者写法（不是官方要求）

以下是从 14 篇已深读论文中**实际观察到**的 relevance 写法，属于**作者实践**，不是规则：

| 写法 | 代表论文 | 出现位置 |
|---|---|---|
| 首段用带引文的宏观 Web 规模数字，再落到具体机制 | `www26-starlink-cd` | P1, PDF p.1 |
| 标题级工作量限定词（"for Mobile Web Services"） | `www24-wise-start` | 题名 |
| 把评价指标本身绑定到 Web 语义 | `www24-wise-start`（First AFT）、`www24-quic-fast`（HTTP/3） | §1 / §4 |
| 领域命名（"microservice systems"），无具名 Web 依赖 | `www24-gamma` | P1–P2 |
| **正文中几乎不出现 "web" 论证** | `www24-mulan`、`www26-metakube` | — |

> `www24-mulan` 与 `www26-metakube` 正文中 "web" 一词仅出现在参考文献、版权行或
> K8s 术语 "admission webhooks" 中；`www24-inart` 的 CCS Concepts 不含任何 Web 类别。
> 详见各分析卡。**这些论文被录用这一事实，不能推出"relevance 论证可以省略"。**
> `【本次推断】`

**为什么不能反推录用原因**：录用是评审委员会基于完整稿件、与当年 pool 比较后的决定。
我们只看到了录用结果与最终文本，看不到审稿意见、rebuttal 与落选稿件。
"某篇弱 relevance 的论文被录用"只说明**它没有被 desk-reject**，不说明弱 relevance 是安全的。
`【本次推断】`

## 5. 对本项目的含义

| 结论 | 性质 |
|---|---|
| 目标轨道 `Web Infrastructure and Agentic Systems` 与官方范围中的 "Web as a technical infrastructure" 直接对应 | `【官方要求】` |
| 轨道名含 "Agentic Systems" **不强制**添加 LLM/agent | `【本次推断】`（官方文本无此要求） |
| 第一页必须出现 relevance 陈述，且须是"Web 科学问题"而非"用了网络数据" | `【官方要求】` |
| 仅凭 Pingmesh 丢包 + 拓扑 + 告警，**目前无法证明**回答了某个具体的 Web 科学问题 | `【本次推断】`，证据缺口见 [synthesis.md](synthesis.md) §5 与 [positioning_options.md](positioning_options.md) |
| 存在"基础设施背景即可"的录用样本（如 JitterSketch），但其 relevance 强度不可作为安全垫 | `【本次推断】` |

## 6. 保存的官方来源

| 文件 | URL | 抓取日期 | 说明 |
|---|---|---|---|
| 本地快照（未入库，位于忽略目录） | `https://www2027.thewebconf.org/research-track-papers/` | 2026-09-11 | HTTP 200，112 226 字节 |
| 官方 Industry 目录参考 | `https://www2026.thewebconf.org/accepted/industry.html` | 2026-09-11 | 用于核验 Smart Eye（ind0103）轨道 |
| 官方 Research 目录 | `https://www2026.thewebconf.org/accepted/research-tracks.html` | 2026-09-11 | 676 条，按 track 分组 |
| 官方 2024 目录 | `https://www2024.thewebconf.org/accepted/research-tracks/` | 2026-09-11 | 405 条 |
| IW3C2 2025 官方存档 | `https://archives.iw3c2.org/www2025/www2025-proceedings.pdf` | 2026-09-11 | 6 574 225 字节，112 页 front matter + TOC |

> 既有 `sources/来源清单.md` 中的 2027 页面快照抓取于 2026-08-27，当时 Calls 页仍为
> Coming Soon。本文件是**新抓取的现行版本**，与旧快照并存，不覆盖历史。
