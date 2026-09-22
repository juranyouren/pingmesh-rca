# RPG-Recon — Pingmesh 故障传播图恢复

面向 WWW 2027 的研究项目：在**单设备起点（Anchor）**假设下，从 Pingmesh 异常、原始设备拓扑
（`task_topo`）与告警/日志中，恢复 incident-specific 的**设备传播解释图** $G_P=(V,E_P)$。
本系统不声称恢复真实 ECMP 报文路径，也不是已识别的干预模型。

## 方法

```text
Raw Incident Evidence
  -> G_E                      事件证据图构建（含 LLM 语义证据编码）
  -> S                        局部传播关系建模（双向关系似然，保留歧义）
  -> q(a)                     Anchor 估计（P(a is anchor | G_E)）
  -> Anchor-Conditioned Reconstruction   锚点条件全局骨架重建 + DAG 增补
  -> G_P
```

方法与实验口径的完整合同见 [CLAUDE.md](CLAUDE.md)。

## 输入与输出边界

每条输出的传播边必须能映射到至少一条原始 `task_topo` 边。未知关系一律掩码，不转换为负例；
`allowed` 为中性。运行期推断不读取根或传播标签（仅显式 Oracle 评测包装层可接收已确认的测试根）。
缺失采集覆盖记为 `input_ineligible`，不做静默补零。

## 主要目录

| 路径 | 职责 |
| --- | --- |
| `Sys/Preprocess/` | 观测预处理、raw 拓扑 sidecar、结构等价映射、LLM 证据编码 |
| `Sys/RootCauseAnalyze/propagation/` | 证据图、局部关系建模、锚点条件重建（M1/M2） |
| `Sys/RootCauseAnalyze/stage1/` | 确定性锚点先验；图注意力锚点估计模型（保留复用，暂无 runner） |
| `Sys/Score/` | 传播图评价、实验汇总 |
| `Baseline/RQ1/` | **当前唯一在用的 baseline experiment runner** |
| `Baseline/common/` | RQ1 依赖的公共数据/标签/评分契约（库，非 runner） |
| `Baseline/NetEventCauseDevice/` | RQ1 的 NEC baseline 实现 |
| `scripts/` | 贯通脚本与服务器环境配置（见下） |
| `docs/` | 方法与历史材料 |
| `tests/` | `python -m pytest` 测试 |

`data/`、`res/`、`tmp/`、`output/`、`archive/` 存放内部数据与环境生成物，默认不入库。

## 运行入口

数据与 NPU 卡只在服务器上，**本地无法运行完整实验**（本地只能跑 CPU-safe 测试）。

```bash
source scripts/common.sh          # 路径/模型/NPU 卡/公共参数的唯一入口

bash scripts/run_rq1.sh                    # RQ1：设备传播图恢复实验
bash scripts/run_preprocess.sh             # raw 拓扑 sidecar + 结构等价映射
bash scripts/run_llm_encoder.sh --data "$PINGMESH_DATA" --output "$PINGMESH_RESULTS/enc"
bash scripts/run_full_experiment.sh        # 完整方案：预处理 -> 重建 -> 评价
bash scripts/run_full_experiment.sh --evidence-dir "$PINGMESH_RESULTS/enc"
bash scripts/run_llm_encoder_full.sh       # 证据编码 -> 重建 -> 指标（含 --compare-rules）
```

每个脚本开头都有完整的调用示例；默认值全部来自 `scripts/common.sh`，无需手工传长参数。

实验结果统一写入 `${PINGMESH_RESULTS}`（默认 `res/`），run 目录命名
`<experiment>_<variant>_<YYYYMMDD_HHMMSS>_<git-short-sha>[_NN]`，由 `pingmesh_create_run_dir`
统一创建，并写入 `run_config.json` 记录 model/seed/git/paths 等可复现信息。

本地 CPU 验证：

```bash
python -m pytest tests -q                  # 17 passed
python -m pytest Baseline/RQ1/tests -q     # 60 passed, 1 skipped
```

## 重要边界

本项目当前处于「实现原型与历史结果已有，评价证据待整理、论文主张待验证」阶段。
历史数字与功能测试通过**不等于**已复现的论文精度。
工程清理状态与尚未实现的研究方法（Maximum Evidence Arborescence、DAG Augmentation 等）
记录见 [CLAUDE.md](CLAUDE.md)。
