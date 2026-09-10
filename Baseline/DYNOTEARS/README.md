# DYNOTEARS-CausalNex-kernel-incident-graph-adapt

本实现运行 CausalNex 作者实现中**未改动的 DYNOTEARS 数值函数**，并接入公共设备事件序列。它保留同期矩阵 W 和滞后矩阵 A 的联合估计，不以静态 NOTEARS 替代 DYNOTEARS。逐事故无标签拟合，所有优化时间计入该事故推断耗时。支持公共适配器的 Oracle/共同预测根图实验；不提供 Root 排名或自主 Full-Graph。

来源：[原论文](https://arxiv.org/abs/2002.00498)、[官方 CausalNex 实现](https://github.com/mckinsey/causalnex/blob/develop/causalnex/structure/dynotears.py)。`upstream/dynotears.py` 保存已核对的完整作者源码；`provenance.json` 固定来源地址、抓取日期、完整源码和提取内核 SHA-256。运行文件 `author_kernel.py` 只提取 `_reshape_wa`、`_learn_dynamic_structure`，移除 pandas、StructureModel 外包装的依赖；这两函数体未经更改。保留作者版权/商标说明和 `LICENSE.causalnex.md`，完整 Apache 2.0 文本在 `LICENSE-2.0.txt`。

| 原机制 | 保留 | 本项目适配 / 限制 |
|---|---|---|
| SVAR 同期 W 与滞后 A 联合目标 | 原作者损失、梯度、L1 正则、增广拉格朗日与无环约束 | 不依赖不兼容 Python 3.12 的完整 CausalNex 包，直接运行锁定数值内核 |
| `Xlags=[shift(X,1),...,shift(X,p)]` | 原始滞后块顺序和 `source(t-lag) → target(t)` | 输入为公共分箱事件数；默认 `log1p(count)`，不是连续 KPI |
| 结构系数 | 原始 W/A、滞后、正负系数、自回归 | 当前事故内按列标准化；输出支持取绝对系数，符号独立保留，负号不反转方向 |
| 优化收敛 | h(W)、警告、每次 L-BFGS-B 状态与损失 | 调用观察器收集作者内核忽略的 OptimizeResult，函数体和数值路径不变 |
| 原生时间图 | 所有超过门限的关系 | 设备折叠可能成环，交公共适配器处理，不宣称原生图就是事故传播 DAG |

调用观察器使用函数局部的 `sopt.minimize` 代理，只记录返回值，不更换优化器、不改参数、不在共享模块上做全局补丁。若任一优化子问题未成功、作者警告未收敛或 h(W) 超容差，则记录 `runtime_failure` 并保留未收敛 W/A 和诊断；这些数组仅供失败分析，不输出有效边。原作者只返回 `.x`，因此检查优化器状态是必要的额外运行审计，而不是算法机制修改。

默认参数见 `default_config.json`：10 秒分箱、`log1p`、最少 30 箱、最多 30 个非常量变量、p=2、两类 L1=0.1、100 次外循环、h_tol=1e-8、绝对边门限 0.05。参数只允许在训练/开发侧冻结，不能按测试图调参。标准化只使用当前事故允许观测，不跨事故拼接。

公共 `baseline-incident-v1` 输入缺可靠采集 coverage、包含未知箱、箱数不足或非常量设备不足时返回 `input_ineligible`。不静默填零；常量设备在公共审计中保留，模型只拟合可估计变量。`require_coverage=false` 只用于另列且明确标识的记录计数假设，默认保持 true。最少箱数是工程门槛，不保证稳定统计估计。

```python
from Baseline.DYNOTEARS import DYNOTEARS

native = DYNOTEARS().predict_raw_graph(incident)
# source(t-lag) -> target(t)，score=abs(coefficient)，coefficient 保留符号。
```

```powershell
python -m pytest tests/test_baseline_discovery.py -q
python -m Baseline.common.runner predict --inputs normalized.jsonl --output dynotears-oracle.json --method dynotears --task oracle --labels labels.json --config Baseline/DYNOTEARS/default_config.json
```

运行版本：Python 3.12；NumPy 2.5.3、SciPy 1.18.1。锁定的完整依赖由公共框架维护。`discover_matrix` 是连续合成序列数值验收入口。

验收包含：与锁定作者源码 AST 核对、同一输入 p=2 的 W/A 数值对照（容差 1e-12）、实际滞后正/负作用方向、自回归、h(W) 和优化器状态、真实外循环不收敛、模拟优化器失败、标签不改变原生图、完整观测事件计数接入、缺 coverage 拒绝。已运行的合成输出见 `validation/synthetic_prediction.json`；本地两例真实 raw 均无可靠 coverage，未产生生产准确率结果。
