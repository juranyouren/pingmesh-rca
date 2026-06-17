# Pingmesh RCA 项目进展报告

> 更新时间: 2026-06-17
> 状态: 数据泄漏已修复，重新消融

---

## 一、方案

```
Pingmesh 告警 → ┬─ Topo: 有向 PageRank ─┐
                └─ Temporal: 时序评分   ─┤
                                         ↓
                                  等权融合 (综合分)
                                         ↓
                                  证据组织 (结构化 JSON)
                                         ↓
                                  LLM 辅助推理
                                         ↓
                                    最终根因 IP
```

---

## 二、消融结果（146 例人工标注，2026-06-17）

```
run_full_ablation.sh — 移除 label.json 泄漏后重新评测
```

| 组合 | Top-1 | Top-3 | Top-5 | 
|------|-------|-------|-------|
| **[1,2] topo+temporal (llm 权重)** | **55.94%** | 60.14% | 64.34% |
| [1,2] topo+temporal (manual 权重) | 54.55% | 58.04% | 64.34% |
| [2] temporal only | 49.65% | 58.04% | 58.74% |
| [1] topo only (manual 权重) | 42.66% | 54.55% | 60.14% |
| [1] topo only (llm 权重) | 39.16% | 51.75% | 60.84% |

**原始 JSON**：
```json
{
  "timestamp": "20260617_165827",
  "total_combinations": 6,
  "results": [
    {"tag":"topo_temporal","skills":"1 2","weight_source":"llm","total_cases":143,"top1":55.94,"top2":58.74,"top3":60.14,"top4":63.64,"top5":64.34},
    {"tag":"topo_temporal","skills":"1 2","weight_source":"manual","total_cases":143,"top1":54.55,"top2":58.04,"top3":58.04,"top4":61.54,"top5":64.34},
    {"tag":"temporal","skills":"2","weight_source":"llm","total_cases":143,"top1":49.65,"top2":57.34,"top3":58.58,"top4":58.04,"top5":58.74},
    {"tag":"temporal","skills":"2","weight_source":"manual","total_cases":143,"top1":49.65,"top2":57.34,"top3":58.04,"top4":58.74,"top5":59.44},
    {"tag":"topo","skills":"1","weight_source":"manual","total_cases":143,"top1":42.66,"top2":51.75,"top3":54.55,"top4":57.34,"top5":60.14},
    {"tag":"topo","skills":"1","weight_source":"llm","total_cases":143,"top1":39.16,"top2":48.95,"top3":51.75,"top4":58.74,"top5":60.84}
  ]
}
```

### 分析

**1. 数据泄漏的影响**

之前的 87.41% 和 76.22% 已被证明是数据泄漏导致的虚假高分。`temporal_score.py` 中的 `_read_label_timestamps()` 从 `label.json`（标注文件）读取根因设备的时间戳，只给根因设备补充时间数据，非根因设备保持为空。

移除后：temporal only 从 76.22% → 49.65%，topo+temporal 从 87.41% → 55.94%。

**2. 当前各信号的定位**

| 信号 | Top-1 | 角色 |
|------|-------|------|
| topo only | 39-43% | PageRank 是稳定基础信号 |
| temporal only | 49.65% | 时序仍有价值（比随机 0.3% 强得多） |
| topo+temporal | 55.94% | 两个信号互补，+6pp over temporal alone |

时序单独 ~50% 说明：去掉泄漏后，仍有一半的 case 中时序正确——不是因为从 label 偷了答案，而是因为节点 alarms/logs 中的时间戳信号确实有效。

**3. 互补效应仍然成立**

topo+temporal (55.94%) > temporal (49.65%)，+6.3pp。拓扑信号在约 9 个 case 中纠正了时序的错误，与之前的 "topo 补上 ~13 个 case" 结论定性一致，绝对值对齐到真实基线。

**4. 权重来源对比**

- llm 权重在组合中略优 (55.94 vs 54.55)，但差距不大
- topo only 上 manual 权重反而更优 (42.66 vs 39.16) — 说明 llm 权重可能在某些告警上过稀疏

**5. Topo 大幅提升的原因（vs 旧消融 14-17%）**

旧消融中的 topo only 是 14-17%（同样是 146 例新数据）。但旧消融用的是**全链路文件中 topo 执行器的原始排名**（文本表），而新消融改为 `_score_topo` 归一化函数。

原因待确认：两点变化可能同时贡献——(1) 评分函数从 executor 原始输出改为统一 `_score_topo`；(2) 权重文件不同。

---

## 三、LLM 重排效果

| 评测层 | Top-1 | Top-3 | Top-5 | 说明 |
|--------|-------|-------|-------|------|
| skill_evaluation | **___** | **___** | **___** | 待回填数据后重跑 |
| llm_evaluation | **___** | **___** | **___** | 待跑 |
| 增益 | **___** | | | |

---

## 四、待办

| 优先级 | 任务 | 状态 |
|--------|------|------|
| P0 | restore_alarms_from_labels — 回填 label→全链路 | ⏳ 脚本已就绪 |
| P0 | 回填后重跑 run_full_ablation + run_inference | ⏳ |
| P1 | LLM 前置告警打分 (llm_alarm_scorer) | ⏳ |
| P2 | 调 K（3/5/10） | ⏳ |
| P2 | NIKA 公开数据集 | ⏳ |
