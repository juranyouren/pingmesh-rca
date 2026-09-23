# LLM Evidence Encoder

服务器运行，输入为预处理后的 incident 目录（`nodes.json` 或现有全链路节点文件），支持节点列表或以设备为键的字典。模型和数据无需下载到本机。

## 一键完整流程与指标

```bash
# 进入项目根目录，激活服务器现有的 Ascend/vLLM 环境。
# 仅在缺少评估依赖时安装，不替换 torch/CANN/vLLM。
python -m pip install -r scripts/requirements-llm-encoder.txt

export PINGMESH_MODEL_PATH="${PINGMESH_MODEL_PATH:-/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B}"
export PINGMESH_NPU_CARDS=0,1,2,3

# 先跑少量真实事件；删除 --limit 10 即跑全量。
bash scripts/run_llm_encoder_full.sh \
  --data /path/to/nodes_max_labeled \
  --output /path/to/results/llm_encoder_run_01 \
  --limit 10 --compare-rules
```

默认使用现有确定性锚点先验（拓扑/告警 PageRank + 时序证据），LLM 证据经 adapter 传入现有 M1 候选图、边状态推断、M2 根因重排和路径推断，最后调用现有根因及路径评估函数。这里不重新训练神经模型。若要复用已有神经模型/OOF 根因结果，增加 `--root-results /path/to/root/res.json`，要求包含当前所有选中事件，且 `dir` 与服务器的数据路径一致。已有 reranked_root_rankings 按原流程保留排序，其影响会反映在结果中。

`--compare-rules` 使用完全相同的事件与锚点先验，再跑一次原规则编码流程，用于观察证据替换带来的差异。模型全程只初始化一次，比较组不调用模型。默认根因候选数为 5，可通过 `--top-k` 增加；Top-5/MRR 只针对所保留的候选排序。

输入每个事件需要 `info.json`、节点文件、从原始 `task_topo` 构建的 `topology_context.json`。缺少原始拓扑时添加 `--raw-root /path/to/raw`，脚本会调用已有回填模块补齐；仍缺失则在加载大模型前报错，不将缺失拓扑退化成空图。若只有 RAW 数据，先用项目已有预处理器生成 NODE 数据：

```bash
python -m Sys.Preprocess.Preprocessor --raw /path/to/raw --out /path/to/nodes --write --count-logs
```

预处理器沿用现有带标签样本筛选规则。根因指标读取事件目录下的 `label_v2.json` 或 `label.json`；路径指标读取同目录的 `propagation_label.json`，也可指定 `--labels-root /path/to/propagation_labels`，其结构为 `<case_id>/propagation_label.json`。推理不读取标签。路径指标采用原始设备边，不做结构等价合并。

运行结束时控制台直接打印结果表，同时落盘：

- `summary.md` / `summary.csv` / `summary.json`：各组 Top-1/3/5 (%)、MRR、节点与有向边 Precision/Recall/F1、评估样本数、失败数；CSV/JSON 还包括 DAG 有效率、拓扑有效率及平均边数。
- `evidence/<case_id>/`：编码证据、原始记录、临时词汇、候选词汇。
- `llm_encoder/res.json`：最终根因排序和证据来源；`selected_propagation_paths.json`：最终传播路径；`evidence_episodes.json`：实际传入 M1 的 canonical evidence 适配结果。
- `llm_encoder/evaluation.json` / `sum.json` / `top1_failures.json`：详细评估与失败案例。
- `rules/`：启用对照时的同格式结果；`run.json`：模型路径、词汇、事件列表及配置。

编码阶段同时输出逐事件进度行与 summary 中的 `Encode:` 行（设备数、有记录设备数、raw 记录数、LLM 调用数、生成耗时、输出 token 数、截断次数）。只有「有记录」的设备会触发 LLM 调用，该计数用于判断耗时到底来自调用次数还是单次生成。

编码汇总包含 raw observation 数、canonical evidence 数、覆盖率、去重压缩率、未解决 UNKNOWN 数和 partial 事件数。覆盖率不是语义准确率。缺少标签时指标显示 N/A，并给出标注样本数，不输出虚假零分；推理失败的带标签事件仍计入准确率分母。图有效性只在成功预测上统计，需结合平均边数查看，避免把空图的有效率当成路径质量。

输出目录必须新建或为空，避免混入旧结果。缺失或输入指纹不匹配的证据会报错，不回退到规则解析。UNKNOWN 原文保留在证据产物中，不伪装成已识别事件；临时概念保留原 predicate，并作为 generic event 参与图中事件/目标选择，不擅自映射到物理链路故障。恢复事件标为 clear，不作为故障目标；不可信时间不参与时序边评分；peer 地址不会擅自解析成管理 IP。

