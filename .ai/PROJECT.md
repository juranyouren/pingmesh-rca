# RPG-Recon — Project Context

本文件保存长期背景与协作规则。阶段状态见 [STATUS.md](STATUS.md)，研究取舍见 [DECISIONS.md](DECISIONS.md)，实验数字见 [EXPERIMENTS.md](EXPERIMENTS.md)。

## Project Name

**RPG-Recon**：incident-specific、root-conditioned 的设备故障传播解释图恢复。仓库名为 `pingmeshPaper`；PC-STGR 是其中的根候选模块，不是整个系统的名称。

## Research Goal

从一次 Pingmesh 异常的端点上下文、原始 `task_topo` 与设备告警/日志，恢复有证据支持的设备级有向传播解释 DAG，并指出证据缺口。根排序提供起点假设；图恢复是论文主任务。

## Problem Definition

- 输入：事故观察窗口内的异常上下文、物理拓扑、设备事件及可用采集信息。缺少记录不等于设备正常。
- 输出：选定设备起点、显式设备节点、有向传播边、证据引用、备选解释与未决关系。
- 研究范围：单设备根。Top-K 表示相互竞争的单根假设；不表示多个根同时故障。
- 每条输出设备边必须对应原始 `task_topo` 邻接。物理连边、时间先后、告警语义只能提供支持，不能直接成为因果真值。
- 目标是观测支持的解释图；不声称识别真实 ECMP 逐包路径、完整结构因果模型或干预效应。事件依赖层辅助设备图，不替代其评价目标。

## Motivation

根因排名只能回答优先检查谁，尚未解释影响如何经设备关系展开。起点不确定、关系方向证据不足，以及局部关系难以组成一致图，构成 C1/C2/C3。其实际诊断价值需要通过图评价与工程任务验证，不能从图的可视化效果推出。

## Target Venue

仓库约定目标：**The Web Conference / WWW 2027 Research Track**，拟定位 Web Infrastructure and Agentic Systems。投稿时重新核验官方范围；本文件不保存动态截止日期。需要实证建立服务与网络端点的关联，不能仅靠 Web/LLM 术语说明契合度。

## Core Contribution

以下为待实验支撑的贡献主张，不是已经证明的 novelty：

1. 将事故起点的不确定性与可恢复图结构联系起来，以多个候选起点进行条件重建。
2. 将设备邻接对的局部方向支持与根条件图组装分开，输出可追溯解释和证据缺口。
3. 用固定根与自主流程的对照，区分根定位、关系恢复和图选择的作用；这是评价设计，本身不自动构成独立科学创新。

概念模块：Stage 1 / M1 = PC-STGR 候选排序；Stage 2 / M2+M3 = 局部支持与条件 DAG 重建。历史代码 `propagation/m1`、`m2` 的编号不定义论文模块。方法细节见 [项目概览](../docs/project_overview.md) 和 [PC-STGR 设计](../docs/PC-STGR设计方案.md)。

## Dataset

内部 Pingmesh/DCN 故障观测、原始拓扑、设备告警/日志，以及分离保存的根与传播标注。原始故障数据不可发布或纳入 Git。公开演示 `DEMO_001` 为合成案例；其历史预测文件不是观测或真值。

数据正式名称、采集时间跨度、站点覆盖、代表性、标注者一致性、独立评测集：**UNKNOWN**，由数据负责人补充；本地数量与版本缺口集中记在 STATUS。不能把采样片段当作完整数据集。

## Evaluation Protocol

遵循 [图评价协议](../docs/conferences/WWW2027/故障传播图指标调研与最终评价方案.md)。协议要求与实现完成度分开记录。

- Root：Top-K、MRR、实际候选覆盖；Oracle：明确注入确认根的条件实验；Shared：共同冻结的 OOF 预测根；Full：方法自身根与图。
- 主指标为逐案例宏平均有向边 P/R/F1；Full 加原始设备根 Top-1 与 Joint-Edge-F1。完整/部分标注分表，各列披露有效分母。
- unknown 掩码排除，allowed 中性；possible 需工程师澄清。显式节点包含孤立根；Exact 仅用于完整且复核的图。
- raw-device 与标签无关的结构等价投影并列，联合根正确性仍按原始设备。投影不能把“负例+未知”变成已知负例。
- 保留失败、弃权、缺失预测、成功空图与缺标的区别；合法率和覆盖率属于诊断指标。
- 按经核实的事故组划分；训练、词表、预训练、校准和阈值选择均隔离测试组。配对组 bootstrap 依赖真实 group manifest。

## Important Constraints

