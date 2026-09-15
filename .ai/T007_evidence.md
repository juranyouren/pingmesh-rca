# Evidence Pack

> **Work 验收更正（2026-09-13），优先于下文执行者原证据声明：**
> T007 部分通过，待 [R1–R7](T007_acceptance.md) 返修。下列 HIGH / Verification Need: NONE
> 不能覆盖已查实的问题：C001 混入 ArrowConfusion 且夸大反向=0/1/2；C002 错分 NEC；
> C003 遗漏 CausIL 真实数据代理图；C006 的 A4 掩码依据不成立；C007 更正后的 SHD 类位置仍错。
> NEC 是局部原因关系恢复先例；A4 未观测依赖降低召回；raw SHD 对零边图有定义。
> C004 第七版发布事实有官方依据，但目录表内部矛盾仍须修正，验收未逐条复验全部级别。
> 本页下文作为交付时证据快照保留，修订后的正式摘要以 T007-R 逐项响应为准。

更新：2026-09-13。范围：T007 图评价指标文献调研。
主产物 [report.md](../docs/conferences/WWW2027/graph_metrics_literature/report.md)、
来源与定位 [sources.md](../docs/conferences/WWW2027/graph_metrics_literature/sources.md)。
上一轮 T006 证据快照保留在 [T006_evidence.md](T006_evidence.md)（未删改）。
本包不复制论文原文，只给结论与可复核定位。

## C001 — "SHD" 在不同实现间不是同一个指标

- **Priority:** P1
- **Claim:** 同名的结构汉明距离，对**一条反向边**的计分在 **0/1/2** 之间不一致；不写明约定则数字不可比。
- **Source / Locator:** Tsamardinos 等 2006 **作者版 PDF p.22–23**（§9.1.4 + Algorithm 4：`if E is incorrectly oriented … shd += 1`，注释含"一图无向、另一图有向"也计 1）；
  gCastle `gcastle/castle/metrics/evaluation.py::MetricsDAG`（`shd = extra + missing + reverse`）；
  causal-learn `causallearn/graph/ArrowConfusion.py`（有序对，1 FP + 1 FN）；
  dodiscover `dodiscover/metrics.py::structure_hamming_dist`（`double_for_anticausal=True` 默认）；
  CDT `cdt/metrics.py::SHD`（默认 True）**与其 `SHD_CPDAG`（传 False）自相矛盾**；
  bnlearn CRAN 手册 `compare()` Note（**`shd()` 先对双方调用 `cpdag()`**）；
  Mahdi & Meek JMLR 14 (2013)（"counted only once in the SHD metric … twice in the TPR plot"）。
- **Finding:** 反向边计分：原始定义 **1**、gCastle **1**、causal-learn 箭头层 **2**、dodiscover 默认 **2**、CDT 默认 **2**；gCastle 另把"无向 vs 有向"记为 **0**（偏离原始定义的 1）；bnlearn 的 SHD **定义在 CPDAG 上**。
- **Interpretation:** 本项目若报 SHD，必须写作 `SHD-1` 并附（反向计 1 / 图类型为 DAG / 零边案例单列）三条约定；**不得**据此宣称"在 SHD 上优于某方法"。
- **Confidence:** HIGH（逐来源读到原文定义或源码）
- **Verification Need:** NONE（本包已定点核到；引用时只需确认未换版本）
- **Ambiguity:** `SHD_CPDAG` 与 `SHD` 的差异出自源码阅读而非官方文档说明；未找到单篇"点名批评 SHD 有歧义"的论文。

## C002 — 网络/系统侧代表论文构建传播图却不评价图

- **Priority:** P1
- **Claim:** 网络与系统领域的代表性工作普遍构建传播/溯源/因果图，但**实验只评价根因定位或下游任务**，没有任何图结构指标。
- **Source / Locator:** 逐篇定位见 report.md §1.3 与 sources.md §2 的 C1–C8 表 ——
  NetEventCause（本地全文 Experiment 2：AUC + ACC@k）、SkyNet（§6.3 locator FP/FN、§6.4 severity、
  736s→147s）、Hawkeye（Abstract：>90% precision/100% recall 的**诊断**）、FaultInsight（§3.1.4 PR@k% + RankScore）、
  RCD（§5：execution time + recall at top-k）、MULAN（§4.3：PR@K/MAP@K/MRR）、Eadro（§V.D：检测 F1 + HR@k + NDCG@k）、APGNN（**仅摘要**：分类 F1）。
- **Finding:** 8 篇中 7 篇读到全文（1 篇仅摘要），**全部无** SHD / 边级 P/R/F1 / 邻接矩阵匹配；多数在文中明确把图当作"中间手段"（RCD 原文即称学完整因果图"不是必需的"）。
- **Interpretation:** 本项目**不能**从同领域论文借到图结构指标的先例；同时这可作为"图本身未被评价"的研究缺口来主张，措辞需保留余地。
- **Confidence:** HIGH（C8 为 LOW，已单列）
- **Verification Need:** NONE（本包已逐篇定位）
- **Ambiguity:** **专项检索曾返回空结果**；检索以英文为主，不能外推为"不存在"。中文告警关联/压缩类未系统检索。

## C003 — 直接评价图结构的论文集中在微服务与通用因果发现一侧