退出码 0 为流程完成；2 表示存在推理失败或 partial 编码，但仍写出已完成的指标。允许 UNKNOWN 而希望正常退出时加 `--allow-partial`；推理失败仍非零。模型加载/执行等异常直接报错。无需 NPU 的完整冒烟验证：

```bash
bash scripts/run_llm_encoder_full.sh --smoke --compare-rules --output output/llm_encoder_smoke
```

`--smoke` 明确使用合成数据和模拟 engine，指标仅说明链路可运行，不代表真实模型准确率。

## 单独运行编码器

```bash
# 在已配置 CANN、torch-npu、兼容版本 vLLM/vllm-ascend 的服务器环境中运行
export PINGMESH_MODEL_PATH="${PINGMESH_MODEL_PATH:-/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B}"
export PINGMESH_NPU_CARDS=0,1,2,3
bash scripts/run_llm_encoder.sh --data /path/to/incidents --output /path/to/evidence

# 小模型：按服务器内存情况配置卡数；0.5B 建议先用单卡验证
export PINGMESH_MODEL_PATH=/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-7B
export PINGMESH_NPU_CARDS=0
# 或 export PINGMESH_MODEL_PATH=/usr/share/large_language_models/Qwen2.5-0.5B
```

入口在读取 incident 前初始化一次 `get_shared_engine()`，所有设备编码与 UNKNOWN 聚合复用同一对象，多 incident 也复用。同进程的后续智能体应通过依赖注入接收此对象，或调用同一 getter；跨进程不共享，也不为每个设备启动进程。初始化后修改环境变量不会切换模型，需重新启动。历史 LLM reranker 与多方法 public runner 已删除；本仓库现在只有 `get_shared_engine()` 一处引擎入口。

推理使用 vLLM Ascend 本地离线接口，可见卡数作为 tensor parallel size，模型路径必须是已存在的本地目录。Ascend 环境请使用服务器已验证的兼容组合，参考 [官方 Ascend 离线推理说明](https://docs.vllm.ai/projects/ascend/en/v0.7.1/tutorials.html)。`PINGMESH_MAX_MODEL_LEN` / `PINGMESH_MAX_TOKENS` 控制上下文与输出长度，`PINGMESH_LLM_MEMORY_UTILIZATION` 默认 0.85。基础版 Qwen 无 chat template 时使用普通文本 prompt；0.5B 的语义能力需要在真实数据上评估。

每设备通常一次调用，超上下文时递归拆分，绝不截断原记录；单条过长保留为 UNKNOWN。全部设备的 UNKNOWN 通常合并一次调用，聚合超限则保留 UNKNOWN 并标记 partial。格式错误最多重试一次；遗漏、重复、外来 ID、未落在词汇内的值及不在原文中的实体不能成为已知证据。模型运行故障直接抛出，避免伪装成成功。

全局词汇为 `Sys/Preprocess/evidence/vocabulary.json`，支持 `--vocabulary /path/to/reviewed.json`。每个 incident 使用独立 local predicate 命名空间。候选词汇状态为 pending，不自动写回全局词汇，人工审核后再维护全局文件与版本。

程序确定性生成 scoped entity、证据 ID、来源记录、时间质量和图的 observes 边。去重键包括 incident、设备实体、predicate、value、原始时间；不同时间或缺失时间不合并。所有时间默认未经验证，不构造时序因果关系。possible_effects 是词汇中的可能影响，不是观测事实；图不将它们自动变成因果边。peer 地址保留其命名空间，不推测为设备管理 IP。

每个 incident 输出：

- `incident.json`：完整结果、原记录、错误、词汇与图，作为权威结果。
- `devices/*.json`：按设备落盘的证据及未解决 UNKNOWN。
- `manifest.json`：本次设备文件清单与状态，重新运行时以此为准。
- `stats.json`：本事件的编码耗时与调用计数（设备数、有记录设备数、raw 记录数、LLM 调用数、生成耗时与输出 token 数）。只作统计，不参与编码结果；`incident.json` 对相同输入保持可复现。
- `incident_vocabulary.json`：仅当前事件生效的临时概念。
- `candidate_vocabulary.json`：人工审核缓冲区，保留支撑 raw IDs。
- `evidence_graph.json`：设备节点、canonical evidence 节点和 observes 边。完整流程通过 adapter 将同一批 canonical evidence 接入传播模块；也可在原 `propagation_pipeline.py` 命令增加 `--evidence-dir /path/to/evidence`。

文件逐个原子替换。入口退出码 0 表示全部 completed，2 表示存在 partial；异常非零退出。输出目录不要与输入目录重叠。重新运行同一事件覆盖其结果，不跨事件累积候选文件。

本地验证：`python -m unittest discover -s tests -p test_llm_evidence_encoder.py`。测试使用注入的模拟 engine，不需要 NPU 或真实模型；服务器性能、模型映射准确率及 NPU 运行兼容性需在服务器实测。
