# BiAn 三流程本地模型适配

方法标识：`BiAn-three-pipeline-adapt-local-no-history`，版本 `0.1.0`。
论文依据是 SIGCOMM 2025 *Towards LLM-Based Failure Localization in Production-Scale Networks* §4.1–4.3、Appendix A；本地全文位于 [`docs/papers/Towards LLM-Based Failure Localization in Production-Scale Networks.txt`](../../docs/papers/Towards%20LLM-Based%20Failure%20Localization%20in%20Production-Scale%20Networks.txt)。

本实现支持 **Root 设备排序**。不输出设备传播图，不支持 Oracle-Graph 或 Full-Graph。不修改旧 `Baseline/BiAn/bian_pipe1.py`，也不使用 P0 / PC-STGR 输出、测试标签或训练历史知识。

## 当前交付状态

- 三流程、全部候选设备、7 类异常分析、Top-p 和 3 次 Rank of Ranks 已实现。
- 26 项契约单元测试通过。测试通过注入假的 HTTP 响应验证接口、证据与失败处理，**不是模型实验或 BiAn 准确率结果**。
- 已用公开构造的合成观测尝试真实 `127.0.0.1:8000/v1` 后端；后端不可用，结果为 `runtime_failure`，排名为空。记录见 [`validation/local_backend_smoke.json`](validation/local_backend_smoke.json)。
- 未进行正式 LLM 评测，未产生设备根准确率。后续须配置实际模型并冻结设置再运行。仓库两个原始事故不等于正式测试集。

## 原机制与当前实现

| 论文模块 | 当前保留的机制 | 适配与缺失 |
|---|---|---|
| 11 个监控来源的摘要 | 对每个设备、每种真实 `source` 分开生成摘要，事件 ID 可追溯 | 公共输入通常只有 alarm/log，不能冒充 11 种专有监控器 |
| 7 个异常场景分析 | Device Down、Congestion、Traffic Drop、Flapping、Network Changes、Syslog Surge、Alarm Count 分别调用；每批次返回独立设备结果 | 缺专有 SOP、微调模型与流量基线；场景指导是明确写出的保守适配提示，不是作者完整 SOP |
| 初始联合评分 | 模型基于全设备异常报告，返回所有候选的分数 | 不沿用论文上游经验六设备限制；设备无事件不等于健康；整个事故无事件则 `input_ineligible` |
| Top-p 内部筛选 | 初评分先做 softmax，再按累计质量选取最小前缀 | 默认 `0.9` 是本项目待冻结工程设置，不能称论文默认；保留筛除名单，由外部评测器计算真根覆盖损失 |
| 嫌疑设备拓扑摘要 | 对每对嫌疑设备枚举所有无向最短路径，移除内部经过其他嫌疑设备的路径，合并保留路径；模型解释空间证据 | 无可靠原设备组信息，禁用“非嫌疑同组节点合并”；类型、跳数都不充当设备组；路径不作为实测探测路径或传播图 |
| 全局时间线 | 全候选事件按事件时间排列；保留记录时间、并列时间与未知时间；分批进行时间证据摘要 | 使用统一每设备事件预算，超过部分逐 ID 披露；未知事件时间不借记录时间伪造 |
| 三流程联合推断 | 异常报告、真实物理拓扑、拓扑报告、全局时间线摘要、白名单端点上下文进入同一提示 | 早停关闭，成功案例必须实际执行三条流程 |
| Rank of Ranks | 默认独立执行联合推断 3 次，按平均名次汇总 | 同分在轮内取平均名次，最终同均值按初排、设备 ID 决定顺序；单次配置有独立 `-single-round-ablation` 方法名 |
| 持续知识演化 | 未启用 | 没有训练历史和操作员反馈，不进行测试答案 reflection 或测试期知识更新 |

模块属于按论文实现的迁移版，不是获得作者专有监控、SOP 与模型后的逐项等价复现。

## 使用

仅需 Python 标准库，测试环境为仓库 `tmp/baselines-venv/Scripts/python.exe`（Python 3.12）。没有 OpenAI SDK、PyTorch 或 `requests` 依赖。生产运行没有 `mock` 选项。

从仓库根目录运行，先在配置中填写真实本地模型标识；`local-model` 只是部署占位符，不会自动选择模型：

```powershell
$env:BIAN_MODEL = '实际本地服务公开的模型标识'
$env:BIAN_BASE_URL = 'http://127.0.0.1:8000/v1'
& 'tmp/baselines-venv/Scripts/python.exe' -m Baseline.BiAnAdapt --synthetic-smoke --config 'Baseline/BiAnAdapt/config.json' --output 'Baseline/BiAnAdapt/validation/configured_model_smoke.json'
```

真实输入使用公共加载器，同一命令处理公共 JSON/JSONL 或支持的原始输入：

```powershell
& 'tmp/baselines-venv/Scripts/python.exe' -m Baseline.BiAnAdapt --input 'path/to/normalized_incidents.json' --config 'Baseline/BiAnAdapt/config.json' --output 'path/to/bian_predictions.json'
```

API 使用：

