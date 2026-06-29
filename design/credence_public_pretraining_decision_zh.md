# CREDENCE public pretraining decision note

Date: 2026-06-29

## 1. Short answer

可以使用公开 RCA 数据集预训练 CREDENCE，但不建议把 Pingmesh 数据说成
"仅仅作为测试集"。

更严谨、也更适合 NSDI 审稿的说法是：

> CREDENCE is source-pretrained and target-calibrated. Public RCA datasets are
> used to learn a raw evidence-trust scorer, while every reported Pingmesh case
> is evaluated out-of-fold. Probability calibration, BYPASS threshold selection,
> and wrong-bypass risk reporting are performed only on Pingmesh calibration
> folds that exclude the test case.

中文表达：

> 公开数据用于学习通用的 RCA 证据可信度表示；Pingmesh 数据不用于大规模训练
> 表示，但必须用于本域校准。最终报告时，每个 Pingmesh case 都是 out-of-fold
> 测试样本，因此不存在在同一个 case 上既调阈值又报结果的问题。

这比"我的数据集仅作为测试集"更稳。原因是 CREDENCE 的核心 claim 不是普通
classification accuracy，而是"高置信 BYPASS 的风险是否被控制"。这个风险只
能用目标域 Pingmesh calibration cases 来校准；公开数据和 Pingmesh 不同分布，
不能直接证明生产 Pingmesh case 上的 wrong-bypass 风险。

## 2. Why the current case set is small

现在的数据集确实偏小。现有设计文档按约 150-160 个 labeled Pingmesh cases
来规划风险控制和 bootstrap。小数据带来三类问题：

1. 学习一个复杂 confidence model 容易过拟合。
2. calibration fold 小时，低风险 BYPASS 的 Clopper-Pearson upper bound 会很松。
3. LLM rescue/harm 是稀有事件，分 bin 后 denominator 会更小。

公开数据能缓解第 1 点，也能部分缓解 confidence ordering 的不稳定；但不能单独
解决第 2 点，因为风险证书必须来自目标域 calibration。

## 3. Recommended method

主方法建议写成：

\[
R_i = f_{\theta_s}(\Phi_i), \qquad
C_i = g_t(R_i), \qquad
\pi_i = \Pi(C_i, D_i, \widehat{\Delta U_i}).
\]

含义：

- \(f_{\theta_s}\): 用公开 RCA 数据预训练的 raw evidence-trust scorer。
- \(\Phi_i\): 每个 case 的 evidence ledger features，例如 rank margin,
  rank agreement, evidence coverage, temporal coherence, semantic conflict,
  diagnosability。
- \(g_t\): 只在 Pingmesh calibration folds 上学习的 target calibration map。
- \(C_i\): target-calibrated confidence，不是公开数据上的置信度。
- \(D_i\): diagnosability score，用来区分 ARBITRATE 和 ESCALATE。
- \(\widehat{\Delta U_i}\): 估计 LLM 对当前 case 的 intervention value。
- \(\pi_i\): 最终路由动作，取 BYPASS、ARBITRATE 或 ESCALATE。

关键点：公开数据只决定 \(f_{\theta_s}\) 的表示和排序能力；Pingmesh 本域
calibration 决定概率含义、BYPASS 阈值和风险声明。

## 4. Public datasets to use

优先级建议如下。

| Priority | Dataset | Why useful | Risk |
| --- | --- | --- | --- |
| 1 | RCAEval | 多个公开 RCA 数据集、可复现实验和 baseline rankers，最适合把"method-case correctness"转成 confidence pretraining 样本。 | 多数是 microservice RCA，不是 datacenter Pingmesh。 |
| 2 | OpenRCA | 有 logs、metrics、traces 和 LLM-oriented RCA benchmark，适合学习 semantic/noisy-telemetry confidence。 | 企业软件/服务故障形态和网络设备根因不同。 |
| 3 | LEMMA-RCA | 多模态、多域 RCA 数据，适合学习 missingness、coverage、cross-domain difficulty。 | 域很杂，可能提升鲁棒性，也可能引入负迁移。 |
| 4 | ICASSP wireless RCA challenge | 更接近 network fault localization。 | Wireless topology 和 datacenter Pingmesh 差异很大。 |

论文里不要声称这些数据和 Pingmesh 同分布。它们的作用是 source pretraining /
representation learning / transfer baseline。

## 5. Three experiment regimes

论文实验至少保留三种设置。

| Regime | Public training | Pingmesh calibration | Pingmesh test | Paper role |
| --- | --- | --- | --- | --- |
| Target-only CREDENCE | no | yes | yes | 小样本本域基线，证明没有公开数据时系统是否已经可用。 |
| Source-only zero-shot | yes | no | yes | 迁移 sanity check，只能报告排序/accuracy，不能报告部署级 BYPASS 风险证书。 |
| Source-pretrained target-calibrated | yes | yes | yes | 推荐主方法。如果公开数据有效，应提升 AUROC/AURC 或相同风险下的 BYPASS coverage。 |

如果数据实在太少，使用 repeated nested cross-fitting：

1. 固定公开数据 adapter、source feature schema 和 source model family。
2. 将 Pingmesh 分成 outer folds。
3. 对第 \(k\) 个 outer test fold，完全不使用这些 cases 做 \(g_t\)、\(\tau_t\)、
   feature selection 或 threshold selection。