- **Priority:** P1
- **Claim:** 本轮只核实到 **4 篇**真正把传播/依赖图结构作为评价对象的工作，全部来自微服务或通用图恢复。
- **Source / Locator:** A1 CausIL（WWW '23 §5.3：Adj / AH / SHD）、
  A2 ErrorPrism（ASE '25 §IV-A3 + Eq.(2)(3)：路径 exact-match）、
  A3 IEEE Access 2026 §V-B-2 式(16)(17)（`normalized SHD=(E+M+R)/T`、方向敏感 F1）、
  A4 arXiv:2510.15490 §VI-A Table I（边级 P/R/F1）。
- **Finding:** 4 篇中 3 篇评**边或路径结构**；A3 是唯一同时给出**含反向边项的归一化 SHD**与方向敏感 F1 的故障传播工作。
- **Interpretation:** 指标依据须主要从通用因果发现/图恢复借；A3 的 `(E+M+R)/T` 形式最贴合本项目，但**要求完整参考图**，部分标签下不适用。
- **Confidence:** HIGH（A4 为预印本，其"方向是否参与匹配"为 UNKNOWN）
- **Verification Need:** NONE
- **Ambiguity:** A3 与 A4 的**真值独立性差别很大**（A3 由 75 分位阈值启发式构造、作者自承有偏；A4 取自应用架构定义），引用时不可混谈。

## C004 — CCF 目录已更新至第七版，级别有变动

- **Priority:** P2
- **Claim:** 现行 CCF 推荐目录为**第七版（2026-03-31 发布，2026-04-09 勘误）**，**ICLR 升 A、IJCAI 降 B**。
- **Source / Locator:** 官方公告 https://www.ccf.org.cn/Academic_Evaluation/By_category/2026-03-31/870181.shtml ；
  官方 72 页 PDF 经分类页取得并解析，脚本 `tmp/t007/parse_ccf.py`、产物 `tmp/t007/ccf7_entries.tsv`（**597 条目**）。
- **Finding:** 本轮所用级别全部据第七版核定，含 TNNLS=**B**、Computer Networks=**B**、TNSM=**C**、IEEE Access=**未收录**、PVLDB/CNSM/NOMS=**未收录**。
- **Interpretation:** 旧方案与既有材料若按 2022 版写级别，ICLR/IJCAI 两项需更正。
- **Confidence:** HIGH（官方 PDF 一手）
- **Verification Need:** NONE
- **Ambiguity:** 官方 PDF 中文缺 ToUnicode，采用"拉丁简称 + dblp URL + 分节标题"解析；**当条目全称行缺失时会错位一行**，涉及条目（Machine Learning、Neural Computation、Computer Networks）已**逐个手工核对**，方法记于 sources.md §3.2–3.3。

## C005 — 既有本地文献正文中不含图结构指标词汇

- **Priority:** P2
- **Claim:** 仓库 `docs/papers/` 的 **36 份全文**中，`structural hamming` / `graph edit distance` / `SHD` / 边级 P/R/F1 的命中数为 **0**。
- **Source / Locator:** 对 `docs/papers/*.txt` 全量 grep；同批 grep 的对照组 `accuracy` 命中 **332** 次、`topology` **312** 次（证明检索本身有效，非编码问题）。
- **Finding:** 零命中是真实的，不是抽取失败。
- **Interpretation:** 与 C002 相互印证。**但**该语料是为 T005/T006 与 INFOCOM 调研装配的，**不是**为本次问题装配，故不能作为"领域现状"的证据，只能作为仓库内的旁证。
- **Confidence:** MEDIUM
- **Verification Need:** NONE
- **Ambiguity:** 语料用途不同，外推需谨慎——这一点已在 report.md §1.4 与 §6 写明。

## C006 — 候选组合及其可用条件

- **Priority:** P1
- **Claim:** 给出两套条件化候选：方案 A（完整图标签）= 有向边 P/R/F1 + `SHD-1`；方案 B（部分标签）= mask 域内有向边 P/R/F1 + 祖先可达 F1（完整子集）。
- **Source / Locator:** report.md §4（含各自的文献依据、本项目语义匹配依据、互补性、可用条件与 UNKNOWN、最强审稿质疑），选择理由草稿见 §4.1。
- **Finding:** 两套均**不采用**单独 coverage、单独 root Top-K、邻接 F1 作主指标；`SHD-1` 在部分标签下不适用。
- **Interpretation:** **这是执行者的有条件建议，不是研究决策**；最终指标待用户精读后确定，本包与 report 均不冻结指标。
- **Confidence:** MEDIUM（建议的性质决定，非事实性问题）
- **Verification Need:** NONE（待 Work 判断是否采纳）
- **Ambiguity:** 方案 A 的 `SHD-1` 依赖完整图标签，而该条件在项目内仍是 UNKNOWN（STATUS B02）⇒ **方案 A 当前处于"暂不可执行"状态**。

## C007 — 自动检索线索中的 6 处身份错误已纠正

- **Priority:** P2
- **Claim:** 上一阶段自动检索给出的候选元数据存在错误，核验时发现并修正。
- **Source / Locator:** sources.md §5.3 对照表。
- **Finding:** Eadro arXiv 应为 **2302.05092**（非 2302.05605）；MULAN arXiv 应为 **2402.02357**、
  DOI 应为 **10.1145/3589334.3645442**；A3 的 `10.1109/ACCESS.11408137` 是 **arnumber 而非 DOI**；
  gCastle 指标文件实为 `.../metrics/evaluation.py`；causal-learn 的 SHD 类在 `causallearn/graph/` 下。
- **Interpretation:** 说明**二手线索不能直接进正文**；本轮所有身份均回到正式页面/源码复核。
- **Confidence:** HIGH
- **Verification Need:** NONE
- **Ambiguity:** 无。
