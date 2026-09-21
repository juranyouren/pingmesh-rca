# RQ1：设备传播图恢复

入口：`python -m Baseline.RQ1 run`，或在服务器执行 `bash scripts/run_rq1.sh run`。
默认方法：TimeOrder、NetEventCause、PCMCI、THP、Ours；THP 已加入七指标表。
2026-09-21 起在本地 CPU 验证环境用真实 case `8294294` 跑通全流程（见 §6）。
该 case 的传播 GT 只有 `possible` 边，因此评分口径改为默认 `possible-positive`（见 §3）。
**n=1、自动分组未核实，属管线自检，不是论文结果。**

## 直接运行（2026-09-21 更新）

在服务器项目目录执行：

```bash
bash scripts/run_rq1.sh
```

脚本 source `scripts/common.sh`，不再要求手填输入、GT、输出路径：

| 项目 | common.sh 配置 | 默认位置 |
|---|---|---|
| 节点观测 | `PINGMESH_DATA` | `data/node/nodes_max_labeled` |
| 传播图 GT | `PINGMESH_PROPAGATION_LABELS_ROOT` | `data/propagation_labels/<case_id>/propagation_label.json` |
| 输出根目录 | `PINGMESH_RESULTS` | `data/res`，自动建立 rq1_oracle 时间戳目录 |
| 方法参数 | `PINGMESH_RQ1_CONFIG` | `configs/baselines/rq1.json` |
| 根条件 | `PINGMESH_RQ1_CONDITION` | `oracle`，使用传播 GT 中确认的单根 |

本地和服务器使用相同相对路径。本地只有两个示例、没有传播 GT，使用只读检查：

```bash
bash scripts/run_rq1.sh --check-inputs
# Windows 无 Bash 时（使用上述相同相对路径默认值）：
python -m Baseline.RQ1 --check-inputs
```

检查只读取节点观测，不读取 `label.json` 或传播 GT、不运行模型、不写实验目录。
正式运行缺 GT 会说明应在服务器执行，不伪造标签或改用根标签生成传播真值。
`--dry-run` 是包含 GT/根/分折的严格预检，需在有 GT 的服务器运行。

若 PCMCI 返回 `input_ineligible: collection_coverage_unknown`，含义是导出未附带完整采集证明，
不是缺包或 GT 缺失。当前节点导出可以显式选择**已导出事件计数**实验：

```bash
bash scripts/run_rq1.sh --pcmci-coverage record-count
# 或在 common.sh / 当前会话设置后，继续使用零参数入口：
export PINGMESH_RQ1_PCMCI_COVERAGE=record-count
bash scripts/run_rq1.sh
```

该模式仅在没有覆盖元数据时将“无导出记录”计为 0，不代表设备健康或真实采集完整。
输入本身不被改为 complete，已有明确采集缺口仍保留掩码，不用补零绕过；
有效设备不足、序列太短等检查仍然生效。结果表、配置和方法名会标记 record-count 模式，
不能把它与严格采集覆盖结果混为一类。默认 `config` 沿用 JSON 中 require_coverage，
可用 `--pcmci-coverage strict` 强制严格模式。

事件标识：原始 `alarm_id` 可能重复，生成的事件 ID 使用来源、设备、原始告警 ID 和
白名单观测内容的 SHA-256。时间／内容不同的记录分别保留，相同观测重复导出去重；
这表示不同观测记录，不代表已证明是独立故障。显式 `event_id` 保持原值，其内容冲突仍报错。
`input_diagnostics.reused_alarm_id_groups` 记录复用情况。
2026-09-21 修复更改了原始观测生成 ID 的规则；重新读取原始节点后输入指纹会变化，
若手动使用旧 manifest，需要从相同核实分组重新生成；默认入口会自动生成新 manifest。

GT 可直接使用现有目录格式 `edges` / `dd_edges`，无需手工转换。
**标签口径由 `--label-policy` 决定（默认 `possible-positive`）：**

