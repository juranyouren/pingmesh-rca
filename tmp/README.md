# tmp — 诊断/预处理脚本

服务器端运行，输出作为分析数据源。

| 脚本 | 用途 |
|------|------|
| `diagnose_pipeline.py` | 候选集大小 / 初筛缩减 / 数据泄漏 三合一诊断 |
| `perceive_and_filter.py` | pingmesh_extend 数据感知 + 过滤，输出 nodes_extend |
| `preprocess_nodes.py` | nodes 数据预处理，同 csn 合并互补缺失键 |
| `restore_alarms_from_rootcause.py` | 从 rootcause_analysis 回填告警到 alarm_list/log_list |
| `restore_alarms_from_labels.py` | 从 label.json 回填告警到全链路文件（旧） |
| `compare_all.py` / `compare_paths.py` | 消融 vs LLM 推理 skill_ips 一致性诊断 |
