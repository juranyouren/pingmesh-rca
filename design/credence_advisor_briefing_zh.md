# CREDENCE 导师汇报短版

## 一句话方向

CREDENCE 研究的不是“LLM 能不能做 RCA”，而是：

> 生产网络 RCA 系统什么时候应该相信已有确定性证据，什么时候应该调用 LLM
> 仲裁，什么时候应该承认证据不足并升级处理。

## 核心问题

当前 Pingmesh case 数量偏小，且数据在服务器上，本地无法直接验证。因此论文不能
只靠一个简单 margin gate，也不能声称公开数据能证明 Pingmesh 风险。CREDENCE 的
关键是把“置信度”定义成一个可校准、可审计、可降级的系统机制。

## 主要创新点

1. **Evidence ledger confidence**  
   对每个 case 构造证据账本，包含 rank margin、method agreement、topology/temporal
   evidence、semantic conflict、missingness 和 diagnosability。

2. **Risk-controlled BYPASS**  
   如果确定性方法置信度高，系统绕过 LLM；但 BYPASS 阈值必须在 Pingmesh target
   calibration fold 上选择，并报告 wrong-bypass upper bound。

3. **Intervention-aware ARBITRATE**  
   低置信不等于必然调用 LLM。CREDENCE 显式统计 LLM rescue 和 harm，只在预期有
   正收益的区域调用 LLM。

4. **Diagnosability-aware ESCALATE**  
   有些 case 不是“模型不够聪明”，而是观测本身不足。CREDENCE 把这类 case 从
   ARBITRATE 中分离出来，作为 ESCALATE。

5. **Source-pretrained, target-calibrated transfer**  
   公开 RCA 数据可以预训练 raw evidence-trust scorer；Pingmesh 数据必须负责本域
   calibration、threshold selection 和风险声明。

## 为什么不是普通 margin threshold

Margin gate 只回答“第一名和第二名差多少”。CREDENCE 回答的是：

- 这个 margin 在当前 case type 下是否可靠；
- 多个方法是否一致；
- 证据是否完整；
- LLM 在这个区域是 rescue 还是 harm；
- 在给定风险预算下可以覆盖多少 case；
- 如果不能安全 BYPASS，是否应该 ARBITRATE 或 ESCALATE。

因此 CREDENCE 的贡献不是一个分数，而是一个 calibrated selective diagnosis
control plane。

## 小数据边界

小数据不是不能做，但必须诚实：

- 用 case-level bootstrap，不用 candidate-level 伪样本。
- 每个 rate 都报告 denominator。
- 如果没有 safe threshold，就报告 `no_safe_threshold`。
- 强 claim 依赖 `risk_coverage.csv`、`calibration_bins.csv`、`llm_value.csv` 和
  `diagnosability_frontier.csv`。

## 公开数据预训练的正确说法

不建议说“Pingmesh 仅作为测试集”。更严谨的说法是：

> Public RCA datasets pretrain the raw evidence-trust scorer. Every reported
> Pingmesh case is evaluated out-of-fold, while probability calibration and
> BYPASS threshold selection are performed only on Pingmesh calibration folds
> excluding that case.

中文：

> 公开数据学习通用证据可信度表示；Pingmesh 数据负责本域校准和 out-of-fold
> 测试。公开数据改善 ordering，Pingmesh calibration 决定风险含义。

## 下一步服务器目标

先跑 target-only CREDENCE artifact pipeline，生成：

```text
confidence_cases.jsonl
confidence_extraction_summary.json
confidence_manifest.json
confidence_calibration.json
risk_coverage.csv
calibration_bins.csv
paired_case_outcomes.csv
bootstrap_intervals.csv
llm_value.csv
diagnosability_frontier.csv
```

服务器上一键运行：

```bash
export PINGMESH_DATA=/path/to/nodes_max_labeled
export PINGMESH_RESULTS=/path/to/results
export PINGMESH_NPU_CARDS=0,1,2,3,4,5,6,7
export CREDENCE_RUN_ID=credence_$(date +%Y%m%d_%H%M%S)
bash scripts/run_credence_artifacts.sh
```

这个脚本会跑两遍 inference：第一遍关闭 gate，得到 always-LLM response，用来统计
LLM rescue/harm；第二遍开启 gate，得到 CREDENCE 的 BYPASS/ARBITRATE 路由和
confidence features。两份 `res.json` 会在导出 `confidence_cases.jsonl` 时按
case 合并，避免用 BYPASS 的伪 response 去冒充真实 LLM 输出。

## Claim ladder

| 服务器结果 | 论文 claim |
| --- | --- |
| 有非平凡 BYPASS coverage，风险 upper bound 过线，LLM call 降低且 accuracy 不差 | 强 CREDENCE 系统论文 |
| confidence calibration 有效，但 LLM value 较弱 | calibrated risk frontier 论文 |
| calibration 较弱，但暴露 margin/LLM failure mode | auditable evaluation framework |
| extraction 或 label isolation 失败 | 先修 artifact，不写 claim |

## 保留设计文件

- `credence_nsdi_final_blueprint.md`
- `credence_paper_method_and_figures.md`
- `credence_algorithm_box_and_proofs.md`
- `credence_feature_schema.md`
- `server_handoff_runbook.md`
- `server_artifact_acceptance_criteria.md`
- `credence_public_pretraining_decision_zh.md`
- `source_verified_literature_catalog.md`