| 原始 state | `possible-positive`（默认） | `strict` |
|---|---|---|
| `definite` | 有向正边 + 双向 known 掩码 | 同左 |
| `possible` | **有向正边 `from→to` + 双向 known 掩码** | 保持未判定 |
| `explicit_no_direct` | 双向 known，非正例 | 同左 |
| 其余状态 | 未判定，计入 `ignored_states` | 同左 |

`possible-positive` 与仓库既有评分器 `Sys/Score/evaluate_propagation.py` 一致（那里本就写作
`membership in {"definite","possible"}`），使 RQ1 的历史数字可比；`strict` 保留旧 RQ1 行为。
两种口径都不解释 `direction_status`（词表仅 `likely` / `unresolved`），一律按行内 `from→to`。
口径写入 `run.json` 的 `arguments`、`summary.json` 的 `label_policies` 与 `table.md` 表头；
`labels.canonical.json` 的 `conversion` 块记录 `policy` / `treated_as_positive` / `ignored_states`。
`possible` 是标注强度，不是已核实的物理关系；该口径改变了评分语义，换口径重评分必须传相同的
`--label-policy`（当前 `evaluate` 不校验 `labels_hash` 是否与首次运行一致）。

```bash
bash scripts/run_rq1.sh --label-policy strict
export PINGMESH_RQ1_LABEL_POLICY=strict
```

**参考图完整性由 `--label-completeness` 决定（默认 `as-declared`）：**

| 取值 | `graph_complete` | 后果 |
|---|---|---|
| `as-declared`（默认） | 取标注文件的 `graph_complete`；缺失即 false | 部分参考不扩展 SHD，`shd_status=partial_reference` |
| `all-complete` | **一律视为完整图** | SHD-1 可算；但未标注的设备对全部算作已确认负例 |

`all-complete` 是一个**假设而非观测**：它会让评分域扩张到整个设备对全集
（如 11 台设备 → 55 个无序对 / 110 个有向槽位），并据此把 SHD 算出来。
只有在确实认为该参考枚举了全部关系时才可用；`annotation_complete_scope` 为 false、
`annotator_confidence` 偏低的标注即使有若干 `possible` 边也不构成完整性声明。
该假设**不写回标注文件**，只记录在 `labels.canonical.json` 的
`conversion.graph_complete_source`（`declared` / `assumed_all_complete` / `undeclared`），
并在 `summary.json` 的 `label_completeness` 与 `table.md` 表头披露。
完全没有 `edges`/`dd_edges` 键的案例仍记为 unavailable，不会被当成"零边的完整图"。

```bash
bash scripts/run_rq1.sh --label-completeness all-complete
export PINGMESH_RQ1_LABEL_COMPLETENESS=all-complete
```

`as-declared` 下只有显式 `graph_complete=true` 且没有未决关系时才计算完整 SHD；
不默认把旧标签视为完整图（这是 graph-eval-v2 的既有约定：部分标签暂不扩展 SHD）。
多根／未知根、冲突标注、acceptable_hypotheses 会明确报错，不取首根或自行解释。
仍兼容 `--labels canonical.json`；canonical 标签已解析完毕，两个口径都不适用（记为 `canonical`）。

无需事先准备分折文件：脚本自动冻结端点／告警上下文分组及清单到输出目录的 `folds.json`。
**自动分组未经人工核实，仅用于探索性推断；不输出事故独立性 CI，NEC 不在这种分组上训练。**
其余四方法继续运行，NEC 记为 `input_ineligible`，退出码为 2，表格和预测仍保留。
要运行完整五方法，在 common.sh 中配置已有的核实分组或 manifest：

```bash
export PINGMESH_RQ1_GROUPS=/server/path/reviewed_groups.json
# 或 export PINGMESH_RQ1_MANIFEST=/server/path/folds.json
bash scripts/run_rq1.sh
```

