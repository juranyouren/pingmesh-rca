# Sys_v1：三模块简单消融实现

`Sys_v1` 是三阶段重构方案的隔离实现。原目录 `Sys/` 不做任何修改；本目录仅只读复用已有的数据加载工具和确定性时序特征计算。

## 四组实验

| Variant | M1 | M2 | M3 | 首版决策分数 |
| --- | :---: | :---: | :---: | --- |
| `m1` | ✓ |  |  | 拓扑分 |
| `m1_m3` | ✓ |  | ✓ | 拓扑分 |
| `m2_m3` |  | ✓ | ✓ | 时序分 |
| `m123` | ✓ | ✓ | ✓ | `(topology + temporal) / 2` |

融合器只对当前实验实际启用的评分源求平均。因此：

- `m1_m3` 不会偷偷调用时序评分；
- `m2_m3` 不会偷偷调用拓扑评分；
- `m123` 始终严格执行 `(topology + temporal) / 2`；
- 某个已启用评分源全为 0 时仍参与平均，并记录在 `fusion.zero_signal_sources`；
- 某个启用源连评分映射都无法生成时，记录在 `fusion.sources_unavailable`。

## 模块边界

### M1：拓扑候选聚焦

`Sys_v1/topology.py` 实现了独立的纯拓扑 PageRank，不使用告警权重、告警数量、日志或标签。允许使用物理连接、Pingmesh 异常端点和路径 `cross` 信息。

### M2：多源证据构建

- `m123`：只处理 M1 Top-K 候选；
- `m2_m3`：处理案例中的全部设备，因此运行时间和证据表规模都会明显增加；
- 首版小模型语义不参与数值打分，只作为 M3 复核上下文；
- 可通过 `--semantic-cache-dir` 加载预先生成的逐设备语义结果。

`m2_m3` 会对全部设备构造证据并计算时序分，但为了避免主 LLM 输入超过上下文，M3 复核只接收综合初排后的 Top-K 设备。设备聚焦依据来自 M2 时序证据，不使用 M1 拓扑排序。

### M3：可信根因决策

首版 Gate 仅使用无标签信号：

- 单一评分源：Top-1/Top-2 分差达到阈值时直接采用，否则调用 LLM；
- 两个评分源：Top-1 一致且融合分差达到阈值时直接采用，否则调用 LLM；
- 无有效评分时转人工复核。

LLM 只能在初始 Top-K 合法候选中调整排序。项目只支持本地 vLLM，不调用外部模型 API。

## 运行

先进行不加载 LLM 的结构和确定性评分检查：

```bash
python -m Sys_v1.run_ablation \
  --variant all \
  --data-root /path/to/nodes_labeled \
  --output-dir /path/to/results/sys_v1_dryrun \
  --llm-backend none
```

`none` 模式下，如果 Gate 请求 LLM，程序会保留初始排名并标记 `llm_unavailable_keep_preliminary`。该结果只能用于流程检查，不能作为完整 LLM 实验结果。

使用本地 Ascend vLLM：

```bash
python -m Sys_v1.run_ablation \
  --variant all \
  --data-root /path/to/nodes_labeled \
  --output-dir /path/to/results/sys_v1_full \
  --llm-backend vllm \
  --model-path /path/to/local/model \
  --npu-cards 0,1 \
  --top-k 10 \
  --llm-batch-size 8
```

常用参数：

```text
--single-source-margin 0.15
--multi-source-margin 0.08
--semantic-cache-dir /path/to/cache
--max-events-per-device 30
--max-cases 10
--save-prompts
```

## 评测与表格

推理代码不读取 `label.json`。实验完成后单独执行评测：

```bash
python -m Sys_v1.evaluate --results-root /path/to/results/sys_v1_full
```

评测输出：

- `ablation_summary.json`：Top-1/3/5、MRR、Fix/Harm/Net Gain、LLM 调用数；
- `ablation_table.md`：可直接复制到论文或方案文档的消融表。

评测采用四组结果目录的案例并集。某个 Variant 缺失输出时按未命中计算，不通过缩小分母提高准确率。
