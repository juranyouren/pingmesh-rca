# Experiment Index

更新：2026-09-11。E 编号为本次建立的长期索引，不是历史 run ID。新增实验顺延编号；标签/评分修订另立条目并链接旧实验，不能覆盖旧数。每项保留 Goal / Hypothesis / Setup / Result / Interpretation，原始大日志留在忽略的产物目录。

证据等级：`SERVER_REPORTED` = 用户转贴服务器输出，只有聚合记录；`LOCAL_ARTIFACT` = 本机有可核验产物。**本次未重跑研究实验。** E001–E004 的 Hypothesis 是按记录目的归纳，不声称曾预注册；历史结果均不是 graph-eval-v2。

统一缺项：207 例实验的完整输入/标签哈希、已核实事故组、精确 folds、完整冻结配置、代码 revision 与逐例预测 **UNKNOWN**。`nogit` 运行名不提供代码可追溯性。SSL 运行名表示自监督预训练后有监督根排序微调；P0 不拟合传播标签，P4 使用传播标签监督。

## E001 本地 LLM 图重排消融

Goal: 检验语义证据、候选图和 Stage-1 先验是否改善根排序。

Hypothesis: 在同一候选集合内，LLM 对证据/图的判断能净修正根选择。

Setup: `SERVER_REPORTED`；2026-09-08 收录，207 例；本地 DeepSeek-R1-Distill-Qwen-32B；Stage-1 为 `pc_stgr_edge_prob`，Top-1 66.67%；实际 Top-5 真根覆盖 203/207=98.07%。不是 E003 的最强 Stage-1。精确运行配置见源记录可得部分，完整冻结件 UNKNOWN。

Result:

| 输入/策略 | Top-1 | 改对 / 改错 | 净改对 |
|---|---:|---:|---:|
| Stage-1 | 66.67% | — | — |
| 证据 | 51.69% | 21 / 52 | -31 |
| 证据 + 图 | 54.59% | 25 / 50 | -25 |
| 先验 + 证据 + 图 | 60.87% | 15 / 27 | -12 |
| 共识门控 | 66.67% | 3 / 3 | 0 |

共识记录 309 次调用、2,382,983 输入 tokens。

Interpretation: 此模型与策略未支持 Top-1 改善；共识恢复原 Top-1，有额外成本。不能外推所有 LLM 无效，也不能与另一配置的 76.33% 直接归因比较。

Source: [9/8 实验记录 §1](../docs/experiment_records/2026-09-08_llm_and_full_self_supervised_summary.md)、[对应 JSON](../docs/experiment_records/2026-09-08_llm_and_full_self_supervised_summary.json)。

## E002 Stage-1 边支持与图特征消融

Goal: 检验传播边支持和图特征是否提供额外根判别信息。

Hypothesis: 同折同种子的图信息增强应优于 base 及仅 Stage-1 分数 MLP 控制。

Setup: `SERVER_REPORTED`；207 例；历史运行 `root_graph_ablation_self_supervised_20260903_111619_nogit`；实际分组独立性与完整配置 UNKNOWN。

Result:

| 方法 | Top-1 | Top-3 | Top-5 | MRR |
|---|---:|---:|---:|---:|
| PC-STGR base | 71.50% | 91.30% | 97.10% | 0.822494 |
| + edge probabilities | 66.67% | 94.20% | 98.07% | 0.803267 |
| base + score-only MLP | 71.50% | 91.30% | 97.10% | 0.818680 |
| base + graph MLP | 71.01% | 91.79% | 97.10% | 0.817955 |
| edge probabilities + graph MLP | 66.67% | 94.20% | 98.07% | 0.800966 |

Interpretation: 该组边增强提高 Top-5、降低 Top-1；图 MLP 未显示额外根排序收益。E003 是另一次完整配置，不能把 base 71.50% 与 76.33% 差值归于某个单独改动。

