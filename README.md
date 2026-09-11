# RPG-Recon — Pingmesh 故障传播图恢复

面向 WWW 2027 的研究项目：在**单设备起点**假设下，从 Pingmesh 异常、原始设备拓扑
（`task_topo`）与告警/日志中，恢复 incident-specific 的**设备传播解释图**。主输出是
设备影响关系的解释 DAG；根排序为其提供候选起点，本身不是最终产物。本系统不声称
恢复真实 ECMP 报文路径，也不是已识别的干预模型。

## 当前方法（两阶段）

```text
Pingmesh context + raw task_topo + alarms/logs
  -> Stage 1  PC-STGR 分组 OOF 根候选 Top-K 排序     (概念模块 M1)
  -> Stage 2  P0 根条件传播 DAG 重建                  (概念模块 M2 + M3)
  -> 最终根 + 设备传播 DAG + 证据与候选替代
```

- **P0** 是论文方法：确定性证据归一化 + 根条件路径选择与 DAG 组装。
- **P4** 是独立的监督优化轨道，与 P0 共用解码器，结果需分开报告。
- **P1 已停用**，不再运行或报告。
- 单设备根范围不变；Top-K 指相互竞争的起点，不是同时存在的多个根。
  多根与链路根扩展延后。

## 输入与输出边界

每条输出的传播边必须能映射到至少一条原始 `task_topo` 边。未知关系一律掩码，
不转换为负例；`allowed` 为中性，`possible` 的语义需人工确认。运行期推断不读取
根或传播标签（仅显式 Oracle 评测包装层可接收已确认的测试根）。

## 主要目录

| 路径 | 职责 |
| --- | --- |
| `Sys/Preprocess/` | 观测预处理、raw 拓扑 sidecar、结构等价映射 |
| `Sys/RootCauseAnalyze/stage1/` | PC-STGR 根候选：确定性排序、神经模型、OOF 训练 |
| `Sys/RootCauseAnalyze/propagation/` | Stage 2：事件整理、局部方向支持、受约束解码 |
| `Sys/Score/` | 根/图评分、P4 训练、实验汇总 |
| `Baseline/` | 外部 baseline 独立实现与公共 runner（见 `Baseline/README.md`） |
| `scripts/` | 实验入口与服务器环境配置（见 `scripts/README.md`） |
| `docs/` | 论文、方法、评价协议与历史材料（见 `docs/README.md`） |
| `pingmesh-propagation-labeler/` | 本地人工 DD/EE 图标注工具 |
| `tests/` | `python -m pytest` 测试 |
| `.ai/` | 任务、状态与交接摘要（非算法产物） |

`data/`、`tmp/`、`output/`、`archive/` 存放内部数据、环境与生成物，默认不入库。

## 文档入口

| 想了解 | 从这里开始 |
| --- | --- |
| 研究合同与不可协商项 | [AGENT.md](AGENT.md)、[CLAUDE.md](CLAUDE.md) |
| 全部文档分类索引 | [docs/README.md](docs/README.md) |
| 当前论文与执行材料 | [docs/conferences/WWW2027/README.md](docs/conferences/WWW2027/README.md) |
| 系统实现契约 | [docs/project_overview.md](docs/project_overview.md)、[docs/PC-STGR设计方案.md](docs/PC-STGR设计方案.md) |
| 图评价协议 | [故障传播图指标调研与最终评价方案.md](docs/conferences/WWW2027/故障传播图指标调研与最终评价方案.md) |
| 当前任务与状态 | [.ai/CURRENT_TASK.md](.ai/CURRENT_TASK.md)、[.ai/STATUS.md](.ai/STATUS.md)（本地工作区，当前尚未入库） |

## 运行入口

Windows CPU 验证环境（已建好，无需重装）：

```powershell
& tmp/baselines-venv/Scripts/python.exe -m pytest tests -q
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common --help
```

Linux/NPU 实验环境：

```bash
source scripts/common.sh
bash scripts/run_full_experiment.sh --dry-run
```

`scripts/common.sh` 是服务器路径、模型设置、NPU 卡号与默认 Top-K 的唯一来源；
用环境变量覆盖，不要直接改各 runner。完整命令见 [scripts/README.md](scripts/README.md)。

## 重要边界

本项目当前处于「实现原型与历史结果已有，评价证据待整理、论文主张待验证」阶段。
历史数字与功能测试通过**不等于**已复现的论文精度；旧 evaluator 语义与新协议尚需统一。
证据缺口、UNKNOWN 与已知实现缺陷集中记录在 [.ai/STATUS.md](.ai/STATUS.md)。
