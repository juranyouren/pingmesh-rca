# Research Decisions

初始化：2026-09-11。D001–D006 整理既有合同，不伪造此前决策的精确时间；D007 记录用户本次要求。研究决策由 Work 维护，执行发现可先写 HANDOFF。若逆转决策，追加新 ID 并指明 supersedes，不删除旧依据。不将“未验证”写成“已否定”。

# D001 图恢复为主任务，保持单设备根范围

## Decision

RPG-Recon 恢复设备传播解释 DAG；根排名供应竞争起点。Top-K 不表示并发多根；多根与链路根扩展延后。

## Context

历史材料曾聚焦设备 RCA 与 LLM 推理，后续也讨论多根，但当前论文需要一个可检验的明确目标。

## Evidence

[AGENT.md](../AGENT.md) 的 Project 与 Paper Argument；[当前 WWW 索引](../docs/conferences/WWW2027/README.md)；[Challenge 设计](../docs/conferences/WWW2027/Challenge设计：从普通根因定位转向故障图恢复.md)。C1 已改为起点不确定性改变可恢复结构。

## Consequence

Root Top-1 不能独自证明主要贡献；同时需要固定根/自主图实验。多根、不确定根、范围外案例保留分类和覆盖统计，不能取标签第一项强行符合模型。代码尚有首根读取缺口，见 STATUS。

# D002 P0 为论文方法，保留 P4 与重排负结果

## Decision

P0 确定性局部证据支持与条件解码为主方法；P4 有监督优化单列，P1 退出活跃矩阵。默认不继续扩大 LLM 重排、图 MLP/verifier 或 P4 调参。

## Context

方法分支增加不等于科学贡献；需保留不成功实验，避免重复投入或只报告有利配置。

## Evidence

[历史运行记录](../docs/experiment_records/2026-09-08_llm_and_full_self_supervised_summary.md)：E003 同轮旧口径 P0/P4 Edge-F1 为 0.600823/0.269366，P4 图较膨胀；图选择后根 Top-1 从 76.33% 降为 72.46%。E001 LLM 共识重排 Top-1 无增益，E002 图 MLP 未显示额外判别力。[最新合同](../AGENT.md) 明确当前方法取舍。

## Consequence

保留实验为有限配置下的负结果；不外推为“所有 LLM/P4 均无效”。重开需具体误差证据和训练侧固定的可证伪假设。SSL 是预训练后用根标签微调，不能把整个方法称无监督。

# D003 先冻结标签与分组，再统一评价和重评分

## Decision

graph-eval-v2 是目标协议，实施前不重命名旧分数。按“标签/事故组审计 → 共同评分入口 → 已有预测重评分 + Shared → 配对真实比较”的依赖推进。

## Context

旧主评分与新 baseline 在 possible、allowed、uncertain 根、显式节点、完整度和失败分母方面不同；新高分还缺变更溯源。

## Evidence

[图协议第 9 节](../docs/conferences/WWW2027/故障传播图指标调研与最终评价方案.md)、[9/10 执行记录第 2 节](../docs/conferences/WWW2027/2026-09-10_后续任务执行记录.md) 列明差距与顺序。E005 修正 JSON 明确 `algorithm_improvement_claim=false`、`run_id=null`。

## Consequence

unknown 掩码；allowed 中性；possible 人审；完整/部分分表；显式孤立根、raw/等价投影及失败分母统一。标签/计分修正与算法改变分别记录。真实分组未确认时不称独立 OOF，不给伪精确的组 CI。不得仅为提高指标选择标签解释。

# D004 用 Root / Oracle / Shared / Full 分离贡献

## Decision

Root 评价排名；Oracle 给确认根评价条件图；Shared 固定同一 OOF 预测根；Full 评价各方法自己的根与图。Candidate Oracle 与 Direct Oracle 分开，保留候选未召回案例。

## Context

