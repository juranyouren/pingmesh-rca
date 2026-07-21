# Sys_v1：三阶段模块化实现

`Sys_v1` 由当前 `Sys` 完整复制后改造，所有新逻辑都保留在本目录中，不修改原 `Sys`。

## 模块边界

- **M1 设备聚焦**：使用告警规则权重构造 Personalized PageRank 初始值，并结合路径穿越增强和源/宿邻近关系在物理拓扑上传播，得到拓扑嫌疑排名。
- **M2 证据构造**：为候选设备构造证据表。小模型按设备独立总结，并同时看到该设备直接邻居的受限告警上下文。默认每个邻居只保留规则权重最高的一条告警。
- **M3 可信决策**：计算最终确定性排名，进行置信度路由；证据充分时直接接受，否则交给本地大模型复核。M3 对外仍是一个模块。

完整方案先由 M1 选出拓扑 Top-K，再在这些候选内运行 M2；初始融合分数严格采用拓扑分数与时序分数的算术平均。小模型语义摘要暂不直接进入数值打分，只作为 M3 复核证据。

## 四组消融

| 参数 | 执行路径 | 数值排名 | 小模型 |
|---|---|---|---|
| `m1` | M1 | 拓扑分数 | 不运行 |
| `m1_m3` | M1 → M3 | 拓扑分数 | 不运行 |
| `m2_m3` | M2 → M3 | 全设备时序分数 | 可运行，扫描全部设备 |
| `m123` | M1 → M2 → M3 | `(拓扑 + 时序) / 2` | 可运行，扫描 M1 Top-K |

统一入口：

```bash
python Sys_v1/RootCauseAnalyze/SkilledAnalyzer.py \
  --ablation m123 \
  --data-root /path/to/cases \
  --top-k 10 \
  --summarize-nodes \
  --summary-model-path /path/to/local-small-model
```

其余消融只需替换 `--ablation`。`m1` 不会初始化小模型或大模型。M1+M3 即使传入 `--summarize-nodes` 也不会执行 M2。

### 一键运行消融实验

默认依次运行四种消融并在每组结束后执行 `Score_N`：

```bash
bash Sys_v1/run_ablation_experiments.sh
```

也可以只运行指定模式：

```bash
bash Sys_v1/run_ablation_experiments.sh m1 m123
```

常用参数通过环境变量覆盖：

```bash
RUN_TAG=paper_v1 \
SYS_V1_MAIN_NPU_CARDS=4,5 \
SYS_V1_SUMMARY_NPU_CARD=0 \
SYS_V1_TOP_K=10 \
SYS_V1_BATCH_SIZE=4 \
bash Sys_v1/run_ablation_experiments.sh
```

默认输出到 `$PINGMESH_RESULTS/${RUN_TAG}_<mode>/`。设置 `SYS_V1_SKIP_SCORE=1` 可只运行推理、不自动评测。

## 邻接告警上下文控制

```bash
--neighbor-alarm-mode highest_weight  # 默认：每个邻居一条最高规则权重告警
--max-neighbor-devices 8              # 单个目标设备最多纳入 8 个有告警邻居
--neighbor-alarm-mode all             # 调试用：每个邻居保留多条告警
--max-neighbor-alarms 3               # all 模式下每个邻居的上限
--summary-context-max-chars 3500       # 单设备小模型 prompt 字符上限
```

邻接告警只用于 M2 的语义证据。告警权重负责选择上下文，不代表设备严重度或因果关系。

## 本地验证

```bash
python -m pytest Sys_v1/tests -q
python -m compileall -q Sys_v1
```