推断不得读取根/传播标签；训练只能读训练折授权标签，Oracle 包装层是明确的测试根注入例外。完整数据训练 checkpoint 只用于未来未见事故。已用于研发的案例不能重新包装为独立测试集。

实验不得调用外部 LLM API；预期重型运行环境是服务器 Linux / Ascend NPU / 本地 vLLM。不得捏造真实事故、人工操作、业务故障、SLO/MTTR 或用户研究收益。不得未经证据将标签争议自动修成单根或正负边。

## Shared Memory Workflow

ChatGPT Work 负责方向、论文叙事、假设、实验设计、审稿分析与科学决策；Claude Code 负责代码理解、实现、调试和实验执行。

1. Work 会话先读取 [GPT_BRIEF.md](GPT_BRIEF.md)，仅按问题补读决策、实验条目或来源段落。需要实现时把一个可验收任务写入 [CURRENT_TASK.md](CURRENT_TASK.md)。
2. Claude Code 开始时显式读取根目录 [AGENT.md](../AGENT.md)、[CLAUDE.md](../CLAUDE.md)、CURRENT_TASK 和 STATUS，再定位必要代码。
3. Claude 完成后写 [HANDOFF.md](HANDOFF.md)：改了什么、证据与命令、失败和未决项；更新 STATUS，新增实验索引。原始数据、日志、checkpoint 留在既有忽略目录。
4. Work 审阅 HANDOFF，判断结果是否支持假设，再压缩更新 GPT_BRIEF；重大取舍追加 DECISIONS。已否定方向重开时记录新证据及取代的决策 ID。

这是文件协作约定；本次不建立两个产品之间的自动同步。使用同一 checkout，或显式传递最新摘要文件并核对更新时间；内部原始材料不随摘要传递。两个 Agent 不同时覆盖同一记忆文件，交接以任务 ID、日期和代码/数据版本对齐。

证据流：原始信息 → Claude 分析 → HANDOFF → Work 审核 → GPT_BRIEF。实验条目只放小表与产物指针，不复制大日志。任何缺失记 `UNKNOWN` 并写明补充人/材料；区分“仓库可核实”“历史转述”“计划”“本轮验证”。最新用户指令优先；代码用于确认实际行为，文档用于确认研究约定，二者冲突写入 STATUS，不能靠摘要宣称已修复。

通用协作规则（角色、上下文加载顺序、评审分级、Git 策略）见 [WORKFLOW.md](WORKFLOW.md)。

## 论文写作与图表约定

- 排障树组织的是调查动作与问题；输出 DAG 组织的是设备影响假设。二者不是同一种图，不能互换标注。
- 举例只使用合成 `DEMO_001` 的 `info.json` / `nodes.json` 观测，配合明确标注为示意的操作动作；其历史预测文件不是观测或标签。
- 图表规范以 [引入案例设计](../docs/conferences/WWW2027/论文引入设计：从工程师排障现场到传播图恢复.md) 与 `docs/conferences/WWW2027/Introduction_提纲_讨论稿.md` 为准：区分物理连边、观测、人工操作与推断的设备关系，并保持 Stage 1 → Stage 2 与 M1/M2/M3 的分组。
- 仓库中现有 PNG 是旧稿示意，不证明已实现的行为；不得据此声称已实现或已取得效果。

## 关键来源

以下文档是当前研究约定与优先级的权威入口，供两个 Agent 定位依据。它们与 `.ai/` 摘要冲突时以文档原文为准，并应在 STATUS 中记录冲突。

- [根 README](../README.md)、[文档索引](../docs/README.md)：方法、论文、实验与运行入口的导航。
- [WWW 论文索引](../docs/conferences/WWW2027/README.md)：当前稿件与研究状态。
- [2026-09-10 执行记录](../docs/conferences/WWW2027/2026-09-10_后续任务执行记录.md)：已完成工作、证据缺口与任务顺序，优先级以其为准。
- [图评价协议](../docs/conferences/WWW2027/故障传播图指标调研与最终评价方案.md)：指标、标签语义与实现缺口。
- [Challenge 设计](../docs/conferences/WWW2027/Challenge设计：从普通根因定位转向故障图恢复.md) 与 [引入案例设计](../docs/conferences/WWW2027/论文引入设计：从工程师排障现场到传播图恢复.md)：当前科学论证与举例写法。
- [项目概览](../docs/project_overview.md)、[PC-STGR 设计](../docs/PC-STGR设计方案.md)：实现与代码组织；二者的优先级列表让位于执行记录。
- [Baseline README](../Baseline/README.md)：方法命名、输入资格、复现边界与命令。

已退役的设计与图件文档是刻意删除的；不要恢复它们，也不要把旧笔记中的悬空引用当作现行要求。
