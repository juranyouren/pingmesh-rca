# Project Status

更新：2026-09-15（第二次）。**T008 已由 Claude Code 执行并交付，待 Work / 用户验收。**
交付物在 [related_work_catalog/](../docs/conferences/WWW2027/related_work_catalog/)：
身份已核实 **306** 条、待核实 13 条、阅读卡 16 张；9 项产物齐全，`check.py` 29 项全 PASS。
见 [CURRENT_TASK](CURRENT_TASK.md)、[交接](HANDOFF.md)、[证据](EVIDENCE.md)。
**本轮未运行项目测试、训练、评分或数据审计；未改动算法/标签/评分协议/实验数字；
未改动 T007 的两份正文（其 R1–R7 返修仍属 T007-R）；未提交、未推送。**
**已知缺口**：APGNN 全文不可得；259/306 条仅核验元数据未读正文；
OpenAlex source 级逐年统计因配额未完成；中文期刊系统性检索未做。
详见 [覆盖报告](../docs/conferences/WWW2027/related_work_catalog/coverage_report.md) §4。

历史（当日第一次写入）：任务书发布，尚未执行检索。
见 [T008 发布任务书](T008_research_task.md)。
T007-R / T006-R 保留待办；T007-R 原活动任务已保存为 [任务快照](T007_R_task_snapshot.md)。
**T007 独立验收仍为部分通过，关键事实与指标推理需返修**。
见 [验收 R1–R7](T007_acceptance.md) 与 [T007 交接](HANDOFF.md)。产物
[report.md](../docs/conferences/WWW2027/graph_metrics_literature/report.md)、
[sources.md](../docs/conferences/WWW2027/graph_metrics_literature/sources.md)。
**资料交付、验收通过与指标定案分别记录**：当前报告仍需修正，最终主指标由用户精读后确定。
T006-R 仍为部分通过；R5/R8 已关闭，[二次验收 U1–U5](T006_R_acceptance.md) 保留待办，
不作为 T007 前置；[原 T006 任务](T006_research_task.md) 已完整留档，
T006 交接与证据快照另存为 [T006_handoff](T006_handoff.md)、[T006_evidence](T006_evidence.md)。
历史见 [T006 验收](T006_acceptance.md)、
[T006-R 逐项应答](../docs/conferences/WWW2027/web_relevance/T006_R_response.md)。
历史初始化基线 commit：`19fad0a`（2026-09-10）。
状态来源是当前工作区文件与已有报告；本轮未运行训练、真实数据重评分或外部模型调用，
未运行项目测试，未改动算法/标签/评分协议/实验数字。

## Completed Work

- 已有 PC-STGR 根候选、P0 条件传播 DAG、P4 监督边分类优化、结构等价工具、独立图标注工具及研究实验入口。
- 新 baseline 公共框架与 SkyNet-inspired / BiAn-adapt / NEC-reimpl / PCMCI+ / DYNOTEARS 实现已入库。可运行范围和复现差距见 [Baseline README](../Baseline/README.md)。
- 2026-09-08 记录包含根排序/图特征/LLM 重排、完整 SSL P0/P4、Candidate/Direct Oracle；不再把这些列为尚未首跑。见 [EXPERIMENTS](EXPERIMENTS.md) E001–E005。
- 2026-09-10 已完成 WWW 叙事、C1/C2/C3 修订、合成引入案例、评价协议与 baseline 功能验收。历史最终测试为主目录 206 passed、labeler 22 passed；合成 NEC 三折 6/6 预测成功。**本轮未重跑，不代表当前新测试结果或论文性能。**
- 本轮新增七个 `.ai/` 文件，建立任务、交接、决策和证据摘要流。没有改动算法、标签、配置或现有论文材料。
- 2026-09-11 T004 完成：新增根 `README.md`（80 行）与 `docs/README.md`（66 行）；删除 53 个
  纯缓存目录（约 10 MB，可自动再生，零跟踪文件受影响）；修复 3 处失效引用并同步 2 处过时待办。
  验证通过：206 + 22 测试、`Baseline.common --help` 退出 0、60 个 Markdown 文件 0 失效链接。
  未改动算法、评分语义、标签与实验数字。处置依据与待定项见 [HANDOFF.md](HANDOFF.md)。
