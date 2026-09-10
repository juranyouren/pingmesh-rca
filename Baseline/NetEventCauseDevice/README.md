# NetEventCause ODE 机制重建与设备适配

身份：`NetEventCause-ODE-reimpl-Device-prior-calibrated-adapt`，版本 `0.1.0`。
这是可训练的 PyTorch 实现，包含 ODE-RNN 点过程、区间似然积分、空历史正则、根事件先验比值及 Integrated Gradients。它不是作者发布模型的原样运行，也不是旧的 Hawkes 根排序器。

## 输入、模块与适配

| 原始机制 | 当前实现 | 输入/适配边界 |
|---|---|---|
| 告警类型 × 实体类型 | 训练折唯一词表，设备 ID 不作为类型特征 | 默认仅 `source=alarm/alert`，日志需预先明确启用并单列配置 |
| Eq. (1) ODE-RNN | 自主神经 ODE + GRU 跳变 | 固定步长 RK4；不是论文实验的 Dormand–Prince |
| Eq. (2) 条件强度 | query 与事件特征的点积给出 log intensity | 维度与时间单位是显式工程参数 |
| Eq. (3) NLL | 所有类型强度的 RK4 联合积分减事件 log intensity | 包含观察起点、事件间隔和末事件到截止时刻的尾区间；逐事故重置 |
| Eq. (7) 根先验 | `mu[k] = rho * count_train[k] / duration_train` | 固定共享 rho 工程适配；没有根告警人工标注；设备根标签不转成事件标签 |
| Eq. (9)/(12)/(13) 空历史正则 | 保留事件时间与 GRU 跳变位置，历史输入嵌入归零；所有类型平方误差求和 | 正则必须启用；默认权重 1 |
| Eq. (10) IG | 对目标 **log intensity** 做梯形积分；空历史与训练正则基线一致 | 保留每个历史事件的带符号贡献和完整性残差 |
| Algorithm 2 | 原始先验/条件强度比值 ≥ 0.2 判根；衍生事件取 Top-K 原因 | 只把正 IG 贡献输出为边；负贡献不反转或抬成正数 |
| 设备根排名 | 每设备事件根评分最大值 | 无可评分事件设备 score=null，排在可评分设备之后 |
| 事件图 → 设备图 | 输出原生事件依赖假说图交给公共适配器 | 原生事件图不强行套物理拓扑；设备输出只能由公共适配器过滤 |

完整偏离、原始代码缺口和哈希见 [reproduction_gap.md](reproduction_gap.md)。没有使用作者检测代码中按事件类型 0–4 写死的因果规则、0.01 支持下限或未知类型自动根概率 1。

## 运行

已验证运行时：Windows / Python 3.12.10 / PyTorch 2.14.0+cpu。固定依赖见 [requirements.txt](requirements.txt)。共享环境位于仓库 `tmp/baselines-venv`；系统 Python 3.14 没有 PyTorch，不应拿它代替该环境。

仓库根目录执行，路径参数可以是其他位置的规范化 JSONL 或 JSON 数组：

```powershell
& 'tmp/baselines-venv/Scripts/python.exe' -m Baseline.NetEventCauseDevice train --inputs train.jsonl --validation-inputs validation.jsonl --checkpoint output/nec/fold0.pt --config Baseline/NetEventCauseDevice/default_config.json
& 'tmp/baselines-venv/Scripts/python.exe' -m Baseline.NetEventCauseDevice predict --inputs test.jsonl --checkpoint output/nec/fold0.pt --output output/nec/root.jsonl
& 'tmp/baselines-venv/Scripts/python.exe' -m Baseline.NetEventCauseDevice predict --inputs test.jsonl --checkpoint output/nec/fold0.pt --output output/nec/native_graph.jsonl --graph
& 'tmp/baselines-venv/Scripts/python.exe' -m pytest tests/test_nec_device.py -q
```

本地 CLI 使用 `Baseline.common.io.normalize_incident` 再次白名单化输入。它不接受原始 full_link、标签文件或 PC-STGR 输出；原始转换、事故分组和 train/validation/test 划分由公共框架负责。推理窗口、事件时刻和记录时刻均按公共 `parse_timestamp` 解析；记录晚于 cutoff 的事件不进入历史。

```python
from Baseline.NetEventCauseDevice import NECConfig, NetEventCauseDevice

model = NetEventCauseDevice(NECConfig(), device="cpu")
model.fit(train_cases, validation_cases=validation_cases)
model.save("output/nec/fold0.pt")
model = NetEventCauseDevice.load("output/nec/fold0.pt")
root = model.predict_root(incident)
native = model.predict_raw_graph(incident)
```

`fit` 可接公共接口的 `train_labels`、`validation_labels` 参数，但明确不使用它们。模型只按训练事件拟合词表/先验/参数；验证集仅按 NLL 选 epoch，不扩充词表。训练与验证的 group_id 重叠会报错。检查点附 `.pt.json` 训练证据：输入清单哈希、训练组、词表哈希、每类型计数、先验、每 epoch NLL/正则、随机种子、时间、实现哈希及运行时版本。

## 输出语义与失败

- `predict_root`：全候选设备排名、事件评分、未知类型及排除事件明细、比值异常、时间开销。
- `predict_raw_graph`：另含事件节点、严格过去 → 当前的原因边、证据 ID、签名 IG 贡献、IG 完整性残差。`graph_kind=event_dependency_hypotheses`，不宣称观察数据识别了真实因果边。
- 两接口都不接收 Oracle 根；根条件只由公共设备图适配器处理。预测不会更新参数或先验。
- 未知组合映射到零嵌入 UNK：可作为有时间的未知事件进入历史，但该事件不评分、不凭未知类型判根；其零输入对 IG 的直接贡献为零。训练 UNK 的先验为零。
- 同时间事件先共享更新前的强度，再按 event_id 稳定顺序跳变；不输出同时间原因边、不抖动时间。稳定顺序仍可能影响后续事件强度，是显式偏离及敏感性因素。
- 比值超过 1 原样保留并记录，不截断或称为校准概率。设备分数为原始比值最大值，边分数为正 IG 归因量。
- 全部无事件/未知类型：`abstained`，全设备保留 null 分数。缺合法时间窗、空候选或超事件预算：`input_ineligible`。无检查点、数值溢出或训练失败不得被当作有效结果。
- 缺失记录时间会被计数；仅知道事件时间并不能证明记录在当时已可获得。缺覆盖元数据时无法证明完整采集；点过程似然拟合的是当前可见告警流，不能把静默设备解释为正常。

## 已验收与尚未验证

实现级数值及隔离测试覆盖解析常数强度 NLL/梯度、含跳变指数强度的 RK4 收敛、空历史正则、未来及同时事件隔离、IG 完整性、实际 ODE-RNN 的 A→B→A 事件方向与设备折叠环、checkpoint roundtrip、未知类型/静默设备/截止时间、标签隔离及训练损失下降。固定合成用例的参数只在测试里使用。

尚未与作者缺失的完整 ODE 模块做逐数值等价对照；没有获得作者 IMOC 数据/权重。未据此报告真实数据 Root/Graph 准确率、论文表格复现成功或生产规模吞吐。默认配置是可运行起点，必须在训练/验证组冻结后使用，不能根据测试效果调整 rho、阈值、K、ODE/IG 步数。
