# WWW 2027 论文与执行材料

更新：2026-09-11。当前主线是从 Pingmesh 异常、原始拓扑与设备事件恢复 incident-specific 设备传播解释图。单设备起点假设不变；概念模块 M1/M2/M3 对应实现的 Stage 1（M1/PC-STGR）与 Stage 2（M2+M3/P0）。

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

## 本轮四项任务

建议按以下顺序阅读；执行依赖与验收记录见[后续任务执行记录](./2026-09-10_后续任务执行记录.md)。

1. [WWW 2024–2026 网络论文与投稿契合分析](./WWW近三年网络相关论文检索与投稿契合分析.md)：区分主研究与 Industry/Companion，从具体 Web 问题、输入输出及实验证据判断本项目契合点。
2. [工程案例与引入正文](./论文引入设计：从工程师排障现场到传播图恢复.md)：基于既有合成 DEMO_001，展示观测、工程师拟定操作、手工排障树及设备解释图。用户确认暂时没有现场记录，不称真实事故复盘。
3. [Challenge 修订](./Challenge设计：从普通根因定位转向故障图恢复.md)：将 C1 改为起点不确定性与图结构恢复的耦合，列出特殊要求、方法对应及可证伪实验。
4. [图指标调研与评价协议](./故障传播图指标调研与最终评价方案.md)：主指标、部分标注语义、raw/等价投影、失败分母、Oracle/共同根/端到端和实现差距。

## 当前稿件

- [中文连续正文](./Introduction_引入与以往工作_中文初稿.md)：案例引入和压缩相关工作，保留详细文献核对信息。
- [中文六部分提纲与配图规范](./Introduction_提纲_讨论稿.md)：已同步 C1、贡献边界及新版案例图位置；旧通用作图 prompt 仅作素材。
- [英文六部分提纲](./Introduction_Outline_EN.md)：与本轮中文任务和挑战同步。
- [相关工作与 Baseline 选型](./Related_Work与Baseline选型.md)、[Baseline 审查意见](./Baseline选型与相关工作审查意见.md)：输入、机制、输出粒度与公平比较边界。
- [SmartEye WWW2026 案例拆解](./SmartEye_WWW2026案例拆解.md)：Industry Track 的 AIOps 叙事参考，不能替代 Research Track 要求。

## 实现与证据

- [Baseline 入口](../../../Baseline/README.md)、[实现任务书](./Baseline实现任务书_供独立智能体执行.md)、[实现进度与验收](./Baseline实现进度与验收.md)：复现/adapt/inspired 的命名、依赖、输入资格和验收边界。
- [项目实现契约](../../project_overview.md)、[PC-STGR 设计](../../PC-STGR设计方案.md)：现行两阶段实现。
- [既有实验记录](../../experiment_records/)：旧结果、标签与评分修订的来源；不是本轮新增研究实验。
- [历史公开网页快照来源](./sources/来源清单.md)：保存抓取时点，不覆盖现行 CFP。以本轮调研中核验的官方页面为准。

当前首选 **Web Infrastructure and Agentic Systems**。正式范围及第一页 relevance 要求见 [WWW2027 Research Track CFP](https://www2027.thewebconf.org/research-track-papers/)。论文第一页需要建立 Web 基础设施的实际问题与贡献关系；模型名称、网络数据或绘图本身不构成范围证据。

## 已有图片的状态

本次保留并提交 `docs/f0.png`、`f1.png`、`f2.png`、`fig1.png` 及 2026-09-09 生成图。这些均为旧示意素材，不是观测/标签或本轮新版案例图。`f1.png` 的“Massive Observations”仍对应旧 C1；`f2.png` 的概率数字及输入/输出小拓扑仅为示意，正式使用前需逐边对齐，且不能用图中文字证明代码已实现可靠拒答。新版 Figure 1 以案例文档的事实和规范为准。

用户删除的过期方案与绘图文档不恢复；相关活跃入口已改指向上述现存材料。