- 2026-09-11 Codex 独立验收：T004 主体交付通过，交接记录待补正，详见 HANDOFF 验收补记。
  实际复验主测试 206 passed、labeler 22 项成功、baseline CLI 退出 0；不属于真实性能实验。
- 2026-09-13 T007 已交付两份产物、5 篇重点卡和候选组合；**独立验收部分通过，T007-R 待执行**。
  关键更正：NEC 已有局部原因关系恢复评价；CausIL 有真实数据代理图结构分数；
  A4 不支持所称“未观测边不计错”；SHD 对照混入 ArrowConfusion，零边 raw SHD 有定义。
  ErrorPrism 比例/定位及部分文献身份亦需修正，见 [R1–R7](T007_acceptance.md)。
  不沿用“网络侧全不评图”“反向边 SHD=0/1/2”等原交付概括。
  原任务及 T006 交接/证据存档保留。本次只核验和维护文档，未改两份核心报告正文或运行研究实验。

## Repository Map

| 路径 | 职责与审计结论 |
|---|---|
| 根 `README.md` | 2026-09-11 新增：项目、两阶段方法、目录表、文档入口与运行入口（80 行）。 |
| 根 `AGENT.md` / `CLAUDE.md` | 2026-09-12 起改为精简入口：`AGENT.md` 供 ChatGPT Work 加载上下文，`CLAUDE.md` 供 Claude Code 执行；项目事实与协作规则移至 `.ai/PROJECT.md`、`.ai/WORKFLOW.md`。 |
| `docs/README.md` | 2026-09-11 新增：按当前论文/方法实现/实验与评价/历史与参考分类的文档索引（66 行）。 |
| `Sys/Preprocess/` | 原始观测预处理、raw 拓扑 sidecar、标签无关结构等价映射。输入源字段需检查标签污染。 |
| `Sys/RootCauseAnalyze/stage1/` | 确定性排序、PC-STGR/SSL、图特征 MLP、verifier、历史 LLM 重排；后几项不是默认论文增益模块。 |
| `Sys/RootCauseAnalyze/propagation/` | 事件整理、邻接支持、P0/P4 接入、受约束解码与解释产物。`heterogeneous/` 为历史原型。 |
| `Sys/Score/` | 根/图评分、P4 训练及实验汇总；旧主图评分尚不满足新协议。 |
| `Baseline/common/` | 输入/标签/预测规范、group manifest、runner、适配及评价；已有 mask/失败统计，尚需与主方法统一。 |
| `scripts/` | Linux Bash 实验入口；`common.sh` 为主要环境配置。旧 README 含过时优先级/标签语义，不能覆盖最新合同。 |
| `configs/baselines/` | 配置索引；真正默认 JSON 在各 baseline 目录，验收默认不等于论文冻结配置。 |
| `tests/`、`pytest.ini` | 本机含更多被忽略的历史测试；干净 checkout 不能默认复现本机 206 项测试集合。使用 `python -m pytest`。 |
| `pingmesh-propagation-labeler/` | 本地人工 DD/EE 标注、盲标及可选预测 overlay；DEMO_001 是合成数据。预测辅助展示可能影响标注独立性，需记录标注流程。 |
| `docs/conferences/WWW2027/` | 当前论文索引、中文正文/中英文提纲、challenge、图指标协议、baseline 审查与执行记录。 |
| `docs/papers/` | 论文文本、综述笔记、历史 INFOCOM/FSE 叙事；本地文献笔记不自动证明 novelty 或取代当前投稿方向。 |
| `docs/experiment_records/` | 207 例服务器结果的聚合转述及评分修正记录，不含完整逐例可重放实验包。 |
| `docs/*.png`、`archive/ppt/`、`output/` | 旧示意图、演示稿/渲染与文档衍生产物；现行论文以 Markdown 稿件为入口。未发现当前完整 `.tex/.bib` 论文工程；外部完整稿件位置 UNKNOWN。 |
| `data/`、`tmp/`、`output/`、`archive/` | 内部数据、环境与生成物主要被忽略；`.ai/` 只放摘要和指针，不搬运其内容。 |

