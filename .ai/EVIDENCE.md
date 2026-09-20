# Evidence Pack — T010 文档同步

2026-09-16。T009 旧证据包见 [T009_before_EVIDENCE](T009_before_EVIDENCE.md)。本包只记录本轮文档更新依据和证据边界，不把 PPT 示意当作实验结果。

| Claim ID | 结论 | 来源/定位 | 性质与边界 |
|---|---|---|---|
| T010-C01 | Web/DCN 依赖与 Pingmesh 异常是论文动机入口 | 用户提供《pingmesh治理》PPT 第 1 页；Pingmesh 引用 | 方案动机；具体业务映射仍 UNKNOWN |
| T010-C02 | 平面排名不能表达设备依赖；图可能帮助恢复动作组织 | PPT 第 2 页 | 待验证机制；无真实动作/成本记录 |
| T010-C03 | PPT 示意为 A→B→{C,D}、排名 A,C,D,B、处理 A/B、4→2 | PPT 第 3 页 | illustrative；A 已排第一，不能证明根排名或效率改善 |
| T010-C04 | C1/C2 为 Local Ambiguity / Global Consistency；M1/M2/M3 为证据图/局部关系/锚点引导重建 | PPT 第 4–5 页及本轮方案说明 | 最新概念组织；不等于代码已重构 |
| T010-C05 | A 修复后 B 是否仍需处理、C/D `Established` 是否异常、反馈和停止规则均未确定 | PPT 信息缺口与本轮文档审查 | 必须补现场记录；不写确定恢复序列 |
| T010-C06 | 当前实现仍为 Stage 1 PC-STGR + Stage 2 P0 | `docs/project_overview.md` 与现有入口 | 仓库可核实；概念映射不改变实现 |
| T010-C07 | 旧 DEMO_001 与 PPT A/B/C/D 是两套示例 | [案例设计](../docs/conferences/WWW2027/论文引入设计：从工程师排障现场到传播图恢复.md) | DEMO_001 只作合成观测示例，旧预测不是证据 |
| T010-C08 | H1–H4 需要 matched evidence、incident groups、反馈和停止规则控制 | [最新方案说明](../docs/conferences/WWW2027/2026-09-16_最新方案与文档同步说明.md) | 验证设计，不是已执行实验 |

## 保留的项目约束

- 单设备根；Top-K 是竞争锚点，不是多根。
- 每条输出边映射原始 `task_topo` 邻接；缺失记录保持 unknown，不能自动变成 No Direct。
- 推断不得读取根/传播标签；Oracle 仅是显式评测包装层。
- 图质量、根排序和动作价值分开评价；模型生成图不能作为独立真值，静态示意动作数不能作为 MTTR。

## 本轮验证

目标 Markdown 已通过 UTF-8 解码和定点术语检查；已修入口中的已知失效 `PC-STGR设计方案.md` 引用。未运行测试、训练、评分、模拟器、数据审计或目录生成器，未产生新实验数字。