`reviewed_groups.json` 是 `case_id -> 真实事故ID`；脚本自动分折，不需要手工生成 folds。
少于两个独立组时不能训练 NEC，不会用测试组补训练样本。
若采用 Shared，需要在 common.sh 配置 `PINGMESH_RQ1_ROOTS`（冻结 OOF 起点文件），
或使用 `--condition shared --roots ...`。传入 roots 且没有显式 `--condition` 时自动选 Shared。
已配置路径还可用原有 `--inputs/--labels/--output/--manifest/--config` 参数覆盖。

## 1. 方法与适配边界

| 表中名称 | 实际实现 | 训练／拟合协议 |
|---|---|---|
| TimeOrder | 两个原始拓扑邻接设备的首个有时间告警／日志定向；并列保留未定向，缺时间不补方向 | 无训练；时间差阈值事前固定 |
| NetEventCause | 仓库 `NetEventCauseDevice` 的 ODE 机制复现、事件归因、设备映射 | 每折仅训练组拟合、验证组选择；测试组只推断 |
| PCMCI | Tigramite **run_pcmci** + ParCorr，设备告警／日志计数序列，默认 log1p | 各事故窗口独立无标签拟合；tau_min=1，不输出同时刻关系 |
| THP | Cai et al. **Topological Hawkes Processes**，gCastle **TTPM** + 显式设备适配 | 各事故窗口独立无标签拟合事件类型结构；不是 Transformer Hawkes Process |
| Ours | 当前 `reconstruct_propagation` 的确定性 P0，公共观测输入、固定起点 | 不重训 Stage 1，不访问外部 LLM，不加载监督边分类 checkpoint |

Ours 调用现有 M1/M2 代码，不另写替代算法。公共白名单保留设备、原始邻接、
告警／日志和端点上下文；设备名、端口等未进入公共输入的字段不被 Ours 额外读取。
因此这里是 **P0-common-input-fixed-root**，不是历史完整系统结果的原样复现。

THP 依据：

