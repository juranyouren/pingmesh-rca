# Baseline 参数入口

当前只有一套在用的 baseline 实验（RQ1），因此本目录只保留 `rq1.json`。

| 文件 | 用途 |
|---|---|
| `rq1.json` | RQ1 方法参数：`timeorder` / `nec` / `pcmci` / `thp` / `ours` 各一段配置 |

`Baseline/RQ1/runner.py` 在启动时校验：配置对象的键必须是已知方法名，出现未知键直接报错。
`pcmci` 段的 `require_coverage` 可被 `--pcmci-coverage {config,strict,record-count}` 覆盖，
被覆盖时结果表、配置与方法名都会显式记录所用口径。

`Baseline/NetEventCauseDevice/default_config.json` 由 RQ1 的 `nec` 方法直接读取，因此留在
该方法自己的目录内，避免两份默认值漂移。

本目录是代码验收时的默认配置，不是已经经验证选优的论文配置。正式实验应把所选配置复制到
实验输出目录，先在训练侧冻结，再保存 cases/groups/folds/labels 的版本及哈希；禁止用测试效果
挑选阈值或窗口。