## Ongoing Work

**当前任务：T008 — 已交付，待验收。** 交付物与缺口见上文与 [交接](HANDOFF.md)。
`related_work_catalog/` 下 `README.md`、`catalog.xlsx`（Papers/Pending/Coverage/Venues）、
`catalog.csv`、`index.md`、`search_log.md`、`coverage_report.md`、`evidence.md`、
`screening.csv`、`papers/*.md` 共 16 张卡。本轮**未运行项目测试**（只做产物检查）。

以下为 T008 发布时的任务描述，保留以便对照：

**T008 — 建设长期可维护的相关文献总目录；已执行。**
三层覆盖，2015 年至实际检索截止日并回溯经典；CCF 等级/版本核验，不按等级筛文献。
交付 Excel/CSV 总表、Markdown 分类索引、检索日志、覆盖报告及核心近邻卡；按覆盖与证据质量验收。
完整要求见 [任务书](T008_research_task.md)。HANDOFF/EVIDENCE 仍属 T007，不代表 T008 已交付。

**保留待办：T007-R — 按 [独立验收 R1–R7](T007_acceptance.md) 修订文献事实及指标依据，尚未执行。**
已交付的论文对照、精读卡和候选组合有可用材料，但不能直接用于指标定案。
NEC 的事件级局部关系评价与设备整图指标须区别；CausIL 真实数据使用代理参考图；
A4 的未观测依赖降低召回，不能据此声称作者使用 mask；SHD 与 ArrowConfusion 分开。
APGNN 只有摘要，其全文是否报告图指标为 UNKNOWN；其他未核到细则的工作保持待核实。
**最终主指标未定案**。完整图标签、mask 资格仍 UNKNOWN，不能把理论可定义写成当前已可执行。
旧[指标协议](../docs/conferences/WWW2027/故障传播图指标调研与最终评价方案.md)
**正文未改**，只是不再被当作本轮结论依据。

**保留待办：T006-R 收尾 — 二次验收已完成，U1–U5 尚未执行。**
交付：[argument_chains.md](../docs/conferences/WWW2027/web_relevance/argument_chains.md)、
[rpg_recon_argument_transfer.md](../docs/conferences/WWW2027/web_relevance/rpg_recon_argument_transfer.md)
（**已重写**：2 条正式候选 + 1 条条件性补充，撤销"首选"排序）、
[T006_R_response.md](../docs/conferences/WWW2027/web_relevance/T006_R_response.md)（R1–R8 逐项应答）。
**结论分层：多数原文纠错通过、迁移推理及摘要同步待收尾 / 证据有限 / 定位未定（不给推荐排序）。**
用户确认华为云 DCN 的具体承载业务仍未知；该缺口不阻塞文献阅读，正式定位未选定。

