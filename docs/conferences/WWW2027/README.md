# WWW 2027 论文与执行材料

## 当前阅读入口（2026-09-16）

- [最新方案与文档同步说明](2026-09-16_最新方案与文档同步说明.md)：根据《pingmesh治理》同步两挑战、三模块、A/B/C/D 示意与验证边界。
- [图指标、排查收益与相关工作缺陷：验收结论](指标与相关工作缺陷_验收结论.md)：对应用户最新三项需求。
- [T008-R 复验](../../../.ai/T008_R_acceptance.md)：部分通过，U1–U4 尚需收尾。
- [T009 阅读包](graph_metrics_literature/README.md)：已执行、待独立验收；指标矩阵、排查设计、逐篇限制与来源。

以下专题保留历史入口；T007 错误已由 T009 修正文，最终指标未冻结。

更新：2026-09-16。当前主线是从 Pingmesh 异常、原始拓扑与设备事件恢复 incident-specific 设备传播解释图。单设备起点假设不变；论文概念模块为 M1 事故证据图、M2 局部关系、M3 锚点引导全局重建。现有代码仍是 Stage 1（PC-STGR 锚点候选）与 Stage 2（P0 局部支持和条件 DAG），概念改名不代表代码已重构。

## T005 / T006 专题：Web relevance 原文调研与论证链复盘

[web_relevance/](web_relevance/README.md) 专题把 WWW 2024–2026 网络相关论文的 PDF 取下、
全文抽取、Introduction 单独定位，逐篇拆解其 Web relevance 论证结构。
**T006（2026-09-12）已把工作重心从"分类定位方案"改为"逐篇还原作者的实际论证链"**，
并对所选分析卡做了必要更正。

**先读两份 T006 产物**：

1. [argument_chains.md](web_relevance/argument_chains.md)——直接回答"作者怎样把 Web
   与这个具体网络问题连起来"：6 篇的 4–7 节点论证链、关键句对照表、证据止点，
   末尾横向归纳**六种桥接动作**（不再使用旧的"四类强弱"框架）。
2. [rpg_recon_argument_transfer.md](web_relevance/rpg_recon_argument_transfer.md)——
   3 条候选迁移链、中文草稿、最小补证表、最强反对意见、可写边界。

**结论分层（2026-09-12 T006-R 更新）**：论文复盘**主体已交付、关键推理已按验收 R1–R8 修正**；
证据**有限**（可完整复核的 DCN 论文只有 `www24-inart` 1 篇，它给出的是
**"Web 动机驱动、但非 Web 专用"**的链——Web 进入了动机层与瓶颈前提，
**未进入问题设定/方法/评价，也未验证具名 Web 服务与服务侧收益**）；
正式定位**待讨论**，两份报告都不给推荐排序。
`www26-starlink-cd` 的 Web 论证是本轮所见最承重的一篇，但它需要本项目不具备的
平台级数据前提。另有 13 篇仅有 ACM 单一公开位置、因机器人拦截未取得全文，
已如实记录、未绕过访问控制，补取结果见
[paper_manifest.md](web_relevance/paper_manifest.md) §T006。

注意：旧文件 [synthesis.md](web_relevance/synthesis.md) 与
[positioning_options.md](web_relevance/positioning_options.md) **保留历史、结论已被取代**
（顶部有被替代指针），仅用于追溯 T005 的原始推理。
本专题**更正**了下方"四项任务"中第 1 项的部分结论（尤其 MULAN / MetaKube 的
Web 关联强度）。

## T007 专题：图评价指标的文献依据调研（2026-09-13）

[graph_metrics_literature/](graph_metrics_literature/report.md) 专题为**给论文选图评价指标**提供可核验的
一手文献依据：核查每篇代表论文**实验里到底评价了什么**（图结构 / 根因排名 / 下游任务）、
指标定义、真值来源与发表级别。

**先读两份 T007 产物**：

1. [report.md](graph_metrics_literature/report.md)——开头一页给出**重点论文与理由**、
   候选指标及待确认前提；随后为分层证据表、重点阅读概述、指标比较、
   两套条件化候选组合与选择理由草稿。
2. [sources.md](graph_metrics_literature/sources.md)——论文身份/正式链接/全文版本与位置、
   指标证据、锁定的实现版本、身份纠错和缺文记录；不宣称重新完成 CCF 全量核验。

**执行状态（2026-09-15）：T009 已修正文，待独立验收。**
见 [逐项返修](graph_metrics_literature/T007_R_response.md)；原验收和原字节快照保留。
NEC 已有局部关系评价；AH、mask 和 SHD 已纠正；未知项不作否定能力证据。

APGNN 仅读到摘要，其全文图指标为 UNKNOWN；部分文献细则尚待定点核实。
**最终指标待用户精读后决定**；修订后的文献包可给阅读建议，也不取代
[现行图评价协议](./故障传播图指标调研与最终评价方案.md)。

## T008 专题：相关工作全面检索与可核验文献目录（2026-09-15）

[related_work_catalog/](related_work_catalog/README.md) 是**长期文献对照表**，
供添加参考文献、挑选精读论文和检查相关工作遗漏使用。检索截止日 2026-09-15，
三层覆盖（L1 核心近邻 / L2 相邻场景 / L3 方法基础），2015 年起并回溯经典。

**规模**：身份已核实 **306** 条 + 待核实 **13** 条；含 DOI 241 条；阅读卡 **16** 张。

