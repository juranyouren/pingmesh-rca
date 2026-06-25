# tmp — 诊断/预处理脚本

服务器端运行，输出作为分析数据源。

| 脚本 | 用途 |
|------|------|
| `diagnose_pipeline.py` | 候选集大小 / 初筛缩减 / 数据泄漏 三合一诊断 |
| `perceive_and_filter.py` | pingmesh_extend 数据感知 + 过滤，输出 nodes_extend |
| `restore_alarms_from_rootcause.py` | 从 rootcause_analysis 回填告警到 alarm_list/log_list |
| `restore_alarms_from_labels.py` | 从 label.json 回填告警到全链路文件（旧） |

> RAW 合并 + 校验 + 提取 NODE 数据请用 `Sys/Preprocess/Preprocessor.py`（整合了原 `preprocess_nodes.py` 和 `perceive_and_filter.py` 的功能）。
| `compare_all.py` / `compare_paths.py` | 消融 vs LLM 推理 skill_ips 一致性诊断 |
