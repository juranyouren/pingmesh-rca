# 方案架构图 — 绘图描述与提示词

---

## 图 1：系统整体架构

### 数据流概述

Pingmesh 拨测发现丢包 → 拉取全链路拓扑（~376 台设备，每台带告警/日志/拓扑连接） → 两条并行评分线 → 融合 → 压缩为 prompt → LLM 辅助推理 → 输出根因 IP。

### 各模块详细描述

**模块 A: 数据采集**
- 输入: Pingmesh 丢包告警（source_ip, sink_ip, alarm_time 等）
- 输出: 全链路设备列表（~376 台），每台含 role, mgmt_ip, alarms[], logs[], linked_from[], linked_to[], cross

**模块 B: 拓扑 PageRank**（左侧分支）

功能：在物理拓扑图上评分——被多条异常路径共同穿越的设备得分高。

计算：
1. 从告警权重表查每台设备命中告警的最高权重
2. 结合 cross（路径交汇次数）、是否靠近 source/sink，算 personalization 向量
3. 在有向图上执行 PageRank 随机游走到收敛
4. 分数归一化到 [0,1]

图示中应标注"告警权重表"作为外部输入流入本模块。

**模块 C: 时序评分**（右侧分支）

功能：不看拓扑，只看告警发生的时间——告警越早、越集中、越密集，越像根因。

计算：
1. 从 info.alarm_time 取故障参考时间
2. Burst: 告警在 ±5min 内的比例 (w=0.40)
3. Early Bird: 首条告警在所有设备中的时间排名 (w=0.35)
4. Density: 单位时间告警密度，上限 20 条/分钟 (w=0.25)
5. 加权求和，归一化到 [0,1]

**模块 D: 得分融合**

功能：两路得分各自归一化后等权平均，得到综合分，按综合分排序输出候选 IP 列表。

输入: 模块B的 PR 得分 + 模块C的时序得分（均为 [0,1]）
输出: 候选 IP 列表，按综合分降序

**模块 E: 证据组织**

功能：将算法输出压缩为 LLM 可读的结构化 prompt。不是简单的文本拼接——去重告警名、只保留 Top-K 候选的详情、info 只取关键字段。

输入: 候选 IP 列表 + 原始设备数据 + info.json
输出: 结构化 JSON prompt（综合排名表 + 每设备告警/日志名称 + 故障概况）
压缩比: 常规 ~6000→~1500 字符 (−75%)

**模块 F: LLM 辅助推理**

功能：审核候选排名。默认信任综合分排序；当候选设备的告警名称提供明确相反证据时（如靠后的设备有硬件故障告警而靠前的只有通知类告警），调整顺序。

输入: 结构化 prompt
输出: 最终根因 IP 列表

**模块 G: 输出**

最终根因 IP，按嫌疑从高到低排列。

### 数据流图（文本描述供绘图参考）

