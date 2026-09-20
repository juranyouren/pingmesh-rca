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


## Dataset

内部 Pingmesh/DCN 故障观测、原始拓扑、设备告警/日志，以及分离保存的根与传播标注。原始故障数据不可发布或纳入 Git。公开演示 `DEMO_001` 为合成案例；其历史预测文件不是观测或真值。

数据正式名称、采集时间跨度、站点覆盖、代表性、标注者一致性、独立评测集：**UNKNOWN**，由数据负责人补充；本地数量与版本缺口集中记在 STATUS。不能把采样片段当作完整数据集。


## Important Constraints

推断不得读取根/传播标签；训练只能读训练折授权标签，Oracle 包装层是明确的测试根注入例外。完整数据训练 checkpoint 只用于未来未见事故。已用于研发的案例不能重新包装为独立测试集。

实验不得调用外部 LLM API；预期重型运行环境是服务器 Linux / Ascend NPU / 本地 vLLM。不得捏造真实事故、人工操作、业务故障、SLO/MTTR 或用户研究收益。不得未经证据将标签争议自动修成单根或正负边。





