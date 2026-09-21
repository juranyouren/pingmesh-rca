# WWW2027 外部 baseline 实现

本轮新增独立实现与公共实验框架。旧 `BiAn/`、`NetEventCause/`、`TraceRCA/` 等目录保持原用途，不自动作为下表方法的替代实现。选型依据和复现边界见 `docs/conferences/WWW2027/Baseline选型与相关工作审查意见.md`、`Baseline实现任务书_供独立智能体执行.md`。

| 命令方法 | 实现与说明 | Root | Oracle / 共同预测根图 | 自主 Full |
|---|---|---|---|---|
| `skynet` | [SkyNet-inspired 告警归属投票](SkyNetVoting/README.md) | 支持 | 不支持 | 不支持 |
| `bian` | [BiAn 三流程、三轮 Rank of Ranks、本地模型适配](BiAnAdapt/README.md) | 支持，需真实模型服务 | 不支持 | 不支持 |
| `nec` | [NetEventCause ODE 机制重建及工程先验](NetEventCauseDevice/README.md) | 支持，需训练 | 支持 | 支持 |
| `pcmci` | [PCMCI+ / ParCorr、Tigramite](PCMCIPlus/README.md) | 不支持 | 输入合格时支持 | 不支持 |
| `dynotears` | [DYNOTEARS、锁定 CausalNex 作者数值内核](DYNOTEARS/README.md) | 不支持 | 输入合格时支持 | 不支持 |

“支持”表示接口与机制实现可运行，不代表已复现原论文精度。NEC、BiAn、SkyNet 的方法名保留 reimpl/adapt/inspired；通用时间图加公共设备适配器后才参与设备传播图任务。REASON、CORAL、NetCause 仍缺对应观测条件，TCDF 为尚未实现的可选扩展。

## 安装和已验证环境

**RQ1（Python 3.10）请使用 [RQ1 安装说明](RQ1/README.md) 和 `Baseline/RQ1/requirements.txt`。**
下面的 `requirements-repro.txt` 是历史 Python 3.12 环境快照，不适用于 RQ1 的 Python 3.10 环境。

本机已建立 `tmp/baselines-venv`，Python 3.12.10 / CPU。从仓库根目录用它运行下列命令，无需重复安装。新机器可执行：

```powershell
py -3.12 -m venv tmp/baselines-venv
& tmp/baselines-venv/Scripts/python.exe -m pip install -r Baseline/requirements-repro.txt
```

[锁定依赖](requirements-repro.txt)包含当前验收的实际版本。SkyNet 和公共数据/评分核心只需标准库；NEC 需要 PyTorch，图方法需要 NumPy/SciPy，PCMCI+ 另需 Tigramite/joblib/cloudpickle。BiAn 使用标准库 HTTP 客户端，模型服务单独部署；默认 `127.0.0.1:8000/v1` 当前未连接。模型权重、型号、采样与 token 设置须在正式实验前冻结。CPU 验收不代表已验证 NPU/GPU。

## 先规范化并审计输入

```powershell
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common prepare --inputs data/raw/pingmesh_labeled --output tmp/baseline-run/inputs.json
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common audit --inputs tmp/baseline-run/inputs.json --output tmp/baseline-run/audit.json
```

也可直接对原始输入运行 audit，以保留原始导出字段的诊断。默认观察窗口是触发 `alarm_time` 前后各 300 秒；`--before-seconds/--after-seconds` 对 raw/processed 转换生效。已规范化输入使用其冻结窗口。所有事件限制在 start–cutoff 内，已知晚于 cutoff 才采集的记录会被剔除。未知事件时间保留为 null，时间算法自行记录排除。

[字段映射](common/raw_to_input_mapping.md)说明原始/处理后文件的接法、零时间占位、缺失行为及禁用字段。公共规范不读取 `label.json`、`groud_truth`、`cross`、预计算分数或本文方法输出。候选来自观测设备和原始物理拓扑，包含静默设备。规范化、标签、统一预测的 [JSON Schema](common/schemas/) 供接入方校验，跨字段关系由公共 Python 校验器继续检查。

时间图默认要求明确的采集覆盖，缺失箱保持未知；不能把样例补成全零背景。`require_coverage=false` 仅允许作为另名、另列的记录计数假设，不能把零记录解释为正常。事件计数不等于 KPI。

## Root 推断与独立计分

```powershell
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common predict --method skynet --inputs tmp/baseline-run/inputs.json --output tmp/baseline-run/skynet.json
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common predict --method bian --config Baseline/BiAnAdapt/config.json --inputs tmp/baseline-run/inputs.json --output tmp/baseline-run/bian.json
```