**本轮更正的主要判断**：InArt 的依赖链是**连续写的**（P3 再点 web applications），
不是"断裂"；JitterSketch 有"缓冲后果 → 实时监测 → 缓冲策略调整"的桥；
Starlink 的"用户离 PoP 近"是旧稿的分析者概括（原文是 CDN 到 PoP 的邻近度），
"换成地面 ISP 问题消失"被原文自身否定；MULAN/GAMMA 的效果不能说成"与 Web 无关"；
ODNS 的"自证"判断已撤回，改为"验证边界待查"。
**二次验收残留**：迁移稿仍把双指标报告当作效度质疑的答案，并错误要求先排除共同原因才能保留
“多症状不证明多传播”的限制；草稿中未知覆盖/标注状态与 root-only 范围未完全同步。
两卡旧结论、InArt 问题前提归纳、README 统一缺文归因，以及少量地理/页段错误见 U3–U5。
DCN/云内部网络可完整复核的样例仍只有 `www24-inart` 1 篇。
候选补取结果与逐篇失败点见 [manifest](../docs/conferences/WWW2027/web_relevance/paper_manifest.md) §T006。

当前是“实现原型和历史结果已有，评价证据待整理、论文主张待验证”的阶段。没有已核实的活动训练任务；远端运行状态 **UNKNOWN**。本地静态盘点不能证明服务器空闲。

保留的科学议题：C1 的起点—图结构耦合是否产生超出普通 RCA 的价值；图恢复在固定根下是否有增益；P0 的距离约束是否过强。T001–T003 继续待办，本轮不运行这些实验。T005 的资料和失败记录见 [web_relevance 专题](../docs/conferences/WWW2027/web_relevance/README.md)、[原交接](HANDOFF.md) 与 [原任务书](T005_research_task.md)，其中失败原因和综合结论须结合验收更正阅读。T004 主体通过、交接记录见 [T004_handoff.md](T004_handoff.md)。

## Blocked Issues

| ID | 已知问题 / UNKNOWN | 需要补充或解决 |
|---|---|---|
| B01 | 本地 `data/` 仅 2 个 raw JSON；默认 processed cases、传播标签、完整 207 例预测/run 目录未见 | 数据负责人提供服务器路径、版本/哈希、冻结输入和预测清单；可先交脱敏清单，不必传原始数据 |
| B02 | 确认单根比例、possible 语义、allowed/unknown、图/节点完整度、标注一致性 UNKNOWN | 工程师提供逐例确认、审查范围和修订依据；多根/不确定/范围外独立标记 |
| B03 | 已核实 incident groups、重复导出/重叠窗口映射、独立新评测集 UNKNOWN | 提供 case→真实事故组及分组来源、开发数据使用史；不得把 case_id 当作验证过的组 |
| B04 | `graph-eval-v2` 已规定但尚未共同实现 | 统一规范输出、mask、显式节点、raw/等价投影和失败分母；冻结后重评 |
| B05 | 修正快照的 run_id、标签差异与 evaluator 版本 UNKNOWN | 找回 E005 原始产物及变更记录；不能从数值倒推修订原因 |
| B06 | 本地 BiAn 真模型后端在上次验收不可用；当前服务器服务/模型可用性 UNKNOWN | 正式运行前由执行 Agent 在授权本地服务环境 probe，并记录模型版本和失败 |
| B07 | 两个 raw 样例在时间序列方法中 input_ineligible；全量 coverage/长度资格 UNKNOWN | 先审采集覆盖和有效长度，不用补零绕过资格；报告全清单和共同适用子集 |
| B08 | 无真实事故复盘、业务—端点关系及人工收益测量 | 工程负责人提供可匿名复盘事故和服务依赖；未实测前只保留 illustrative opening |

## Confirmed Implementation Gaps

