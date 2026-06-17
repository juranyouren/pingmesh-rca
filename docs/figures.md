# 方案架构图

---

## 图 1：系统整体架构

### 描述

一张简洁的流程图，从左到右或从上到下，5个模块。不要文字冗长，用图标和简短标签。

### 数据流

```
[告警输入] → [拓扑评分] ↘
                        → [融合] → [证据组织] → [LLM推理] → [输出IP]
[告警输入] → [时序评分] ↗
```

### 各模块

**模块 1: 拓扑评分 (Topo)**
- 图上做 PageRank，利用告警权重 + 拓扑交汇度
- 输出: 每设备 PR 得分

**模块 2: 时序评分 (Temporal)**
- 三特征: 集中度 + 最早+ 密度
- 输出: 每设备时序得分

**模块 3: 融合**
- 两路得分归一化后等权平均
- 输出: 综合排名

**模块 4: 证据组织**
- 排名 + 告警名 + 关键字段 → 结构化 prompt
- 标注: 常规 ~1500 字符

**模块 5: LLM 辅助推理**
- 默认信任融合排名，仅在告警语义提供明确相反证据时重排
- 输出: 最终 IP 列表

### 绘图提示词 (英文)

```
Simple technical architecture diagram. Minimal text, clean lines.

Flow: 5 boxes, left to right or top to bottom.

Box 1 (left): "Input"
  Icon: bell + network topology
  Sublabel: "Device alarms + topology"

SPLIT into two parallel boxes:

Box 2a (upper): "Topology Scoring"
  Sublabel: "PageRank + alarm weights + cross-path"
  Output arrow: "→ PR scores"

Box 2b (lower): "Temporal Scoring"  
  Sublabel: "Burst · EarlyBird · Density"
  Output arrow: "→ Temporal scores"

Two arrows converge to:

Box 3 (center): "Fusion"
  Sublabel: "Normalize → weighted avg → rank"
  Output arrow: "→ Combined ranking"

Box 4: "Evidence Packaging"
  Sublabel: "Compact structured prompt (~1500 chars)"

Box 5 (right): "LLM Review"
  Sublabel: "Verify ranking via alarm semantics"
  Output arrow: "→ Root cause IPs"

Color scheme: blue=input, green=scoring, orange=fusion, purple=LLM.
No metrics. No percentages. Clean modern tech-diagram style.
```

---

## 图 2：时序评分展开

### 绘图提示词 (英文)

```
Simple diagram showing 3 parallel sub-features of temporal scoring.

Top label: "Fault Reference Time (info.alarm_time)"

Three horizontal panels side by side:

Panel 1: "Burst"
  "Proportion of alarms within ±5min of fault time"
  Small timeline icon showing dots concentrated near center line

Panel 2: "Early Bird"  
  "1 / rank of device's first alarm among all devices"
  Small podium icon with #1 highlighted

Panel 3: "Density"
  "Alarms per minute (capped at 20/min)"
  Dense cluster vs sparse dots

Three arrows converge:
  "Score = 0.40·Burst + 0.35·Early + 0.25·Density"
  "→ Normalize to [0,1]"

Clean, minimal. Orange/amber color scheme.
```

---

## 图 3：证据组织 — 压缩前后对比

### 绘图提示词 (英文)

```
Before/After comparison. Two columns.

LEFT (red, marked X):
  "Raw JSON concatenation"
  3 large blocks: "Topo output (~5000 chars)" | "Temporal output (~1100 chars)" | "Full info dump"
  Red arrow off-screen: "Exceeds context window"

RIGHT (green, marked ✓):
  "Evidence Packaging"
  3 compact blocks: "Ranked table" | "Key info fields" | "Alarm names (dedup)"
  Green checkmark: "~1500 chars, fits in window"

Center arrow between columns: "75-93% reduction"

Simple comparison style. Red/green coding.
```
