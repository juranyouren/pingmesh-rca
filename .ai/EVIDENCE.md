# Evidence Pack — T008 相关工作目录

更新：2026-09-15。范围：T008 文献检索与核验。
主产物 [related_work_catalog/](../docs/conferences/WWW2027/related_work_catalog/)。
T007 的证据快照已原样保留在 [T007_evidence.md](T007_evidence.md)（未删改）。
本包只给结论与可复核定位，不复制论文原文。

> **读取提示**：下列 C1xx 序号是**本任务新增**的证据条目，与 T007 的 C001–C007 **不连续**，
> 避免与其编号混淆。T007 条目凡被本任务引用，均显式写「T007 C00x」。

---

## C101 — 身份核验不是手抄，全部来自提供方记录

- **claim**：本目录 306 条已核实条目的题名、作者、venue、年份、DOI 均取自提供方记录，
  不存在人工键入的著录。
- **source**：`tmp/t008/resolve.py` / `resolve2.py` / `resolve3.py` / `verify_url.py` 的
  解析逻辑；`evidence.md` 的「核验路径」列逐条给出该条走的通道
  （`doi` / `doi-adjudicated` / `title` / `query.title` / `page` / `page-curl` / `arxiv`）。
- **finding**：306 条中 241 条带 DOI；其余来自出版方页面或 arXiv abs 页的
  `citation_*` 元数据。所有提供方响应缓存在 `tmp/t008/cache*`。
- **interpretation**：身份可信度高于「按题名回忆」或「二手综述转抄」。
- **confidence**：HIGH（流程可复现，缓存可查）
- **verification need**：NONE（如需复核，重跑 `resolve*.py` 即可复现同一结果）

## C102 — 短题名存缴与系统名混淆是被显式处理的，不是静默覆盖

- **claim**：Crossref 对部分 ACM 记录的存缴题名是**缩写**（如 SIGCOMM 2015 Pingmesh 存缴为
  `Pingmesh`），另有旧材料把**系统名**当作正式题名。两类情况均已分别处理并记录。
- **source**：
  - 短题名：`tmp/t008/resolve3.py` 的 prefix 规则 + `build.py` 的 `pick_title()`；
    结果写入 `catalog.csv` 的 `题名说明` 列（**19 条**）。
  - 系统名：`tmp/t008/adjudicate.py` 的 `ADJUDICATE` 表，逐条附依据。
- **finding**：
  - Crossref `/works/10.1145/2785956.2787496` 返回题名 `Pingmesh`（完整题名见 SIGCOMM 2015）。
  - `10.1145/3580305.3599849` → *Interdependent Causal Networks for Root Cause Localization*
    （旧材料记作 *REASON: Reasoning about Root Causes…*）
  - `10.1145/3580305.3599392` → *Incremental Causal Graph Learning for Online Root Cause Analysis*
    （旧材料记作 *CORAL: Causal Graph based Root Cause Analysis…*）
- **interpretation**：旧材料的 REASON / CORAL 题名**不是**这两篇论文的正式题名，
  不能直接进入参考文献表。已在 `evidence.md` §1 建更正记录并指向原位置。
- **confidence**：HIGH（DOI 直取，可复核）
- **verification need**：NONE

## C103 — 「网络侧没有传播关系评价」必须撤回

- **claim**：不能在论文中声称网络运维领域不存在传播/因果关系的评价先例。
- **source**：
  - NetEventCause：DOI `10.1109/TNNLS.2025.3574316`；T007 sources.md §2 的
    C1 定位（Experiment 2 的 ACC@k）；**T007 验收 R1** 已认定其评价对象为
    事件级局部原因关系集合。
  - APGNN：DOI `10.1016/j.comnet.2022.109485`，题名本身即
    *Alarm **Propagation** Graph Neural Network for fault detection and alarm root cause analysis*。
- **finding**：至少两篇网络/运维工作以「告警传播图 / 局部原因关系」为对象。
- **interpretation**：可保留的**较弱**表述是「未查到与本项目**同粒度（设备级）、
  同输出对象（显式设备 DAG）** 的完整图指标先例」。**该缺口不等于 novelty。**