- [neural_graph.py](../Sys/RootCauseAnalyze/stage1/neural_graph.py) 的 `load_training_label` 取第一个根设备，可能把多根或候选集合压成单根；实际影响数量 UNKNOWN。其 `split_group_key` 基于端点/告警/AZ 的启发式，不能替代真实事故分组核实。
- [旧图 evaluator](../Sys/Score/evaluate_propagation.py) 将 definite/possible 同作正边、将 allowed 并入参考，uncertain 根给成功；节点/Exact/执行分母也与新协议存在差距。
- [P4 trainer](../Sys/Score/train_stage2_edge_classifier.py) 同样将 possible 作为正边，需在监督标签冻结后处理，不能仅修评分而忽略训练语义。
- [旧标签审计脚本](../scripts/audit_propagation_labels.py) 复用首根 loader、将 possible 计为正边，且跳过缺标/缺根案例；不能原样作为 T001 全量科学审计的依据。
- [Preprocessor.py](../Sys/Preprocess/Preprocessor.py) 要求 GT，并剔除根不在拓扑或根缺少相应告警/日志的案例。若历史数据由此生成，需审计样本选择偏差和静默根覆盖；不能据推断不读标签宣称整个数据构建不依赖标签。
- 主模型使用 `nodes.cross`，预处理从 raw `full_link.cross` 复制；[baseline 字段映射](../Baseline/common/raw_to_input_mapping.md) 禁用 cross。该字段的生成来源、推断时刻可用性和公平输入条件 UNKNOWN；目前不能断言已发生泄漏。
- P4 将无可用传播标签案例分配到 full-data 模型，尚需核查同事故组的其他案例是否用于训练。[Stage-2 入口](../Sys/RootCauseAnalyze/propagation_pipeline.py) 读取上游排名时不核验 OOF/input hash，且可能只枚举已有排名记录；必须另对完整 roster 检查缺例与训练隔离。
- P0 采用最短跳距严格增加的方向限制，比一般根可达 DAG 更强；与人工确认边的冲突率 UNKNOWN。不能把约束满足视作恢复正确。

标签是否见过 P0/其他模型输出、是否独立复核及盲标，仍为 UNKNOWN；标注 UI 支持盲标/overlay 不等于历史标签实际保持独立。需避免把预测经确认形成的同源标签当独立真值。

## Configuration and Runtime

从 [scripts/common.sh](../scripts/common.sh) 读取 `PINGMESH_DATA`、`PINGMESH_RAW_DATA`、`PINGMESH_RESULTS`、`PINGMESH_PROPAGATION_LABELS_ROOT` 等；`Sys/config.py` 未经脚本设置时仍有历史服务器默认根路径，且部分默认值与脚本不同。运行必须保存解析后的实际环境与配置，不直接沿用旧路径。

当前脚本默认：根模型 supervised、5 folds、seed 42；全流程 Stage-2 Top-K 5，通用 Top-K 10；Stage-1 权重 0.5。历史最佳为 SSL 配置，**这些默认值不证明能重现历史最佳**。baseline 默认种子 20260909、窗口前后各 300 秒、10 秒事件计数与 `device_greedy_v1`；真实配置以每个 run 冻结件为准。

本机存在 `tmp/baselines-venv/Scripts/python.exe`。Linux/NPU/vLLM 全量运行环境版本、当前资源占用和历史 run 的完整配置 **UNKNOWN**。不要为了初始化启动实验、模型服务或依赖安装。

## Current Experiments

E001–E005 是历史服务器聚合结果；E006/E007 是已留存功能验收和输入/后端资格检查；没有本轮新性能实验。旧 Oracle 已运行，下一步是版本一致的重评分。当前没有证据支持“P4 优化成功”“LLM 提升定位”或“v2 公平主表已完成”。

## Next Actions

**T008 / Claude Code — 当前优先：执行 [相关工作目录任务书](T008_research_task.md)。**
先整理种子与覆盖矩阵，再多源检索/引文扩展，核实身份与等级，生成目录和核心阅读卡，最后完成覆盖审计。
用户已确认写入任务书；无需重新确认常规检索策略。发布不等于检索已经启动。

**T007-R / Claude Code — 保留待办：按 [验收 R1–R7](T007_acceptance.md) 定点返修。**
先修 NEC/CausIL/A4 的评价对象与参考图口径，再修 SHD、公式、比例及文献身份；
同步 report/sources/入口/交接，交付逐项响应。保留已核实材料，不全量重搜，不运行实验。
验收通过后供用户选择精读论文及最终指标；不把用户定案或 T001 标签审计作为文献返修前置。