Source: [9/8 记录 §2](../docs/experiment_records/2026-09-08_llm_and_full_self_supervised_summary.md)、[运行信息 JSON](../docs/experiment_records/2026-09-08_llm_and_full_self_supervised_summary.json)。

## E003 完整 SSL Stage-1 + P0 / P4

Goal: 评价条件传播图，以及图选择对最终根排序的影响。

Hypothesis: 根条件图能恢复有用关系，并可能改善最终根选择；P4 监督边分类可能改善 P0 支持。

Setup: `SERVER_REPORTED`；207 例；run `full_self_supervised_20260902_154317_nogit`；旧标签/旧评分，结构等价口径；Stage-1 使用根监督微调，P4 另使用边监督。精确阈值、训练/校准配置需找回冻结件，不以当前默认值回填。

Result:

| 指标 | Stage-1 OOF | P0 | P4 |
|---|---:|---:|---:|
| Root Top-1 | 76.33% | 72.46% | 72.46% |
| Top-3 / Top-5 | 95.65% / 97.10% | 93.72% / 97.10% | 92.75% / 97.10% |
| MRR | 0.863573 | 0.832689 | 0.826006 |
| Edge P / R / F1 | — | 0.648597 / 0.662605 / 0.600823 | 0.269517 / 0.566735 / 0.269366 |
| Node F1 | — | 0.750833 | 0.446055 |
| 历史 strict exact | — | 0.454106 | 0.149758 |
| 平均输出边数 | — | 1.188406 | 3.038647 |

P0 拓扑/DAG/根可达合法率均 1.0；182 例发生结构聚合。程序状态 34 partially_observed、173 unidentifiable；平均 observed impact coverage 0.244234。

Interpretation: 旧同轮记录中 P0 图指标优于 P4，P4 图膨胀；最终根正确数从 158 降至 150，净少 8。合法率不等于准确率，程序 unidentifiable 不等于工程师确认的信息上限。历史 strict exact 缺完整标注门槛，不能改名为 v2 Exact。

Source: [9/8 记录 §3–4](../docs/experiment_records/2026-09-08_llm_and_full_self_supervised_summary.md)。

## E004 Candidate / Direct Oracle 误差分解

Goal: 区分根选择、候选漏召回与给定根下的图恢复误差。

Hypothesis: 确认根可改善图质量；两种 Oracle 的差异可显示 Top-K 外根遗漏的影响。

Setup: `SERVER_REPORTED`；207 例，P0 Top-K=5、`stage1_weight=1.0`；Candidate 真根覆盖 201/207，Direct 207/207；旧标签/旧评价器，候选外失败保留在全范围解释中。

Result:

| 设置 | Root Top-1（输入条件） | Edge-F1 | Node-F1 | 历史 strict exact |
|---|---:|---:|---:|---:|
| Candidate Oracle | 97.10% | 0.673314 | 0.703589 | 0.574879 |
| Direct Oracle | 100.00% | 0.679412 | 0.708547 | 0.579710 |

Interpretation: 已执行过；下一步统一重评。旧口径下给对根有帮助，但 Direct 相对 Candidate 仅增 0.006098 Edge-F1；固定正确根仍有图误差。Node-F1 反而低于普通 P0，需逐例解释。此设置不是理论上限，根输入不得当作自主定位成绩。

Source: [9/8 记录 §6](../docs/experiment_records/2026-09-08_llm_and_full_self_supervised_summary.md)。该文 §5 的 Oracle 待办早于 §6，进度以已记录结果为准。

## E005 标签或评分修正快照

Goal: 保存后续修正的数值及其来源，不与算法提升混淆。

Hypothesis: **UNKNOWN / 不适用算法假设**，这是重评分快照。

Setup: `SERVER_REPORTED`；207 例；来源 `user_pasted_evaluation_summary`；run_id=null；具体标签/evaluator 变化 `not_yet_recorded`；投影 `evidence_free_exact_structural_twins_v1`。不得自行补全所属 run 或修改项。

