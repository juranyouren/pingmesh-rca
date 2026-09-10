# BiAn-adapt 验收记录

日期：2026-09-10。版本 `0.1.0`，输入契约 `baseline-incident-v1`。

## 已执行

使用 `tmp/baselines-venv/Scripts/python.exe -m pytest tests/test_bian_adapt.py -q`：**26 项通过**。

测试故意注入由测试代码生成的响应，仅检查工程契约，不是模型预测证据、作者示例复现结果或正式 RCA 成绩。测试覆盖：

- 8 个候选设备完整保留（含无事件设备），7 类异常、拓扑和时间线都执行，联合推断执行 3 次。
- 对顶层、window、endpoint、devices、links、events、coverage 增加或替换标签/派生分数字段后，发送的所有请求、输入哈希和排名完全一致。
- 白名单端点列表保留，嵌套额外对象被剔除；事件窗口和记录截止时间在发送前验证。
- 并列事件与未知时间保留；每设备预算相同、逐 ID 记录遗漏；无观测事故明确不适用。
- 未知证据 ID、遗漏候选、第三次联合推断失败均使事故失败；重试保存首个错误响应；后端失败不生成启发式排名。
- Top-p 累计 softmax 和筛除后的初排尾部可重算；Rank of Ranks 使用平均名次，轮内平分取平均名次，而不是平均模型分数。
- 拓扑摘要保留全部最短路径、移除经过内部嫌疑设备的路径，缺设备组时不虚构合并；路径预算超限有错误。
- 私网/远程/带 URL 凭据的端点被拒绝；生产客户端禁用代理和重定向。异常不会输出任意第三方异常文本或密钥，独立 reasoning 字段不落盘。
- 单轮模式使用独立的消融方法标识。

另执行真实 HTTP 后端连通检查：

```text
python -m Baseline.BiAnAdapt --synthetic-smoke
  --output Baseline/BiAnAdapt/validation/local_backend_smoke.json
  --timeout-seconds 1 --retries 0
```

该命令未注入测试 transport，只向本机 loopback 发送公开构造的三设备、两事件观测。结果为 **`runtime_failure`，调用次数 1，排名为空**；服务不可用或超时。没有把该失败计为 BiAn 根定位成绩，也没有发送真实事故到外部服务。记录保存了精确请求、配置、输入/代码哈希与失败时间。

## 尚未验证

- 未连接实际部署模型，未验证后端对所配置模型标识、seed、JSON response_format 的支持。
- 未运行正式数据集、正式多种子实验或模型 Root 准确率；不存在可报告的 Top-1/3/5、MRR。
- 原文的专有 11 来源、操作 SOP、微调权重、设备组和历史知识演化不可用；只承诺 README 中披露的机制适配。
- 模型对证据的语义解释质量尚未验证；ID 校验能阻止不存在的引用，不能证明真实引用足以支持每项解释。
- Top-p 与裁剪预算的实测召回损失需由独立标签评测器计算；本实现只记录候选及证据的保留/筛除名单。

## 接口交接

公共入口：`from Baseline.BiAnAdapt import BiAnAdapt, BiAnConfig`，调用 `BiAnAdapt(config).predict_root(incident)`。

成功/失败均返回同一结果字典，图字段为 null，能力元数据明确图任务不支持。输入无效或全例无事件为 `input_ineligible`；后端、JSON、引用、候选、预算失败为 `runtime_failure`。没有跨案例 fit 状态，也不隐式载入标签文件。公共 runner 应保留全部状态及失败分母，不能只评估 `ok` 条目。