**T006-R 收尾 / Claude Code — 保留待办：按 [二次验收 U1–U5](T006_R_acceptance.md) 定点修正，尚未执行。**
先修双指标效度和共同原因的逻辑条件，再同步草稿中的事实标签、root-only 范围、标注未知状态，
最后清除卡片/入口旧结论并校正少量地理事实、页段与顺序归属。
R5/R8 关闭，已修好的来源、实验定义和用户研究控制不要求重做。
**正式定位未选定**；补齐业务映射或全部 DCN 缺文不作为本轮返修前置。
**未完成（已在文档中如实标注）**：逐页视觉 QA（本机无 `pdftoppm`，按要求在服务器执行）、
最近邻 N1–N5 的实际核实、`graph-eval-v2` 统一实现与独立关系标注下的重评、使用者实验。
二次验收写入前独立检查：**71 个 Markdown、409 条相对文件链接（含 URL 解码）、0 失效**。
文档增加后计数会变化；检查口径和版本见二次验收。未运行项目测试或研究实验。

**T004 / Claude Code — 清理仓库并建立文档索引：已完成（2026-09-11）。** 删除 53 个纯缓存
目录（约 10 MB，全部可自动再生），新增根 `README.md` 与 `docs/README.md`，修复 3 处失效的
`论文方案.md` 引用并同步 2 处过时待办。**零个被跟踪文件被删除或移动。** 验证：206 + 22
测试通过、60 个 Markdown 本地链接 0 失效。`.ai/` 已纳入版本控制，变更已提交到
`graphrebuild`（未推送）。待用户决定的待定项（`.codex-tmp/`、`RCAcopilot/`、
`/tests/*` 忽略规则）见 [HANDOFF.md](HANDOFF.md)。

以下研究任务继续保留待办，本次 T008 不自动启动：

用户最新执行约束（2026-09-11）：后续审计、重评分与实验在服务器执行，不在本地电脑执行。
T001 后续可拆出“服务器只读证据清点与待签认审计包”；该建议未启动，当前优先 T008 文献目录。

1. **T001 / Claude + 工程师：证据冻结准备。** 完成全量清单审计工具；缺源显式报告；工程师确认根/边语义和真实分组后再冻结。交付：审计摘要、缺口、版本指纹及待签认 manifest。
2. **T002 / Claude，Work 审核协议：统一评价。** 同一规范评价入口覆盖主方法和 baseline；先用可手算的合成例验证语义，再接真实标签。此项代码可与人审并行准备，真实主表依赖 T001。
3. **T003 / Claude 执行，Work 分析：重评与 Shared 控制。** 用冻结预测重评 P0/P4、Candidate/Direct Oracle；补共同 OOF 预测根；分离 root correction/corruption、候选漏召回及固定根图误差，再决定 decoder/P4 优化。

真实案例与服务依赖材料的收集可并行。大规模调参、扩展 LLM 重排、多根研究和复制按钮不作为默认下一任务。

## Maintenance

重大进展更新本文件日期、状态和依赖；同次更新 HANDOFF 与相关实验 ID。实验“计划/已执行/报告已收到/已复现/可进论文”分别标记。未提交用户修改和无关文件不归入 Agent 的完成项。

来源优先读：[根 README](../README.md)、[docs 索引](../docs/README.md)、[最新合同](../AGENT.md)、[9/10 执行记录](../docs/conferences/WWW2027/2026-09-10_后续任务执行记录.md)、[图评价协议](../docs/conferences/WWW2027/故障传播图指标调研与最终评价方案.md)、[WWW 索引](../docs/conferences/WWW2027/README.md)。9/8 文档前段 Oracle 待办已过时；项目概览的旧 Immediate Priorities 已于 T004 替换为指向本文件的说明，不据此恢复已暂停任务或已删除文档。