```python
from Baseline.BiAnAdapt import BiAnAdapt, BiAnConfig

model = BiAnAdapt(BiAnConfig.from_file("Baseline/BiAnAdapt/config.json"))
prediction = model.predict_root(incident)
```

`predict_root(incident)` 可直接接公共 `baseline-incident-v1` 字典；模块级 `predict_root` 使用环境配置。公共 runner 可直接构造 `BiAnAdapt` 复用同一接口。没有 `fit` 阶段和隐式跨事故状态。

只允许 loopback 模型端点，禁用系统 HTTP 代理与重定向；私网机器的本地模型可先由操作者建立 loopback 隧道。不会根据 URL 自动访问外部模型服务。服务需要密钥时只读取配置 `api_key_env` 指定的环境变量，默认 `BIAN_API_KEY`，不保存密钥。`BIAN_BASE_URL` / `BIAN_MODEL` 优先于配置文件，也兼容 `OPENAI_BASE_URL` / `PINGMESH_MODEL_PATH`；不检查或输出完整环境。

默认请求包含 `model/temperature/top_p/max_tokens/seed/response_format`。后端必须接受 OpenAI-compatible `POST /v1/chat/completions` 和 JSON object 输出。后端若不支持这些参数，记录真实失败，不自动删参数、换模型或回退到规则打分。模型输出不合法时按固定重试次数重新请求完整 JSON，失败轮次同样保存。

## 输入与证据边界

`structure.observable_input` 重新建立白名单对象：设备只取 `id/type`；事件只取事件 ID、设备、类型、事件/记录时间、严重性、消息与来源，以及明确的 `related_device_ids/link_endpoints`；物理图只取端点和来源 ID。消息按固定字符预算裁剪并记录事件 ID，未知字段、label、score、任意 nested dict 不透传。

端点只保留 `source_ip/sink_ip/source_az/sink_az/alarm_name/alarm_time/trigger_time/analysis_from_time/analysis_to_time` 的标量或标量列表。原始 source/sink 为数组时保留数组；列表中的任意对象剔除。`observation_coverage` 不盲目传递，第一版保守地声明完整覆盖未知。

普通 Root 接口拒绝无效窗口、窗口外已知事件时间及截止时间后才记录的事件；公共加载器负责原始输入过滤。未知或不可解析的事件时间以未知值保留，解析失败有记录，绝不抖动或生成时间。全设备候选不随标签与事件量缩减；每设备事件预算按事件时间和 ID 取固定前缀。每一步返回的证据 ID 必须属于该步骤实际收到的事件证据，不能凭空引入其他事故或同事故尚未展示的证据。

历史知识、派生诊断分数与原始整包 `full_link` 都不进入提示。提示将日志和上游摘要声明为不可信证据，要求只给结论和可核查引用，不请求隐式思维过程。记录最终响应 `content`；独立 `reasoning_content` 字段不保存，完整 `<think>…</think>` 块剔除并记录标志。

## 排名、预算与失败

初排及每轮联合输出保存 `failure_score`，要求非负且总和为 1（浮点/格式舍入容忍 ±0.02），其含义为未校准的模型判断。

最终 `root_ranking.score` 对选中设备为负平均名次，越大越好；被 Top-p 筛除的设备按初排顺序附在尾部，以负最终位置评分，另有 `stage=retained_initial_tail`。不把这些分数称为概率。三轮中的任何一轮失败都会使整例失败，不择优取轮，也不把失败事故移出结果。

配置区分 `sampling_top_p`（模型采样）和 `candidate_top_p`（内部候选筛选），默认独立联合轮数为 3。可冻结批次大小、每设备事件数、消息字符数、时间线批次、最短路径枚举上限、模型最大输出 token、提示字符上限、调用次数上限、温度、随机种子、超时和重试次数。

`max_prompt_chars` 是明确的字符上限，不冒充精确 token 计数；token 使用量只记录后端实际返回的 usage。后端缺 usage 时另报未知调用数，不以 0 表示无成本。触及全候选初排/联合提示长度、路径枚举或调用预算会显式 `runtime_failure`，不会偷偷缩减候选。所有调用的耗时包含失败重试。

输出包含：`case_id/method/version/seed/status/root_ranking/native_graph/device_graph/graph_condition/adapter_version/diagnostics/timing`。诊断保存白名单输入哈希、配置、提示版本、所有实际请求和最终响应内容、已解析结果、阶段摘要、初排、筛选、每轮排名、聚合规则、证据裁剪清单和 token/时延。CLI 另保存输入集合与实现文件的 SHA-256 清单。失败输出排名为空，状态保留原 case_id，CLI 以非零退出码提醒存在失败，仍写出完整结果文件。

## 验收

```powershell
& 'tmp/baselines-venv/Scripts/python.exe' -m pytest tests/test_bian_adapt.py -q
```

详细边界和验证状态见 [`validation_report.md`](validation_report.md)。正式评测还需实际模型部署、冻结事故划分与数据清单、确认预算和后端版本，并通过公共评测器计算覆盖及失败分母。该实现本身不读取根/边真值，也不计算依赖真值的得分。