| 入口 | 用途 |
|---|---|
| [catalog.xlsx](related_work_catalog/catalog.xlsx) | 按题名/venue/等级/时间/链接筛选（`Papers`/`Pending`/`Coverage`/`Venues`） |
| [catalog.csv](related_work_catalog/catalog.csv) | 机器可读主表 |
| [index.md](related_work_catalog/index.md) | 按层次与主题的简明索引 |
| [coverage_report.md](related_work_catalog/coverage_report.md) | 覆盖矩阵、缺口 G1–G11、停止依据 |
| [search_log.md](related_work_catalog/search_log.md) | 实际执行的检索通道与更正记录 |
| [papers/](related_work_catalog/papers/) | 核心近邻阅读卡 |

> **阅读时务必先看 `内容阅读深度` 列**：306 条中只有 **47** 条读到摘要，
> **259 条仅核验了身份与著录、未读正文**。`论文自身输出对象` 与 `与本文关系`
> 两列是**检索线索**，列名已标注「未逐篇核实」，不能当作原文事实引用。

**本轮发现的三项要点**（详见覆盖报告 §6）：

1. 「网络侧没有传播关系评价」这一旧概括**必须撤回**——NetEventCause 已有事件级局部
   原因关系的 ACC@k 与参考关系对照，APGNN 的题名本身就是「告警传播图」。
2. 最接近本文的**直接挑战者是两篇 2026 预印本**：PropLLM（逐跳回溯传播路径）与
   EvoCause（LLM 演化因果图，用 Node F1 / Case EM / Graph F1 / nSHD 评价，附 TeleRCA benchmark）。
3. 旧材料把 **COLA / REASON / CORAL 三个系统名当作正式题名**；其中 REASON 与 CORAL
   的正式题名与旧记录完全不同，COLA 与另存条目实为同一篇。

本目录**未改动** T007 的 `report.md` / `sources.md`（其 R1–R7 返修仍属 T007-R），
也**未改动**正式论文的 related work 与主指标决定。

## 本轮四项任务

建议按以下顺序阅读；执行依赖与验收记录见[后续任务执行记录](./2026-09-10_后续任务执行记录.md)。

1. [WWW 2024–2026 网络论文与投稿契合分析](./WWW近三年网络相关论文检索与投稿契合分析.md)：区分主研究与 Industry/Companion，从具体 Web 问题、输入输出及实验证据判断本项目契合点。
2. [工程案例与引入正文](./论文引入设计：从工程师排障现场到传播图恢复.md)：基于既有合成 DEMO_001，展示观测、工程师拟定操作、手工排障树及设备解释图。用户确认暂时没有现场记录，不称真实事故复盘。
3. [Challenge 修订](./Challenge设计：从普通根因定位转向故障图恢复.md)：将 C1 改为起点不确定性与图结构恢复的耦合，列出特殊要求、方法对应及可证伪实验。
4. [图指标调研与评价协议](./故障传播图指标调研与最终评价方案.md)：主指标、部分标注语义、raw/等价投影、失败分母、Oracle/共同根/端到端和实现差距。

## 当前稿件

- [中文连续正文](./Introduction_引入与以往工作_中文初稿.md)：案例引入和压缩相关工作，保留详细文献核对信息。
- [中文六部分提纲与配图规范](./Introduction_提纲_讨论稿.md)：已同步两挑战、三模块、贡献边界及新版案例图位置。
- [英文六部分提纲](./Introduction_Outline_EN.md)：与本轮中文任务和挑战同步。
- [相关工作与 Baseline 选型](./Related_Work与Baseline选型.md)、[Baseline 审查意见](./Baseline选型与相关工作审查意见.md)：输入、机制、输出粒度与公平比较边界。
- [SmartEye WWW2026 案例拆解](./SmartEye_WWW2026案例拆解.md)：Industry Track 的 AIOps 叙事参考，不能替代 Research Track 要求。

## 实现与证据

- [Baseline 入口](../../../Baseline/README.md)、[实现任务书](./Baseline实现任务书_供独立智能体执行.md)、[实现进度与验收](./Baseline实现进度与验收.md)：复现/adapt/inspired 的命名、依赖、输入资格和验收边界。
- [项目实现契约](../../project_overview.md)：现行代码两阶段实现及其与论文三模块的映射。
- [既有实验记录](../../experiment_records/)：旧结果、标签与评分修订的来源；不是本轮新增研究实验。
- [历史公开网页快照来源](./sources/来源清单.md)：保存抓取时点，不覆盖现行 CFP。以本轮调研中核验的官方页面为准。

当前首选 **Web Infrastructure and Agentic Systems**。正式范围及第一页 relevance 要求见 [WWW2027 Research Track CFP](https://www2027.thewebconf.org/research-track-papers/)。论文第一页需要建立 Web 基础设施的实际问题与贡献关系；模型名称、网络数据或绘图本身不构成范围证据。

## 已有图片的状态

本次保留并提交 `docs/f0.png`、`f1.png`、`f2.png`、`fig1.png` 及 2026-09-09 生成图。这些均为旧示意素材，不是观测/标签或本轮新版案例图。`f1.png` 的“Massive Observations”仍对应旧 C1；`f2.png` 的概率数字及输入/输出小拓扑仅为示意，正式使用前需逐边对齐，且不能用图中文字证明代码已实现可靠拒答。新版 Figure 1 以案例文档的事实和规范为准。

用户删除的过期方案与绘图文档不恢复；相关活跃入口已改指向上述现存材料。
