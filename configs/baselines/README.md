# Baseline 参数入口

参数文件由各方法目录维护，公共 runner 的 `--config` 直接读取对应 JSON，避免两份默认值漂移：

| 方法 | 冻结候选配置 |
|---|---|
| skynet | `Baseline/SkyNetVoting/default_config.json` |
| bian | `Baseline/BiAnAdapt/config.json` |
| nec | `Baseline/NetEventCauseDevice/default_config.json` |
| pcmci | `Baseline/PCMCIPlus/default_config.json` |
| dynotears | `Baseline/DYNOTEARS/default_config.json` |

公共协议 v1：raw 触发窗口前后各 300 秒；规范化输入自己的窗口优先；图适配 `device_greedy_v1`；默认 group split 种子 20260909；单事故独立推断，NEC 每折重训；图方法当前共同采用 10 秒 log1p(count) 序列、覆盖未知不补零；评分保留失败、使用显式已知标签范围。

这是代码验收时的默认配置，不是已经经验证选优的论文配置。正式实验应把所选配置复制到实验输出目录，先在训练侧冻结，再保存 cases/groups/folds/labels 的版本及哈希；禁止用测试效果挑选阈值或窗口。

统一命令、输入形态和完整工作流见 `Baseline/README.md`。`Baseline.common.synthetic` 产生的 `nec-smoke.json` 仅为快速接口检查，不能作为正式训练设置引用。