```
                        ┌─ 告警权重表 ─┐
                        │  (外部输入)   │
                        └──────┬───────┘
                               │
  ┌────────────────────────────┼──────────────────────────────┐
  │                   数据采集 (Pingmesh 触发)                  │
  │  输入: source_ip, sink_ip, alarm_time                     │
  │  输出: 376台设备 × {role, mgmt_ip, alarms, logs,          │
  │        linked_from, linked_to, cross}                     │
  └──────────┬────────────────┬──────────────────────────────┘
             │                │
             ▼                ▼
  ┌──────────────────┐  ┌──────────────────┐
  │ 拓扑 PageRank     │  │ 时序评分          │
  │                  │  │                  │
  │ 告警权重(查表)    │  │ ref_time =       │
  │   ↓              │  │ info.alarm_time  │
  │ personalization  │  │   ↓              │
  │ + cross + 端点    │  │ Burst (0.40)     │
  │   ↓              │  │ EarlyBird (0.35) │
  │ 有向图 PageRank   │  │ Density (0.25)   │
  │   ↓              │  │   ↓              │
  │ PR得分 [0,1]      │  │ 时序得分 [0,1]    │
  └────────┬─────────┘  └────────┬─────────┘
           │                     │
           └──────────┬──────────┘
                      ▼
           ┌──────────────────┐
           │ 得分融合           │
           │ 归一化 → 等权平均  │
           │ → 综合排序         │
           │ 输出: 候选IP列表    │
           └────────┬─────────┘
                    ▼
           ┌──────────────────┐
           │ 证据组织           │
           │ 告警名去重         │
           │ Top-K 详情提取      │
           │ info 关键字段      │
           │ → 结构化 JSON      │
           │ (压缩 ~75%)       │
           └────────┬─────────┘
                    ▼
           ┌──────────────────┐
           │ LLM 辅助推理       │
           │ 默认信任综合分      │
           │ 告警语义提供补充    │
           │ 判断                │
           └────────┬─────────┘
                    ▼
           ┌──────────────────┐
           │ 根因 IP 列表       │
           └──────────────────┘
```

### 绘图要点

- B/C 两模块**左右并排**，用虚线框标出"并行评分"
- "告警权重表"作为独立方块，箭头指向 B
- 每条数据流标注数据类型（如 `PR得分 [0,1]`、`候选IP列表`、`结构化JSON`）
- E 模块旁标注压缩比 `~6000 → ~1500 chars`
- 色彩：蓝色=数据采集，绿色=算法评分，橙色=融合/组织，紫色=LLM
- 不出现任何准确率数字

### AI 绘图提示词 (英文)

```
Technical architecture diagram for a data center network root cause analysis system. Clean, modern engineering diagram style. No metrics or percentages.

FLOW (top to bottom):

1. TOP: "Pingmesh Alert" box → "Data Collection" box
   - Input: source_ip, sink_ip, alarm_time
   - Output: "376 devices: {role, mgmt_ip, alarms[], logs[], linked_from[], linked_to[], cross}"

2. SPLIT into TWO PARALLEL COLUMNS (equal width, side by side):

   LEFT COLUMN - "Topology PageRank":
   - External input arrow from "Alarm Weight Table" flowing in
   - Small blocks showing computation steps:
     a) "Lookup alarm weights per device" 
     b) "Build personalization vector (weights + cross + endpoint proximity)"
     c) "Directed graph PageRank until convergence"
   - Output labeled: "Per-device PR Score [0,1]"

   RIGHT COLUMN - "Temporal Scoring":
   - Reference time from "info.alarm_time"
   - Three horizontal sub-blocks:
     a) "Burst: proportion of alarms within +/-5min of fault time"
     b) "Early Bird: 1 / rank of device's first alarm"
     c) "Density: alarms per minute (capped)"
   - Output labeled: "Per-device Temporal Score [0,1]"

3. BOTH COLUMNS converge into "Score Fusion" box (center):
   - "Normalize each signal → Equal-weight average → Sort by combined score"
   - Output: "Candidate IP List (ranked)"

4. ARROW down to "Evidence Organization" box:
   - "Deduplicate alarm names, extract Top-K device details, keep key info fields"
   - "Compress into structured JSON prompt"
   - Small annotation: "~6000 → ~1500 chars"

5. ARROW down to "LLM-Assisted Review" box (purple/ai color):
   - "Default: trust combined ranking"
   - "Intervene only when alarm names provide clear contrary evidence"

6. ARROW down to "Root Cause IPs" output box.

VISUAL NOTES:
- Blue for data stages, green for algorithm stages, orange for fusion, purple for LLM
- Each arrow labeled with data type
- "Alarm Weight Table" as a separate small box with arrow into PageRank
- No accuracy numbers anywhere
- Clean, sparse, each box has 1-2 lines max
```

---

## 图 2：时序评分模块展开

### 描述

