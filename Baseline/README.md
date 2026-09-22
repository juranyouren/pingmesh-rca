# Baseline — 当前在用的实验与依赖库

当前**只有一套** baseline experiment runner。历史的多方法公共 runner 与适配层
（SkyNet / BiAn / PCMCI+ / DYNOTEARS 独立入口）已删除；它们与被 RQ1 取代的重复实现
不再维护，需要时从 git 历史取回。

## 目录

| 路径 | 角色 | 说明 |
|---|---|---|
| `RQ1/` | **ACTIVE** | 设备传播图恢复实验，当前唯一在用的 runner |
| `common/` | LIBRARY | RQ1 依赖的公共契约：输入规范化、标签校验、分折、时序、图适配 |
| `NetEventCauseDevice/` | ACTIVE | RQ1 `nec` 方法的实现 |

`common/` 不再是独立 runner（`runner.py` / `__main__.py` 已删除），只作为库被 RQ1 导入：
`common.io` / `common.schema` / `common.splits` / `common.timeseries` / `common.graph` /
`common.evaluation` / `common.synthetic`。

## 安装与运行

RQ1 使用 Python 3.10，依赖见 `RQ1/requirements.txt`：

```bash
pip install -r Baseline/RQ1/requirements.txt
```

运行入口（默认值来自 `scripts/common.sh`，无需手工传参）：

```bash
bash scripts/run_rq1.sh                 # 等价于 python -m Baseline.RQ1 run
bash scripts/run_rq1.sh --check-inputs  # 只读检查，不读 GT、不写实验目录
bash scripts/run_rq1.sh --dry-run       # 严格预检，需要 GT
```

本地只有示例数据、没有传播 GT，因此本地只能执行 `--check-inputs` 与 CPU 测试：

```bash
python -m pytest Baseline/RQ1/tests -q
```

## 输出

run 目录写入 `${PINGMESH_RESULTS}`（默认 `res/`），命名
`rq1_<condition>_<YYYYMMDD_HHMMSS>_<git-short-sha>[_NN]`，与 `scripts/common.sh` 的
`pingmesh_create_run_dir` 使用同一命名契约。目录内含 `run.json`（git 状态、源码哈希、
配置哈希、输入/标签/分折哈希）、`table.md` / `table.csv`、`summary.json`、`predictions.json`
与逐 case 预测，足以复现与审计。

完整实验协议、标签格式与指标定义见 `RQ1/README.md`。
