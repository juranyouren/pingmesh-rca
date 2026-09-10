# PCMCI+-ParCorr-incident-graph-adapt

本实现实际调用 Tigramite 的 `PCMCI.run_pcmciplus`，发现含同期及滞后关系的原生时间图。逐事故、无标签拟合，拟合开销全部计入单例推断耗时。支持交给公共适配器的 Oracle/共同预测根图实验；没有原生根排名，不支持 Root 或自主 Full-Graph。

来源：[Runge, UAI 2020](https://proceedings.mlr.press/v124/runge20a.html)、[Tigramite 官方 API 源码](https://jakobrunge.github.io/tigramite/_modules/tigramite/pcmci.html)。使用已安装依赖 `tigramite==5.2.10.1`，没有在此目录复制 Tigramite 源码；上游代码遵循 GPL-3.0，许可详情见[官方仓库](https://github.com/jakobrunge/tigramite)。本目录为数据接入和输出映射代码。

| 原机制 | 保留 | 当前输入适配 / 限制 |
|---|---|---|
| PCMCI+ 同期及滞后条件独立检验 | `run_pcmciplus`、冲突处理、原始箭头矩阵 | 默认 `ParCorr` 是对事件计数 `log1p` 序列的线性连续近似；不能称为原有连续 KPI |
| CPDAG 中未定向关系 | `o-o`/`x-x` 等作为 `directed=false` 另存 | 不靠 p 值、设备 ID、根位置强制定向；公共适配器仅聚合确定方向 |
| 时间变量及原生统计量 | `graph/p_matrix/val_matrix`、方向、滞后、符号 | 设备序列一变量一设备，支持分数为绝对 ParCorr 统计量，不是概率 |
| 多变量统计估计 | 每例重置，无跨事故拼接 | v1 与 DYNOTEARS 一致，只接收完整共同观测窗口；不使用插值或填零补缺 |

默认配置见 `default_config.json`：10 秒分箱、`log1p(count)`、最少 30 箱、最多 50 个非常量变量、最大滞后 2、`pc_alpha=0.01`、最大条件集 3、无 FDR 校正。门槛是工程配置，不证明平稳性、可识别性或足够统计功效。时间图不能直接解释为某次事故的实测传播图。

公共 `baseline-incident-v1` 输入必须具有可靠 `observation_coverage`。缺 coverage 返回 `input_ineligible`；部分箱未知也不拟合。常量设备从拟合中剔除并在 `input_audit.constant_devices` 留痕，公共候选域不删除。`require_coverage=false` 是明确另列的记录计数假设，零记录不表示健康，正式主配置保持 true。全部参数应在训练/开发事故冻结，不按测试图调整。

```python
from Baseline.PCMCIPlus import PCMCIPlus

native = PCMCIPlus().predict_raw_graph(incident)
# 原生 edges 的 source(t-lag) -> target(t)，包括原生自回归。
# native 交给公共 adapt_graph；本模型不接收根条件或标签。
```

```powershell
python -m pytest tests/test_baseline_discovery.py -q
python -m Baseline.common.runner predict --inputs normalized.jsonl --output pcmci-oracle.json --method pcmci --task oracle --labels labels.json --config Baseline/PCMCIPlus/default_config.json
```

`predict_raw_graph` 返回状态、原生矩阵、每条关系的滞后/原始箭头/符号/p 值/支持分数及 `series:<device>` 证据引用。预测失败保留案例 ID 和原因，不伪造成功空图。`discover_matrix(matrix, device_ids)` 是连续合成序列的数值验收入口，不跳过正式输入门槛参加生产评测。

已实际运行的验证见 `validation/synthetic_prediction.json` 和共享的 `tests/test_baseline_discovery.py`：固定种子滞后链方向、负统计量、自回归、同期未定向关系、完整观测事件计数的公共输入接入、标签变动不影响图、缺 coverage 拒绝。合成结果仅说明实现接通并通过机制检查；本地真实 raw 两例没有可靠 coverage，均按 `input_ineligible` 记录，没有生产准确率结果。
