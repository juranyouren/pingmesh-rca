# RQ1：设备传播图恢复

入口：`python -m Baseline.RQ1 run`，或在服务器执行 `bash scripts/run_rq1.sh run`。
默认方法：TimeOrder、NetEventCause、PCMCI、THP、Ours；THP 已加入七指标表。
本次交付脚本与服务器验证用例，**未执行服务器实验，也未生成真实结果**。

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

不自动读取旧传播标签，不把 `possible` 推成正例，也不从真根推导传播图。
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

**Shared（默认）**：使用同一份冻结 OOF 预测起点。`roots.json`：

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
若一个待汇总子集存在失败，主表 SHD 为 N/A，成功样本 SHD 仅在 JSON 诊断中保留。
PRF 中成功的双方空图为 1，失败始终为 0；无可判定关系不产生该项指标。

完整和部分参考分别成表。默认先对同事故窗口取均值，再对事故取宏平均。
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
# 单元测试、实际 Ours 入口、轻量端到端、标签隔离、分折隔离和失败记账。
python -m pytest Baseline/RQ1/tests -q

# 额外执行真实 Tigramite 和 gCastle 小规模数值接口检查。
RQ1_NUMERICAL_SMOKE=1 python -m pytest Baseline/RQ1/tests -q
```

测试数据是合成接口样例，不是论文精度证据。Python 与 JSON 已通过静态语法检查，当前未在本地或服务器执行上述测试；
正式实验前请在目标环境先跑验证，依赖／数值错误会保留为失败，不回退到替代算法。