- **confidence**：HIGH（题名与 DOI 一手可查）
- **verification need**：APGNN **是否报告图结构指标** 仍为 **UNKNOWN**
  （全文不可得，见 C107）。**不得**给确定的「无」。

## C104 — 两篇 2026 预印本构成最强直接近邻

- **claim**：与本项目问题设定最接近的工作是 2026 年的两篇 arXiv 预印本，
  而非数据库中的既有论文。
- **source**：
  - PropLLM：`arxiv.org/abs/2606.00582`（本轮实际抓取 abs 页元数据与摘要）
  - EvoCause：`arxiv.org/abs/2607.27290`（同上）
- **finding**：
  - PropLLM 从末端告警**逐跳回溯传播路径**，用 Temporal Causal Propagation Attention
    把拓扑因果先验编入注意力；输出是**一条因果链**。
  - EvoCause 用 LLM 提议图编辑、确定性代码校验无环性，在带标签对齐集上选图；
    用 **Node F1 / Case EM / Graph F1 / nSHD** 评价；发布 **TeleRCA**
    （485,681 告警事件、194 种告警类型、5,621 资源、专家标注）。
- **interpretation**：
  1. EvoCause 表明**「对告警因果图打分」在该社区已有被接受的指标口径**，
     本文的图指标设计必须正面处理这些口径，不能只引用因果发现工具。
  2. PropLLM 的输出是链而非图，且未（摘要层面）处理起点不确定性 —— 这是我方
     可主张的差异点，但**必须全文核实后才能写进论文**。
- **confidence**：MEDIUM-HIGH（题名、作者、摘要为一手；**正文未读**）
- **verification need**：**必须有**。取得两篇全文，核实：
  PropLLM 是否支持多根/起点不确定；EvoCause 的 nSHD 归一化分母与是否约束物理邻接。

## C105 — CCF 等级来自第七版官方目录，且非正式轨道不继承主会等级

- **claim**：本目录的 A/B/C 等级取自 CCF 第七版官方目录 PDF（官网发布 2026-03-31），
  Companion/Workshop/Poster 条目**不继承**主会等级。
- **source**：
  - 官方 PDF 解析：`tmp/t007/parse_ccf.py` → `tmp/t007/ccf7_entries.tsv`（597 条），
    本轮经 `tmp/t008/ccf_lookup.py` **按 dblp URL 条目锚定**重新索引为 593 个 slug。
  - 轨道判定：`tmp/t008/ccf_map.py` 的 `TRACK_WORKSHOP`。
- **finding**：
  - 按 dblp slug 取等级比按简称可靠：解析表的**简称字段存在错位**（如
    `journals/ml` 的简称显示为 `JSLHR`、`conf/sigmetrics` 显示为 `SIG-`），
    但 **URL 与 A/B/C 分节是稳的**。本目录只用后者。
  - 有 **11** 条因 Companion/Workshop/Poster 轨道被判「不适用」，主会等级记入 `CCF备注`。
- **interpretation**：等级不会被预印本或 Companion 条目污染。
- **confidence**：HIGH（可复现解析）
- **verification need**：`ACM Computing Surveys` 与 `IEEE Access` 之外的个别未匹配条目
  仍待人工确认（缺口 G3）。

## C106 — 探测表不是出版量普查（方法局限）

- **claim**：`Coverage` 工作表中的 `n_records` **不能**读作「该会刊该年发表了多少篇」。
- **source**：`tmp/t008/coverage.py` 使用 Crossref `query.container-title`。
- **finding**：该参数是**相关性排序**而非精确过滤。实测 SoCC 2017 返回
  `total-results` 58,582，本地按 container 名称过滤后仍留 1000 条（行数上限）。
  且 **NSDI 全 12 年零命中**，实因 **Crossref 不索引 USENIX 论文集**。
