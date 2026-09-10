# SkyNet-inspired Alert Attribution Voting

本实现是受 SkyNet 启发的**设备根因投票适配基线**，支持 Root 排名。不支持传播图、Oracle-Graph、自主 Full-Graph，也不实现 SkyNet 的完整告警聚合、定位和影响评价系统。

论文来源：Yang et al., *SkyNet: Analyzing Alert Flooding from Severe Network Failures in Large Cloud Infrastructures*, SIGCOMM 2025，[作者 PDF](https://ennanzhai.github.io/pub/sigcomm25-skynet.pdf) §7.1；已核对仓库本地全文 `docs/papers/SkyNet_ Analyzing Alert Flooding from Severe Network Failures in Large Cloud Infrastructures.txt` 的 §7.1（约 791–807 行）。该节描述设备/链路告警给自身及连接的链路/设备投票，用于可视化和定位，没有公布完整的字段映射算法。本目录为独立实现，无外部作者代码依赖。

| 原始机制 | 当前输入 | 保留内容 | 本项目适配 / 缺失 |
|---|---|---|---|
| 设备与链路告警投票 | 公共设备、物理链路、事件来源和归属 | 由告警证据产生票数 | 仅排名设备；每事件每设备一票；不是完整 SkyNet |
| 告警自身及连接实体 | `device_id`、`related_device_ids`、`link_endpoints` | 自身和明确连接的设备 | 默认不推断全部邻居；字段未解析则不猜测 |
| 图上投票高亮 | 每设备票数 | 保留票数及其证据 | 不产生因果图；最高票根排名是本项目任务映射 |
| 未公开的实现细节 | 无作者投票模块 | 按描述独立实现 | 权重、去重、平分及缺失规则均为预先明确的工程选择 |

## 告警归属表（默认配置）

`alarm_type` 在此表示可观察的**归属字段形状**。不按告警名称关键词或自由文本猜测接口、对端或故障类别。任何 `event_type` 均采用相同的单位权重。

| alarm_type / 字段形状 | V(e) 规则 | 必需字段 | 缺失或不成立行为 |
|---|---|---|---|
| 设备告警 | 投所属设备 | `source=alarm/alert`、有效 `device_id` | 无所属设备则记录原因；仍可独立解析明确链路端点 |
| 明确对端告警 | 所属设备，加每个**直接物理相邻**的明确对端 | `device_id`、`related_device_ids: list[str]`、对应 `physical_links` | 未知对端、未连通、缺少所属设备均不扩展，逐项记原因 |
| 明确链路告警 | 两个直接物理连接的有效端点；与所属设备票取集合并集 | `link_endpoints: [u,v]`、真实 `physical_links` | 端点不足、多于两个、自环、未知或不连通时忽略链路归属，保留有效自身归属 |
| 自身、对端及链路字段同时存在 | 合并以上已经确认的归属集合 | 对应字段均各自满足条件 | 同设备仍最多一票，不因多条归属或多重边加权 |
| 接口名仅在消息中、未知接口 | 不从文本扩大集合 | 无可核验对端字段 | 保留有效设备自身票，报告未解析的显式字段 |
| 普通日志或未知来源 | 默认不投票 | 来源须经公共预处理明确归类为告警 | `source_not_enabled`；正文中出现“alarm”不会改归类 |

`device_id` 必须表示**告警所属设备**，不能填仅负责转发/采集日志的设备。若链路告警仅有采集器身份，公共层应将 `device_id` 置空并保留真正的 `link_endpoints`。若三者同时存在，本方法按已声明归属求并集，不能反向猜测采集器语义。

同一事件 `event_id` 非空时按 ID 去重；无 ID 时按固定字段的 SHA-256 签名去重：`device_id/event_type/event_time/record_time/severity/message/source/related_device_ids/link_endpoints`。来源大小写归一，对端/端点集合排序去重。签名不包含标签、诊断分数或额外字段。不进行时间分箱或相近时间合并。不同事件 ID 即使内容相同也各计一次；同一 ID 内容冲突时保留输入中第一条并记录 `conflicting_duplicate`。公共层必须保证事件 ID 在案例内标识同一个真实事件。只有允许来源参与去重，避免普通日志占用告警 ID。

所有公共候选设备均保留，零票设备得 0 分。分数是**整数单位票数，不是概率**。按票数降序、设备 ID 的 Unicode 字典序升序排序。无有效票时返回 `abstained` 并保留全部零票设备，评测器应按失败/弃权处理，不能将平分首项当有效预测；无候选设备返回 `input_ineligible`。

## 接口与运行

运行时仅依赖 Python 标准库（Python 3.10+），不训练、不访问网络或模型，不读取标签。公共输入版本 `baseline-incident-v1`；只消费 `case_id/devices/physical_links/events` 中上述字段。窗口截止和来源字段转换由公共输入层统一负责，本方法不自行裁窗。

```python
from Baseline.SkyNetVoting import SkyNetVoting, predict_root

prediction = predict_root(incident)
prediction = SkyNetVoting({"mode": "attribution", "include_logs": False}).predict_root(incident)
```

默认配置位于 `default_config.json`。从仓库根目录执行：

```powershell
python -m Baseline.SkyNetVoting --input input.json --output predictions.json
python -m Baseline.SkyNetVoting --input input.jsonl --output predictions.json --config Baseline/SkyNetVoting/default_config.json
python -m pytest tests/test_skynet_voting.py -q
```

CLI 使用公共 `Baseline.common.io.load_incidents` 的观测白名单及 `dump_json`；不要把标签文件当作 `--input`。

输出包含每个输入事件的处理结果 `event_decisions`、每票 `vote_evidence`、来源事件 ID、物理连接证明、映射失败原因、被忽略告警、零票设备、平分组及设备平分率、输入规模、版本、参数和单例耗时。输入事件无 ID 时以输入下标和签名追溯。

明确分名的可选扩展：

- `mode=one_hop`：命名为 `SkyNet-inspired one-hop voting`。将默认已解析归属集合中的每个设备扩展一次至全部物理一跳邻居；不递归扩展。此扩展属于本项目，不冒充论文公布的完整算法。
- `include_logs=true`：名称追加 `(alerts+logs adapt)`，额外接收 `source=log/syslog`；这是独立实验。默认告警来源固定为 `alarm/alert`，不因配置任意改名日志。

## 手算与验收

物理图：`A—B—C`。三个告警：e1 属于 A；e2 属于 B，明确对端 A；e3 属于 C，明确链路 B—C。

| 事件 | V(e) | A 票 | B 票 | C 票 |
|---|---|---|---|---|
| e1 | A | 1 | 0 | 0 |
| e2 | A、B | 1 | 1 | 0 |
| e3 | B、C | 0 | 1 | 1 |
| 合计 | | 2 | 2 | 1 |

排名为 A、B、C；前两名平分，设备平分率为 2/3。A 的自身告警不会默认给 B 加票。多重边和重复显式归属不增加权重。

`tests/test_skynet_voting.py` 覆盖逐票手算、ID/签名去重、不同 ID/时间真实重复、拓扑多重边、未知接口/非相邻对端、无归属但有效链路、标签与诊断分数无关、输入不变、无票弃权、全设备保留、扩展分名及仅一次邻居扩展、冲突重复记录、空设备输入。真实全量数据结果须由公共运行器产生；本目录没有预填论文指标。
