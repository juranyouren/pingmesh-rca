# docs 文档索引

本目录按用途分为四类。**当前论文 / 方法实现 / 实验与评价**是活跃阅读路径；
**历史与参考**只作追溯，不覆盖现行合同。上层入口见 [根 README](../README.md)。

## 当前论文（WWW 2027）

- **[WWW2027 论文与执行材料](conferences/WWW2027/README.md)** — 论文侧总索引，
  含本轮四项任务、当前稿件清单与配图规范。以下条目均以它为准。
- [Challenge 修订：从普通根因定位转向故障图恢复](conferences/WWW2027/Challenge设计：从普通根因定位转向故障图恢复.md)
  — C1/C2/C3 问题定义、方法对应与可证伪实验。
- [论文引入设计：从工程师排障现场到传播图恢复](conferences/WWW2027/论文引入设计：从工程师排障现场到传播图恢复.md)
  — 合成案例 DEMO_001 的引入写法（非真实事故复盘）。
- [Introduction 中文初稿](conferences/WWW2027/Introduction_引入与以往工作_中文初稿.md)、
  [中文提纲讨论稿](conferences/WWW2027/Introduction_提纲_讨论稿.md)、
  [英文提纲](conferences/WWW2027/Introduction_Outline_EN.md)。
- [WWW 近三年网络论文检索与投稿契合分析](conferences/WWW2027/WWW近三年网络相关论文检索与投稿契合分析.md)
  — 区分 Research 与 Industry/Companion，判定契合点。
- [相关工作与 Baseline 选型](conferences/WWW2027/Related_Work与Baseline选型.md)、
  [Baseline 选型审查意见](conferences/WWW2027/Baseline选型与相关工作审查意见.md)。

投稿范围以官方 CFP 为准；[sources/](conferences/WWW2027/sources/) 内为抓取时点的
网页快照，[来源清单](conferences/WWW2027/sources/来源清单.md) 记录抓取时间，不替代现行 CFP。

## 方法实现

- [项目概览与实现契约](project_overview.md) — 两阶段系统的输入、输出与入口总表。
- [PC-STGR 设计方案](PC-STGR设计方案.md) — Stage 1 网络结构与训练设定。
- [Baseline 实现](../Baseline/README.md) — 方法命名、输入资格、复现边界与命令。
- [Baseline 参数入口](../configs/baselines/README.md) — 各方法默认配置位置。
- [raw → 规范化输入字段映射](../Baseline/common/raw_to_input_mapping.md) — 含禁用字段。
- [实验脚本入口](../scripts/README.md) — 全部 runner 的用途与调用方式。
- [传播图标注工具](../pingmesh-propagation-labeler/README.md) — 人工 DD/EE 标注。

## 实验与评价

- **[故障传播图指标调研与最终评价方案](conferences/WWW2027/故障传播图指标调研与最终评价方案.md)**
  — 现行 `graph-eval-v2` 协议：主指标、部分标注语义、raw/等价投影、失败分母、
  Oracle/共同预测根/端到端口径。**新评价工作以它为准，实现尚未完成。**
- [后续任务执行记录（2026-09-10）](conferences/WWW2027/2026-09-10_后续任务执行记录.md)
  — 治理当前写作与任务顺序的日期化记录。
- [Baseline 实现任务书](conferences/WWW2027/Baseline实现任务书_供独立智能体执行.md)、
  [实现进度与验收](conferences/WWW2027/Baseline实现进度与验收.md)。
- [既有实验记录](experiment_records/) — 历史聚合结果与评分修订：
  [多根标签复核与传播图改进计划](experiment_records/2026-09-08_多根标签复核与传播图改进计划.md)、
  [LLM 与全量自监督汇总](experiment_records/2026-09-08_llm_and_full_self_supervised_summary.md)、
  [修正后的图评分](experiment_records/2026-09-08_graph_evaluation_corrected.json)。
  这些是服务器输出的**历史转述**，不含完整逐例可重放实验包，也不是本轮新结果。
- 当前证据缺口与 UNKNOWN 清单见 [.ai/STATUS.md](../.ai/STATUS.md)（本地工作区，当前尚未入库）。

## 历史与参考

保留研究追溯价值，但与当前阅读路径分离。**不据此恢复已停用方案或已删除文档。**

- [文献笔记](papers/) — 论文文本与综述：
  [论文文本与综述笔记](papers/)（如 [Pingmesh](papers/Pingmesh_ A Large-Scale System for Data Center Network Latency Measurement and Analysis.txt)）、
  [INFOCOM 2023–2025 根因定位调研](papers/INFOCOM_2023_2025_根因定位相关论文调研.md)、
  [FSE 近三年工程现象映射](papers/FSE近三年_工程现象与相关工作映射.md)、
  [相关工作：三类方法与缺口（INFOCOM 版）](papers/相关工作_三类方法与缺口_INFOCOM版.md)。
  本地文献笔记不自动证明 novelty，也不取代当前投稿方向。
- [历史演示图](f0.png) — `f0.png` / `f1.png` / `f2.png` / `fig1.png` 及 2026-09-09
  生成图均为**旧示意素材**，不是观测、标签或本轮新版案例图；正式使用前需逐边对齐。
- 更早的设计、诊断脚本、notebook 与演示材料在 [archive/](../archive/)，
  其范围说明见 [archive/README.md](../archive/README.md)。

用户已删除的过期方案与绘图文档不恢复；活跃入口已改指向现存材料。