- **interpretation**：该表只能作为**粗粒度检索记录**。真正的逐年出版量需用
  OpenAlex source 作用域统计（`coverage2.py`，本轮因配额耗尽未完成）。
  覆盖报告中已把 NSDI 一行标注为「**来源未收录**」而非「查无结果」。
- **confidence**：HIGH（现象可复现）
- **verification need**：配额重置后重跑 `coverage2.py`（缺口 G4）。

## C107 — APGNN 全文不可得，其能力判断为 UNKNOWN

- **claim**：无法判断 APGNN 是否报告图结构指标。
- **source**：T007 sources.md §5.2 的缺文记录：OpenAlex 明确 `is_oa: false`、
  `any_repository_has_fulltext: false`；ScienceDirect / ACM DL / 机构门户 / Unpaywall /
  OpenAlex / OpenAIRE / CORE / aminer 均无 OA 全文。本轮**未重试**。
- **finding**：只读到摘要；摘要中唯一量化表述是「4.6% in F1-score」（语境为 APG→故障的
  整图二分类）。
- **interpretation**：该判断**置信度 low**，不得用于声称该文采用或未采用图结构指标。
- **confidence**：LOW（内容）；HIGH（不可得这一事实）
- **verification need**：**必须有**。机构订阅取得 Computer Networks 220:109485。

## C108 — 一条独立的经验依据支持「依赖图不是固定真值」

- **claim**：生产环境的调用图数据缺失是**系统性**的，而非随机缺失。
- **source**：
  - *Complexity at Scale: A Quantitative Analysis of an Alibaba Microservice Deployment*
    （arXiv:2504.13141，本轮取得摘要）：调用图**高度时变**、依赖呈**长尾**分布，
    作者明确指出这些观察**挑战故障管理等研究中的常见假设**。
  - *Systemizing and Mitigating Topological Inconsistencies in Alibaba's Microservice
    Call-graph Datasets*（ICPE 2024，DOI `10.1145/3629526.3645043`，由检索代理发现）。
- **interpretation**：可用来支撑「未观测 ≠ 不存在」，从而支持 unknown 掩码设计。
  **但**：这是**微服务追踪数据**上的结论，外推到 DCN 设备告警是**类比**，
  不能替代本项目自己的参考图来源说明（该项目参考图来源仍为 UNKNOWN）。
- **confidence**：MEDIUM（摘要级证据；跨场景外推为研究者判断）
- **verification need**：引用时须标注为类比性支撑。

## C109 — A4（Retrofitting）不构成掩码先例（沿用 T007 R3 更正）

- **claim**：不能引用 *Retrofitting Service Dependency Discovery in Distributed Systems*
  作为「未观测依赖不计错 / 显式掩码」的先例。
- **source**：arXiv:2510.15490 §VI-A（T007 R3 定位）；本轮取得该文摘要复核。
- **finding**：原文说明参考拓扑含**架构定义的潜在依赖**，运行期无流量导致部分依赖
  发现不了，因此 **recall/F1 下降**。**未核实到**作者把这些边从分母排除。
- **interpretation**：T007 首轮「不算错／显式排除」写反了。必须区分
  「已知存在但观测窗未出现的边」与「真值尚未判定的关系」——两者不能用同一掩码。
  我方的 unknown/allowed 设计应标明为**本项目建议**。
- **confidence**：HIGH
- **verification need**：NONE（更正已落实在本目录 RW0218 阅读卡）

---

## 未被本包支持的命题（禁止引用）

以下命题在本轮**没有**得到证据支持，不得写进论文或后续摘要：

1. 「网络侧不存在任何传播关系或图结构评价」——见 C103。
2. 「APGNN 没有报告图结构指标」——见 C107，应为 UNKNOWN。
3. 「本目录已穷尽相关文献」——见 C106 与覆盖报告 §5，结论是「已完成可访问范围，仍有缺口」。
4. 「Retrofitting 提供了掩码先例」——见 C109。
5. 「已与 CausIL 共享『真值来自系统结构定义』这一事实」——CausIL 真实数据用的是
   **假设构造的代理参考图**；本项目参考图来源仍为 **UNKNOWN**。