4. 在其余 Pingmesh folds 内做 target calibration 和 threshold selection。
5. 在第 \(k\) 个 held-out fold 上报告 CREDENCE decision 和 outcome。
6. 对所有 outer folds 聚合，统计单位始终是 unique case_id。

这样可以说"每个 Pingmesh case 都是测试 case"，但不能说"Pingmesh 标签完全
没有参与 calibration"。

## 6. What public pretraining is allowed to learn

公开数据可以学习：

- evidence coverage 和 correctness 的关系；
- rank margin / agreement 和 Top-K hit 的关系；
- telemetry missingness、时间一致性、semantic conflict 对诊断难度的影响；
- 不同 baseline ranker 的局部可靠性；
- LLM rescue/harm 的粗略先验，如果公开数据中有可比较的 LLM output。

公开数据不能学习并直接用于论文主 claim 的内容：

- Pingmesh BYPASS threshold；
- Pingmesh wrong-bypass risk certificate；
- Pingmesh-specific root-cause prior；
- Pingmesh case-type specific calibration probability；
- final paper figures 中的 target-domain risk-coverage curve。

一句话：公开数据学"排序感"，Pingmesh calibration 学"概率含义和风险边界"。

## 7. Reviewer-safe claims

强 claim：

> Source pretraining improves the ordering of evidence-trust scores, while
> target calibration preserves the Pingmesh-domain risk-control semantics.

中等 claim：

> Even when public-source transfer is imperfect, CREDENCE exposes a calibrated
> risk-coverage frontier on Pingmesh cases and prevents source-domain confidence
> from being mistaken for deployment confidence.

不能写的 claim：

> Public RCA data proves that CREDENCE's BYPASS decisions are safe on Pingmesh.

也不要写：

> Pingmesh is only used as a test set.

应改写为：

> Pingmesh cases are evaluated out-of-fold, and the calibration fold used for a
> reported test case excludes that case.

## 8. Why this is still fancy enough

这个方向不仅是"拿公开数据预训练一下"。真正 fancy 的点在于它把迁移学习变成
可审计的风险控制系统：

1. Public source pretraining: 学跨域 RCA evidence-trust representation。
2. Target calibration: 把 raw score 变成 Pingmesh-domain calibrated confidence。
3. Selective risk control: 在目标域 calibration 上选择 BYPASS threshold。
4. LLM intervention accounting: 分别度量 rescue、harm、cost，而不是默认 LLM
   一定有帮助。
5. Diagnosability split: 低置信 case 不都给 LLM；不可诊断的 case 应 ESCALATE。

NSDI 角度，这比单纯的 LLM reranker 更像系统贡献：它回答生产 RCA 里更实际的
问题，什么时候该相信已有 evidence，什么时候该调用昂贵且可能有害的语义推理，
什么时候应该承认证据不足。

## 9. Implementation order

推荐顺序：

1. 先在服务器跑 target-only CREDENCE，导出 `confidence_cases.jsonl`,
   `risk_coverage.csv`, `calibration_bins.csv`, `llm_value.csv`。
2. 如果 target-only 已有非平凡 BYPASS coverage，公开预训练作为增强实验。
3. 如果 target-only 很不稳定，公开预训练成为主线补强：先接 RCAEval adapter。
4. source-only zero-shot 只作 baseline，不作为主方法。
5. 最终比较 target-only vs source-pretrained target-calibrated CREDENCE。

## 10. Paper wording

可以放进 method/evaluation 的段落：

> Because the private Pingmesh case set is small, CREDENCE separates
> representation learning from deployment calibration. We pretrain the raw
> evidence-trust scorer on public RCA datasets converted into a common evidence
> ledger format. The public datasets teach the model which observable patterns
> tend to make an RCA method reliable, such as rank agreement, temporal
> coherence, evidence coverage, and semantic conflict. However, we do not use
> source-domain calibration to certify Pingmesh decisions. For every reported
> Pingmesh case, probability calibration and BYPASS threshold selection are
> performed on Pingmesh calibration folds that exclude the evaluated case. Thus
> public data improves confidence ordering, while target data defines the
> calibrated risk-coverage frontier.

中文导师汇报版：

> 我们不把小数据硬训练成一个复杂模型，而是把训练和风险校准拆开。公开 RCA
> 数据负责预训练一个 evidence-trust scorer，学习哪些证据形态通常可靠；Pingmesh
> 数据只负责本域校准和测试。每个 case 报结果时都是 out-of-fold，因此不会在同
> 一个 case 上调阈值再证明自己正确。这个设计既利用了公开数据，又保留了生产
> 网络风险声明的严谨性。

## 11. Links to source-backed dataset notes

- RCAEval: <https://github.com/phamquiluan/RCAEval> and
  <https://zenodo.org/records/14590730>
- OpenRCA: <https://github.com/microsoft/OpenRCA> and
  <https://microsoft.github.io/OpenRCA/>
- LEMMA-RCA: <https://lemma-rca.github.io/> and
  <https://arxiv.org/abs/2406.05375>
- Existing internal catalog:
  `design/source_verified_literature_catalog.md`

