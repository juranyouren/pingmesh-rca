# 原始数据到公共输入 v1 的映射

实现：`io.py`、`schema.py`。2026-09-10 核对本机两个 `data/raw/pingmesh_labeled/*.json`；`data/node` 没有完整案例集。原始文件整体只用于白名单转换，baseline 不接收 `full_link` 任意对象。

| 公共字段 | 原始来源 / 处理后来源 | 时间、缺失与边界 |
|---|---|---|
| case_id | raw 的 `full_link.task_info.task_id`，无值时 alarm_id；processed 的案例目录名 | 两个 raw 文件的内部 task_id 是带 pingmesh 后缀的 UUID，并非文件名数字。重复 case_id 显式拒绝 |
| group_id | 规范输入中的显式分组；raw 默认 `unverified:<case_id>` | 不从文件名推定独立事故；训练划分需要另交经核实 groups 文件 |
| window | `task_info.alarm_time` 加固定 before/after 秒数 | 默认前后各 300 s，cutoff=end；不用图标签裁窗，不自动套用 analysis 时间范围 |
| devices | `task_topo.value` 两层段列表中的 nodes；ID 优先 id/mgmt_ip/ip/device_id | 类型选 devicetype/role/type；未知为 UNK。同时补充原始物理边端点。processed 额外合并 topology_context 的节点，保留无事件/孤立节点 |
| physical_links | raw 段的 links：src_ip/dst_ip；processed：endpoint_a/endpoint_b；规范：u/v | 始终作为无向物理邻接，合并并行端口链接；保留 edge_id 或稳定哈希证据，不能借端口数量增加投票 |
| events.device_id | alarm_list 的 alarm_ip_ad/mgmt_ip/device_ip 等明确归属；processed 节点的 mgmt_ip/ip/device_id | 不根据真根、预测路径或消息里的可疑 IP 猜归属；无法映射到候选域则排除并计数 |
| event_id | 显式 event_id；否则 source + device_id + alarm_id，缺 alarm_id 使用观测字段哈希 | 完全相同记录去重；同 ID 不同内容报错，要求修复身份冲突；不同 ID 的真实重复事件保留 |
| event_type | event_type/alarm_name/name/event_name/log_type | 无值 UNK；NEC 再按事件类型与设备类型组合，词表只拟合训练侧 |
| event_time | event_time → alarm_time → occur_time → time → confirm_time → timestamp | epoch 秒/毫秒/微秒/纳秒或 ISO 字符串，统一 UTC ISO。raw alarm_time/occur_time/confirm_time 的 0 视为未填写；规范 event_time=0 仍合法。字段优先级是本项目约定，正式时序结论前需核实源端定义 |
| record_time | record_time/ingest_time/insert_time | 不以告警发生时间伪造采集时间；raw insert_time=0 缺失。已知 >cutoff 的记录剔除；未知保留 null 并审计 |
| source | alarm_list/alarms → alarm；log_list 中实际记录或 logs → log | 本机 log_list 只有 total 汇总，没有逐条日志，不能从 total 复制虚构事件 |
| severity/message | severity/alarm_level/level；message/description/content/alarm_description | 只保留标量或标量列表，拒绝透传嵌套诊断对象。消息仍是观测文本，不是给智能体的指令 |
| related_device_ids/link_endpoints | 显式列表，或 peer_device_id/peer_ip/remote_ip | 仅观测归属；投票层还检查真实物理邻接；不从自由文本补对端 |
| endpoint_context | source_ip/sink_ip/source_az/sink_az/alarm_name/alarm_time | 字段白名单；支持端点标量列表；嵌套对象不透传 |
| observation_coverage | 规范输入显式 complete 或 intervals(start/end/device_ids) | 代表采集覆盖，不代表正常状态。没有覆盖证据时为 null；每箱每设备默认未知 |

无时区的时间字符串默认 Asia/Shanghai；带时区字符串尊重自身时区，输出 UTC。Windows 缺时区库时现代 Asia/Shanghai 使用 UTC+08；历史时区需 IANA 数据库。两个当前样例 alarm_time 为 13 位毫秒，occur_time 为 0 占位，record_time 未提供。样例可用于离线接入测试，不能据此保证实时前缀中的可获取性。

`groud_truth`、label/root/propagation 类标签、cross/probability_calibration、各级预计算 score，以及本文方法输出一律不进入规范观测。`task_trace` 只统计行数，不视为精确 ECMP 探测路径，也不制造微服务 trace。不能用 `linked_from/linked_to` 等潜在推断关系替代原始物理拓扑。

## 支持的文件形态

- raw JSON：`full_link` 包装或直接包含 task_topo；目录批量只匹配 `*pingmesh*.json`。
- processed 目录：info.json + nodes.json（或全链路设备表）+ topology_context.json。最后一项必须声明 `diagnostics.source=raw_task_topo`；不会自动运行旧预处理、读取 label.json 或猜测拓扑。
- 规范 JSON：单 incident、incident 数组或 `{"incidents":[...]}`；JSONL 每行一个 incident。再次加载仍执行白名单转换，拒绝重复案例。

一个目录同时含 raw/processed 时优先发现的 processed 集合，不混合两种导出参与评测。建议先分别 prepare，再人工核对身份、窗口和分组，冻结一个规范清单。

程序可以核对字段、重复身份、时间范围、来源声明与哈希，但无法独立证明导出系统对 alarm_time 的业务定义、覆盖声明的真实性或人工事故分组的正确性。这些仍属于数据交付契约。