图选择可改对也可改错；根输入不同会混淆图能力，Top-K 漏召回与固定根解码错误也需分离。

## Evidence

E003 图选择净损失 8 个正确根；E004 已有 Candidate/Direct Oracle，旧 Edge-F1 0.673314/0.679412，仍有固定正确根下的错误。[评价协议第 7 节](../docs/conferences/WWW2027/故障传播图指标调研与最终评价方案.md) 规定比较设计。

## Consequence

下一轮先重评既有 Oracle，新增 Shared 控制，不重复宣称首跑。Oracle 根准确率是输入条件，Direct Oracle 不是理论图恢复上限。Full 报 Root Top-1、Edge-F1、Joint-Edge-F1，并单列 correction/corruption；不预设选图改善根排序。

# D005 Baseline 保留原机制、输入资格与适配边界

## Decision

使用公共框架下的 SkyNet-inspired、BiAn-adapt、NEC-reimpl、PCMCI+、DYNOTEARS；不将旧同名 toy/统计脚本当等价复现。时间图先审输入资格，根-only 方法若接 P0 必须命名 `X + P0`。

## Context

原论文任务粒度、观测和输出不同，直接拼表会把适配器能力或数据可用性混成方法性能。

## Evidence

[Baseline README](../Baseline/README.md)、[选型审查](../docs/conferences/WWW2027/Baseline选型与相关工作审查意见.md)。E006 仅功能验收；E007 两例时间图输入不合格，BiAn 历史后端不可用。

## Consequence

保存 native 图、设备投影、最终适配图及删除理由，不暗用 P0 补图。Root-only、图-only 与 Full 支持范围照实报告；全清单适用率与预先确定的共同适用子集分开。NetRCA 固定类别不冒充任意设备定位；缺观测的 REASON/CORAL 不承诺 Full；新增方法需先核实原始机制和输入条件。

# D006 限制论文案例与因果/工程收益主张

## Decision

当前 opening 使用合成 DEMO_001 的 `info.json` / `nodes.json`，排障动作为 illustrative。设备 DAG 表示影响假设；排障树表示操作组织，二者不是同一真值图。旧 demo_predictions 和图片不充当事故证据。

## Context

目前无可用现场复盘；将示意图、推测动作或合法率写成业务实证会使论文主张失真。

## Evidence

[案例设计](../docs/conferences/WWW2027/论文引入设计：从工程师排障现场到传播图恢复.md)、[WWW 索引图片状态](../docs/conferences/WWW2027/README.md)、[9/10 执行记录](../docs/conferences/WWW2027/2026-09-10_后续任务执行记录.md)。现有 P0 的最短跳距递增限制也不是物理传播规律。

## Consequence

不编造真实事故、Web 请求失败、人工动作、SLO/MTTR 或用户收益。目标会议仍是 WWW 2027，实际 relevance 需要服务依赖证据。最接近方法的区别必须逐项对照；不能用“前人只有根排名”“首次融合拓扑时间”等笼统论断代替 novelty 证据。

# D007 以 `.ai/` 管理共享长期记忆

## Decision

按用户 2026-09-11 指令建立七文件协作系统：Work 决策，Claude Code 执行，HANDOFF 经审核后压缩为 GPT_BRIEF。长期背景、决策、短期任务和实验分开。

## Context

代码、日志与历史方案过多，且旧优先级仍留在 overview/scripts README，直接堆叠会使 Agent 恢复过时任务或混用结果。

## Evidence

本轮仓库审计发现旧 Oracle 待办与后文已有结果并存，P4 旧优先级与最新合同不同；用户明确指定共享记忆结构及分工。

## Consequence

只维护可溯源摘要，缺失标 UNKNOWN；GPT_BRIEF 保持约 1000–2000 tokens 的阅读规模。每次执行有任务 ID、范围、验收、命令与交接；初始化本身不执行 T001，不自动启动训练或建立跨产品同步。执行会话显式读取文件，避免依赖隐式加载。