展开图 1 中"时序评分"模块的内部三个特征，展示每个特征的计算公式和物理含义。

### 绘图提示词 (英文)

```
Detailed diagram of the "Temporal Scoring" module. Three parallel feature computation paths, converging to a combined score.

TOP BOX: "Fault Reference Time: info.alarm_time (Pingmesh trigger timestamp)"

THREE PARALLEL PATHS (left to right):

PATH 1 - "Burst" (weight 0.40):
  Formula display: "count(|alarm_time - ref_time| <= 5min) / total_alarms"
  Visual: timeline with a vertical dashed "fault line" at center, alarm dots clustered near it
  Interpretation: "Root cause alarms concentrate near fault onset"

PATH 2 - "Early Bird" (weight 0.35):
  Formula display: "1 / rank(device_first_alarm among all devices)"
  Visual: devices sorted by first alarm time, the earliest one highlighted
  Interpretation: "Root cause alarms appear first"

PATH 3 - "Density" (weight 0.25):
  Formula display: "alarm_count / active_span_minutes (cap 20/min)"
  Visual: compact alarm cluster vs sparse spread
  Interpretation: "Root cause has denser alarm burst"

Three paths converge into:
  "Score = 0.40*Burst + 0.35*Early + 0.25*Density"
  "→ Normalize to [0,1]"

BOTTOM NOTE (small, italic):
  "Physical observation: in ~3/4 of DCN failures, root devices alarm earlier and more concentrated than downstream victims."
```

---

## 图 3：证据组织模块 — 压缩前后对比

### 描述

并排对比旧方式（原始 JSON 拼接，撑爆上下文）与新方式（结构化组织，始终在窗口内）。

### 绘图提示词 (英文)

```
Before/After comparison diagram for prompt construction.

LEFT SIDE (red tint, marked with X):
Title: "Raw Concatenation"
Three large text blocks:
  1. "Topo skill output: ~4900 chars (full device data dump)"
  2. "Temporal skill output: ~1100 chars (all device scores)"
  3. "Info.json + Nodes.json: full dump"
Below: "Total: ~6000 chars (normal case) / ~26000+ chars (alarm storm)"
Red arrow pointing right with text: "Exceeds LLM context → truncated"

RIGHT SIDE (green tint, marked with checkmark):
Title: "Evidence Organization"
Three compact blocks:
  1. "Combined Ranking Table: rank | IP | combined_score | PR | temporal | key_alarms"
  2. "Fault Summary: alarm_name, source/sink IP, alarm_time, scenario"
  3. "Candidate Detail: per-device alarm names (deduplicated) + topology neighbors"
Below: "Total: ~1500 chars (constant, independent of alarm volume)"
Green checkmark: "Always fits in context window"

Center arrow: "75-93% reduction"
```

---

## 图 4：告警权重表流程

### 描述

补充图 1 中"告警权重表"作为外部输入的来源——如何从标注数据中学习告警权重，并用于 PageRank personalization。

### 绘图提示词 (英文)

```
Small supporting diagram: "Alarm Weight Table Construction and Usage."

Two connected sub-diagrams:

LEFT - "Weight Learning" (offline):
  "Labeled cases (146)" → "Count: how often does each alarm type appear on a root-cause device?" → "Weight = P(root_cause | alarm_name) * 100" → "Alarm Weight Table (JSON)"

RIGHT - "Weight Usage" (online, feeds into PageRank):
  "Alarm Weight Table" → "For each device, find max weight among its triggered alarms" → "Personalization vector for PageRank" → "Device initial score"

Arrow from LEFT to RIGHT labeled: "Loaded at inference time"
```

---

## 使用说明

- **Mermaid 图**直接嵌入 Markdown，GitHub 自动渲染。
- **英文提示词**可直接粘贴到 AI 绘图工具（DALL-E, Midjourney, Stable Diffusion）生成论文插图。
- 每张图的数据类型、流向均已在描述中标注。