BiAn 不提供生产 mock 或启发式 fallback。模型不可用、JSON/证据校验失败均保留失败记录。它的注入 transport 只出现在单元测试中。

标签另行人工核定为规范格式后，再执行：

```powershell
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common evaluate --task root --inputs tmp/baseline-run/inputs.json --labels reviewed-labels.json --predictions tmp/baseline-run/skynet.json --output tmp/baseline-run/skynet-eval.json
```

`reviewed-labels.json` 是待提供文件，不是本仓库已有生产真值。完整标签须显式给出节点和边；部分标签使用 `positive_edges/known_edge_mask/allowed_edges` 和节点 mask。允许边为中性，不自动作为必需边；mask 外预测不自动算负例；完全无已知范围时不生成虚假的满分。RQ1 对旧标注 `possible` 采用 `possible-positive` 默认口径（计为已确认有向正边，与 `Sys/Score/evaluate_propagation.py` 一致），可用 `--label-policy strict` 留待人工确认；两种口径都会显式记录，不静默改变评分语义。成功空图和失败分别记录。

## NEC 分组训练与图实验

先提供经核实的 `case_id → 实际事故组` JSON；重复导出、重叠窗口及同源衍生样例须归到同组。分组文件的人工来源仍需实验者核实，程序只检查完整性、组隔离与哈希。

```powershell
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common manifest --inputs tmp/baseline-run/inputs.json --groups reviewed-groups.json --folds 5 --output tmp/baseline-run/folds.json
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common crossvalidate --method nec --task full --inputs tmp/baseline-run/inputs.json --manifest tmp/baseline-run/folds.json --config Baseline/NetEventCauseDevice/default_config.json --labels reviewed-labels.json --output tmp/baseline-run/nec-full.json
```

折数不能超过独立组数量；每个外层测试折外取一个组作为验证，余组训练。两组 smoke 没有验证组，不能据此调参。当前 runner 固定传入配置，只用训练/验证 NLL 选 NEC epoch，**没有自动超参搜索**。若需调参，另在外层训练域内实现内层选择。每折重新训练词表、先验及模型，并保存独立 checkpoint；初始化/训练失败的测试案例仍会落盘。

NEC `predict --checkpoint ... --task root/full/oracle` 使用已有冻结检查点。Root/Full 的 predict 入口拒绝标签参数；crossvalidate 可单独读取标签用于末端评分，只有 Oracle 包装层使用确认根。

```powershell
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common predict --method pcmci --task oracle --inputs tmp/baseline-run/inputs.json --labels reviewed-labels.json --config Baseline/PCMCIPlus/default_config.json --output tmp/baseline-run/pcmci-oracle.json
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common predict --method dynotears --task shared --inputs tmp/baseline-run/inputs.json --roots frozen-shared-roots.json --config Baseline/DYNOTEARS/default_config.json --output tmp/baseline-run/dynotears-shared.json
```

`shared` 的根文件是另一方法提前冻结的预测根映射，不能填入真根冒充共享预测根。公共包装器不向外部图算法传根，只在 `device_greedy_v1` 中使用根。保存原生图、未筛选设备投影、最终图、逐边删除原因及前后合法性；保留多父节点，不补连通路径、不强行定向、不借用本文 P0 解码器。Full 联合边 F1 为“自身 Top-1 正确指示 × 边 F1”。

输入/预测/标签必须覆盖相同案例清单，失败进入分母；另报成功例均值。每项指标有自己的有效标注例数。置信区间仅在事故组已核实且至少两组时进行 group bootstrap。

## 可重复的功能 smoke 与测试

以下命令只生成公开合成接口夹具，不生成真实研究结论：

```powershell
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common.synthetic --output tmp/baseline-validation/synthetic
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common manifest --inputs tmp/baseline-validation/synthetic/inputs.json --groups tmp/baseline-validation/synthetic/groups.json --folds 3 --output tmp/baseline-validation/synthetic/folds.json
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common crossvalidate --method nec --task full --inputs tmp/baseline-validation/synthetic/inputs.json --manifest tmp/baseline-validation/synthetic/folds.json --labels tmp/baseline-validation/synthetic/labels.json --config tmp/baseline-validation/synthetic/nec-smoke.json --output tmp/baseline-validation/synthetic/nec-full.json
& tmp/baselines-venv/Scripts/python.exe -m pytest tests/test_baseline_common.py tests/test_nec_device.py tests/test_bian_adapt.py tests/test_skynet_voting.py tests/test_baseline_discovery.py -q
```

完整状态与尚缺条件见 `docs/conferences/WWW2027/Baseline实现进度与验收.md`。原始观测派生的逐例产物放在忽略的 `tmp/baseline-validation/`；本轮没有填入论文性能表或修改原稿中的实验数字。