- [论文全文](https://arxiv.org/pdf/2105.10884)，§III–IV：物理节点拓扑与事件类型因果图是两个不同对象。
- [gCastle TTPM 接口](https://gcastle.readthedocs.io/en/latest/castle/castle.algorithms.html#castle.algorithms.TTPM)。
- [上游实现](https://github.com/huawei-noah/trustworthyAI/blob/master/gcastle/castle/algorithms/ttpm/ttpm.py)：指数核、EM、BIC/AIC 结构搜索。这里调用该实现，不以共现规则冒充 THP。
- [Tigramite 官方 PCMCI 接口](https://jakobrunge.github.io/tigramite/#tigramite.pcmci.PCMCI.run_pcmci)。

THP 输入三列 `event=告警/日志类型`、`timestamp=相对秒`、`node=设备索引`；
topology_matrix 为原始物理邻接，默认 max_hop=1，不能设为 0 后仍声称用了跨节点拓扑。
类型图的 i→j 加上相邻设备 u/v 上实际发生的严格先后事件、以及最大时间差，映射为 u→v。
分数是支持的目标事件／类型对数量，**不是因果概率或上游估计的激励系数**。
TTPM 固定对角线为 1；适配器排除它，避免凭固定自激项推断同类型跨设备传播。
该限制会漏掉同类型传播，应在论文说明。保留类型矩阵、类型顺序、证据 ID 和原生设备边。
上游按首末事件计算暴露时长，并在学习时使用有事件节点的拓扑子图；本适配没有暗改这些行为。
设备／事件／类型超过预算时记录不适用，不根据测试标签筛选或静默截断。

NEC 延续仓库的“机制复现 + 设备适配”名称，不声称精确作者代码复现。
PCMCI 使用 ParCorr 处理计数变换是迁移近似；不把它叫 PCMCI+。

## 2. 服务器环境

在项目根目录、已有兼容 PyTorch 的 Python 3.10/3.11 独立环境中：

**使用本目录的 `Baseline/RQ1/requirements.txt`，不要安装 `Baseline/requirements-repro.txt`。**
后者是另一套 Windows/Python 3.12 环境快照，锁定的 NetworkX 3.6.1、NumPy 2.5.3、
SciPy 1.18.1 等版本与 RQ1 的 Python 3.10 不兼容，仅替换其中一个包不能解决整份环境冲突。
RQ1 将 NetworkX 固定为支持 Python 3.10 的 3.4.2。

```bash
python -m pip install -r Baseline/RQ1/requirements.txt
python -m pip freeze > /path/to/rq1-environment.txt
python -m Baseline.RQ1 --help
```

THP/PCMCI 使用 CPU。NEC 默认 CPU，`--device cuda:0` 等由服务器已有 torch 构建决定；
不自动替换 Ascend/PyTorch。依赖范围是兼容性约束，尚不是经过服务器验证的锁文件。

## 3. 准备输入、标签和事故划分

输入复用 `Baseline.common`：

- 原始 `full_link`／`task_topo` JSON，或包含 `*pingmesh*.json` 的目录；
- 处理后的案例目录，需要 `info.json`、节点文件，以及来源为 `raw_task_topo` 的 `topology_context.json`；
- 规范化 `incidents.json` / JSONL。

不从真根推导传播图，也不删除未在标签中出现的设备或边；`possible` 的处理见上文 `--label-policy`。
规范化输入没有集合覆盖信息时，PCMCI 默认标记 `input_ineligible`，不会填零假装完整采样。
若有真实采集覆盖资料，应写入每个规范化事故的 `observation_coverage`；只有已经验证整个窗口完整采集，
才能设置 `{"complete": true}`。配置中的 `require_coverage=false` 仅可作为另行披露的计数假设实验。

```bash
python -m Baseline.common prepare \
  --inputs /server/data/raw/pingmesh_labeled \
  --output /server/rq1/inputs.json

# groups.json 必须由真实事故归属核实，不能临时按导出文件当独立事故。
python -m Baseline.common manifest \
  --inputs /server/rq1/inputs.json \
  --groups /server/rq1/groups.json \
  --folds 5 --seed 20260920 \
  --output /server/rq1/folds.json
```

`groups.json` 格式为 `{"case-001":"incident-001", "case-002":"incident-001", ...}`。
同一事故的多个窗口不得跨训练、验证或测试。所有方法使用相同清单、窗口和分折。
改变输入、采集覆盖或窗口之后应重建冻结 manifest。

完整标签 `labels.json` 示例：

```json
{"labels": [{
  "case_id": "case-001",
  "root_status": "confirmed",
  "root_device": "A",
  "graph_complete": true,
  "positive_nodes": ["A", "B", "C"],
  "positive_edges": [["A", "B"], ["B", "C"]]
}]}
```

部分标签用 `graph_complete=false`，配 `known_edge_mask`、`known_node_mask`。
`known_edge_mask=[["A","B"]]` 只确认 A→B 存在与否，不自动确认反向关系。
如仅确认相邻、方向未知，使用 `positive_adjacencies=[["A","B"]]` 和
`known_adjacency_mask=[["A","B"]]`；`positive_edges=[]`、`known_edge_mask=[]`。
`allowed_edges` 涉及的整对关系中性排除，不能与确认正例同时标注。
无图标签的案例仍保留一条 `case_id` 标签记录，不填 `positive_edges`，记为 unavailable。
标签必须完整覆盖输入清单；未知设备、非原始邻接正边、循环参考图会报错，不能通过静默删标签解决。

## 4. 正式运行

**Shared（可选；零参数入口默认 Oracle）**：使用同一份冻结 OOF 预测起点。`roots.json`：

```json
{
  "manifest_hash": "folds.json 中的 manifest_hash",
  "source": "Stage-1 OOF run ID / checkpoint / 生成协议",
  "roots": {"case-001": "A", "case-002": "B"}
}
```

脚本核对事故清单、输入指纹、分折和起点域。`source` 是可审计说明，
不代表脚本能证明外部起点模型确实没有泄漏；应保留其 OOF 生成记录。

```bash
# 先检查输入合同，不训练、不写实验产物。
bash scripts/run_rq1.sh run \
  --inputs /server/rq1/inputs.json --labels /server/rq1/labels.json \
  --manifest /server/rq1/folds.json --roots /server/rq1/roots.json \
  --config configs/baselines/rq1.json --output /server/results/rq1_shared_01 \
  --dry-run

# 去掉 --dry-run 即正式运行。
bash scripts/run_rq1.sh run \
  --inputs /server/rq1/inputs.json --labels /server/rq1/labels.json \
  --manifest /server/rq1/folds.json --roots /server/rq1/roots.json \
  --config configs/baselines/rq1.json --output /server/results/rq1_shared_01
```

**Oracle**：不传 `--roots`，增加 `--condition oracle`。只在包装层提取每例明确确认的单根，
方法推断仍不接收传播标签。结果必须标明 Oracle，不能与 Shared 混表。
本 RQ1 入口不包含各方法自身起点的端到端 Full 实验。

可用 `--methods timeorder ours` 先跑轻量方法；完整表运行时保留默认五方法。
原始目录输入可设 `--before-seconds` / `--after-seconds`，它们必须与 manifest 一致；
规范化输入以自身显式窗口为准。

`--output` 必须是新目录，避免覆盖服务器已有结果。
退出码 0 表示全部方法／案例成功，2 表示已生成表格但存在失败／不适用／弃权；
输入合同错误会直接中止。依赖缺失保留失败记录，不冒充成功空图。
中断前的逐案例 JSON 和逐折汇总保留；当前入口不提供自动续跑。

## 5. 输出与评价口径

- `table.md` / `table.csv`：直接使用七列指标；附案例和失败数量。
- `summary.json`：逐案例评分、每项有效分母、按事故组 bootstrap 的 95% CI。
- `predictions.json`：每种方法／每例恰好一条记录，含失败、原生图、设备图、配置、时间。
- `cases/<method>/*.json`：逐案例持久化，文件名为 case_id 哈希。
- `checkpoints/nec-fold-*.pt`：每折 NEC checkpoint，只用于对应测试折。
- `run.json`：输入／标签／配置／起点指纹、源码 SHA-256、Git 状态、运行环境和状态。
- `folds.json` / `labels.canonical.json` / `roots.json`：本次使用的冻结分折、规范化 GT 和起点。

每个条件同时给两种图：

1. `rooted`（默认主表）：统一现有 baseline adapter；删除入根边、非物理边、环、根不可达边，
   不给外部方法使用本文 M1/M2 解码器。该 adapter 不猜未定向边，因此会删除它们；删除原因均保存。
2. `topology`（伴随表）：仅事件→设备映射、去自环、原始邻接约束、重复合并，
   保留未定向和双向证据，不做根可达／去环。用来检查后处理对结果的影响。

`--graph-view topology` 可调整表格主次；不会影响推断与另一张表。
Ours 的 `topology` 图仍然是自身固定根解码结果，不是 Ours 的 root-independent M1 图。

Adj 比较无序设备对。AH 比较所有已判定边上的“设备对 + 箭头端点”，不局限于共同邻接；
未定向边只命中 Adj，不自动产生箭头 TP。部分标签的 Adj 与 AH 分别建立掩码；
仅当一个方向为正或两个方向都已判断，才能从有向标签推导邻接是否已知。

SHD 只用于完整参考。简单 DAG 增边、删边、反向各计 1；topology 表的混合图扩展明确为：
同一无序对上的未定向／双箭头状态改为参考方向也计 1，不暗中补方向。
`--label-completeness all-complete` 会把部分参考当作完整参考来算 SHD，此时表中的 SHD
是**在该完整性假设下**的距离，不等于已验证完整标注上的 SHD-1；引用时必须连同
`label_completeness` 一起写明。若一个待汇总子集存在失败，主表 SHD 为 N/A，
成功样本 SHD 仅在 JSON 诊断中保留。
PRF 中成功的双方空图为 1，失败始终为 0；无可判定关系不产生该项指标。

完整和部分参考分别成表。先对同组窗口取均值，再对组取宏平均；自动组不声称为核实事故。
`all` 保留所有失败；`common_success` 使用所有方法均成功的整事故组共同子集，
一组中任一方法任一窗口失败，整组退出共同成功表，不制造方法间不同分母。
共同成功表仅是诊断，不能代替 all 表或事前共同适用性审计。
部分参考、多个窗口具有不同标注完整度时，指标只在各自已判定窗口内平均，并披露分母。

离线重评分（无需重新拟合）：

```bash
python -m Baseline.RQ1 evaluate \
  --inputs /server/rq1/inputs.json --labels /server/rq1/labels.json \
  --manifest /server/rq1/folds.json --roots /server/rq1/roots.json \
  --predictions /server/results/rq1_shared_01/predictions.json \
  --output /server/results/rq1_shared_rescore_01
```

若预测只运行部分方法，重评分传相同 `--methods`；Oracle 重评分同样传 `--condition oracle`。

## 6. 服务器验证

```bash
# 无第三方依赖的目录、GT 转换、默认路径、轻量端到端与重评分测试。
python -m unittest Baseline.RQ1.tests.test_prepare -v
python -m unittest Baseline.RQ1.tests.test_event_identity -v
python -m unittest Baseline.RQ1.tests.test_coverage -v

# 单元测试、实际 Ours 入口、轻量端到端、标签隔离、分折隔离和失败记账。
python -m pytest Baseline/RQ1/tests -q

# 额外执行真实 Tigramite 和 gCastle 小规模数值接口检查。
RQ1_NUMERICAL_SMOKE=1 python -m pytest Baseline/RQ1/tests -q
```

2026-09-21：23 项 unittest 全通过（含 9 项重复告警 ID、6 项覆盖策略回归测试），本地两个示例只读加载通过。
完整 pytest 与数值后端测试仍待服务器执行。测试数据是合成接口样例，不是论文精度证据；
正式实验前请在目标环境先跑验证，依赖／数值错误会保留为失败，不回退到替代算法。

2026-09-21（Windows 本地 CPU 验证环境 `tmp/baselines-venv`）：本次首次在真实 case 上执行。
`pytest Baseline/RQ1/tests -q` 54 passed（含上述数值后端测试）；`RQ1_NUMERICAL_SMOKE=1` 同样通过。
case `8294294` 五方法端到端跑通（Oracle 根，`--pcmci-coverage record-count`）：
TimeOrder / PCMCI / THP / Ours 为 `ok`，NEC 因只有 1 个未核实分组记为 `input_ineligible`（退出码 2）。
`--label-policy strict` 的结果与本次改动前逐字段一致（回归保护）。
该 case 的传播 GT 无 `definite` 边且 `annotation_complete_scope` 四项全 false，
默认 `--label-completeness as-declared` 下 `shd_status=partial_reference`、SHD 为 N/A。
加 `--label-completeness all-complete` 后评分域扩为 55 对 / 110 槽位，SHD 可算：
TimeOrder 2、THP 2、PCMCI 0、Ours 0，NEC 因预测失败扣留。
**该 SHD 建立在"此参考为完整图"的假设上，不是已验证完整标注上的 SHD-1。**
`pytest Baseline/RQ1/tests -q` 60 passed。
**n=1、自动分组未核实、无自助 CI，只能作为管线自检，不构成论文精度证据。**