Result: Root accuracy 0.714976；Edge P/R/F1 = 0.672222 / 0.711594 / **0.664640**；Node-F1 0.791667；历史 strict exact 0.521739；182 例结构聚合。

Interpretation: 最新记录分数，不是已验证最佳算法结果。JSON 明确不主张算法提升；不能将 0.600823→0.664640 归为方法增益，不能与旧 Stage-1/P4/Oracle 或新 baseline 同表比较。

Source: [修正 JSON](../docs/experiment_records/2026-09-08_graph_evaluation_corrected.json)。需要找回标签差异、评分版本和逐例预测。

## E006 Baseline 功能与机制验收

Goal: 验证公共输入、训练、适配、评分接口与失败记录路径。

Hypothesis: 实现可以按约定完成接口调用；不是论文精度或因果恢复假设。

Setup: `LOCAL_ARTIFACT`；2026-09-10，Windows Python 3.12.10 CPU，依赖见 [锁定文件](../Baseline/requirements-repro.txt)。合成 NEC 6 例/3 折，Root/Oracle 各首折 2 例。

Result: baseline 专项 95 tests，0 failure/error/skip，24.208s；NEC Full 6/6 ok、Root/Oracle 各 2/2 ok。后续提交验证另记录主测试 206 passed / 35.34s、labeler 22 passed、合成 NEC 再次 6/6。

Interpretation: 工程功能记录，不能当成 100% 真实精度。本轮只读审计核对总报告列出的 6 个本地产物 SHA-256，均匹配；JUnit/合成预测/checkpoint 实存，未重跑测试。95 与 206/22 是不同范围的历史验证，不能相加称本轮测试数。当前仅部分 tests 文件被 Git 跟踪，复现需说明测试集合。

Source: [总报告](../Baseline/validation_report.json)、[验收记录](../docs/conferences/WWW2027/Baseline实现进度与验收.md)、[9/10 执行记录 §4](../docs/conferences/WWW2027/2026-09-10_后续任务执行记录.md)。本地产物目录：`tmp/baseline-validation/`，不搬入 `.ai/`。

## E007 Raw 输入资格与 BiAn 后端检查

Goal: 判断已有观测与运行环境是否支持真实 baseline 比较。

Hypothesis: **资格检查**；所需采集覆盖/有效长度及本地模型服务存在与否待核实。

Setup: `LOCAL_ARTIFACT`；2 个 raw 样例，观察窗口触发前后各 300 秒；BiAn 另用合成输入做真实 loopback HTTP smoke。是历史验收状态，本轮未 probe 服务。

Result: SkyNet 两例 ok（无精度真值）；PCMCI+、DYNOTEARS 各 2/2 input_ineligible，原因 collection_coverage_unknown。BiAn 一次调用 runtime_failure、无排名。两例设备数 22/11、物理边 16/13、窗口告警数 2/12；不能据此认定代表全量分布。

Interpretation: 缺采集覆盖不补零，缺服务不补 heuristic 假结果。正式比较需预先固定适用子集，并保留全清单适用率/失败效用。当前 BiAn 可用性 UNKNOWN。

Source: [PCMCI+ 资格](../Baseline/PCMCIPlus/validation/raw_eligibility.json)、[DYNOTEARS 资格](../Baseline/DYNOTEARS/validation/raw_eligibility.json)、[BiAn 验收](../Baseline/BiAnAdapt/validation_report.md)、[本地后端记录](../Baseline/BiAnAdapt/validation/local_backend_smoke.json)。

## Adding a New Entry

下一编号 E008。Setup 至少给 task（Root/Oracle/Shared/Full）、输入/标签/fold/config/evaluator 版本或哈希、监督额度、seed、运行位置和产物指针；缺失写 UNKNOWN。Result 同时保留样本数、适用/失败分母、主要指标和必要不确定性。Interpretation 写假设是否获支持、泄漏/混杂风险和可推广边界。计划不能先填结果，smoke 不能进入真实性能表。
