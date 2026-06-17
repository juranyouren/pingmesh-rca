# 方案架构图 — 绘图描述与提示词

---

## 图 1：系统整体架构

### 数据流（逐箭头标注）

```
告警权重表 ────────────────┐
(离线学习, JSON)           │
                          ▼
  Pingmesh 告警 ──→ [数据采集] ──→ 全链路设备数据 ──┬──→ [拓扑 PageRank] ──→ PR 排名列表
                         (role, mgmt_ip,           │                         [{ip, score, role, cross}, …]
                          alarms, logs,            │
                          linked_from/to, cross)   │
                                                   ├──→ [时序评分] ──→ 时序排名列表
                                                   │                   [{ip, score, burst, early, density}, …]
                                                   │
                                                   └──→ [告警权重表] ← 查表: 哪些告警是高危的?
                                                         │
                                                         ▼
                                                    重要告警列表
                                                    [{ip, alarms_matched, …}, …]
```

```
                               PR 排名列表 ──────────────────────────────┐
                               时序排名列表 ────────────────────────────┐│
                               融合排名列表(综合分) ───────────────────┐││
                               重要告警列表 ────────────────────────┐ │││
                                                                  │ │││
                                                                  ▼ ▼▼▼
                                                           [证据组织 ──→ 结构化 Prompt]
                                                                  │
                                                                  ▼
                                                           [LLM 辅助推理]
                                                                  │
                                                                  ▼
                                                           最终 IP 列表
```

### 各模块详解

**模块 A: 数据采集**

输入: Pingmesh 拨测丢包告警 → 拉取该次故障涉及的全部网络设备。

输出: 每台设备含 `role`, `mgmt_ip`, `alarms[]`（告警名称+时间戳）, `logs[]`, `linked_from[]`（邻接上游）, `linked_to[]`（邻接下游）, `cross`（路径交汇次数）。

这份数据同时送往三个方向：拓扑评分、时序评分、告警匹配。

---

**模块 B: 拓扑 PageRank**

在物理拓扑图上执行 Personalized PageRank。personalization 向量由两部分初始化：(1) 从告警权重表查询该设备命中的最高权重告警；(2) 结合 `cross`（路径交汇次数）和与受损端点（source/sink IP）的邻近度加分。

随机游走收敛后，每设备得到一个 PageRank 分数，归一化到 [0,1]。

**输出**: `PR 排名列表` — 每个设备一个条目 `{ip, pr_score, role, cross}`，按分数降序。

---

**模块 C: 时序评分**

不依赖拓扑，仅根据告警发生时间判断。以 `info.alarm_time` 为故障参考时间，计算三个特征后加权求和，归一化到 [0,1]：

- **Burst** (0.40): 告警在参考时间 ±5 分钟内的比例
- **Early Bird** (0.35): 设备首条告警在所有设备中的时间排名倒数
- **Density** (0.25): 单位时间告警密度（上限 20 条/分钟）

**输出**: `时序排名列表` — 每个设备一个条目 `{ip, temporal_score, burst, early, density}`，按分数降序。

---

**模块 D: 得分融合**

将 PR 得分和时序得分各自归一化后等权平均，得到综合分。

**输出**: `融合排名列表` — 每个设备一个条目 `{ip, combined_score, role}`，按综合分降序。

---

**模块 E: 告警匹配（确定"重要告警"）**

**如何确定"重要"**：将设备上实际触发的告警名称与**告警权重表**逐一匹配。权重表是离线从标注数据中学到的——每条告警类型的权重 = `P(根因设备 | 该告警出现) × 100`。命中权重表的告警即为"重要告警"。权重越高的告警越指向根因。

告警权重表独立于单次推理——146 例标注数据上统计一次，推理时直接查表。

**输出**: `重要告警列表` — Top-K 候选设备上命中权重表的告警名称 `{ip, matched_alarms[], max_weight}`，以及未命中但仍在设备上的全部告警名称（供 LLM 参考）。

---

**模块 F: 证据组织**

将四份列表（PR 排名、时序排名、融合排名、重要告警 + 全量告警名）组织为结构化 JSON，在同一批候选 IP 上对齐。同时附带故障概况（info.json 关键字段）。

**输出**: 结构化 JSON — 包含 `combined_score_rankings`（综合排名）、`topo`（PR 得分）、`temporal`（时序得分）、`devices`（每设备告警名 + 命中高优告警 + 拓扑邻居）。

压缩比：~6000 → ~1500 字符，大小与告警量解耦。

---

**模块 G: LLM 辅助推理**

接收结构化 Prompt。**默认信任融合排名**——综合分差距大的情况下不做干预。仅在候选设备的重要告警名称提供明确相反证据时（如排名靠后的设备有"光模块硬件故障"，而靠前的只有"端口 Up/Down 通知"），调整顺序。

**输出**: 最终 IP 列表（嫌疑从高到低）。

---

### 数据流图（文本，供绘图参考）

```
                          ┌── 告警权重表 ──┐
                          │ (离线统计, JSON) │
                          └───────┬────────┘
                                  │
  ┌───────────────────────────────┼──────────────────────────────────┐
  │ Pingmesh 告警 ──→ 数据采集 ──┤                                   │
  │ (source_ip, sink_ip,          │                                   │
  │  alarm_time)                  │                                   │
  │                               ▼                                   │
  │              全链路设备数据 (role, mgmt_ip, alarms[], logs[],      │
  │              linked_from[], linked_to[], cross)                    │
  └───────────────────────────────┬──────────────────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
              ▼                   ▼                   ▼
  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
  │  拓扑 PageRank    │ │    时序评分       │ │   告警匹配        │
  │                  │ │                  │ │                  │
  │ 查告警权重表      │ │ ref_time =       │ │ 设备告警名        │
  │   ↓              │ │   info.alarm_time│ │   ↓              │
  │ personalization  │ │   ↓              │ │ 查告警权重表      │
  │ + cross + 端点    │ │ Burst   (0.40)   │ │   ↓              │
  │   ↓              │ │ Early   (0.35)   │ │ 命中 → 重要告警   │
  │ 有向图 PageRank   │ │ Density (0.25)   │ │ 未命中 → 普通告警 │
  │   ↓              │ │   ↓              │ │                  │
  │ 归一化 [0,1]      │ │ 归一化 [0,1]      │ └────────┬─────────┘
  └────────┬─────────┘ └────────┬─────────┘           │
           │                    │                     │
           ▼                    ▼                     │
  PR 排名列表            时序排名列表                   │
  [{ip, score,          [{ip, score,                  │
    role, cross}, …]      burst, early,               │
                          density}, …]                │
           │                    │                     │
           └────────┬───────────┘                     │
                    ▼                                 │
           ┌──────────────────┐                      │
           │ 得分融合          │                      │
           │ 等权平均 → 综合分  │                      │
           └────────┬─────────┘                      │
                    │                                │
                    ▼                                │
           融合排名列表                               │
           [{ip, combined_                           │
             score, role}, …]                        │
                    │                                │
                    │    ┌───────────────────────────┘
                    │    │  重要告警列表
                    │    │  [{ip, matched_alarms,
                    │    │    max_weight}, …]
                    │    │
                    ▼    ▼
           ┌──────────────────┐
           │ 证据组织          │
           │                  │
           │ 四份列表按 IP 对齐 │
           │ → 结构化 JSON     │
           │                  │
           │ 输入:             │
           │  • PR排名列表      │
           │  • 时序排名列表    │
           │  • 融合排名列表    │
           │  • 重要告警列表    │
           │  • 全量告警名      │
           │  • info 关键字段   │
           │                  │
           │ 输出: 结构化Prompt │
           │ (~1500 chars)     │
           └────────┬─────────┘
                    ▼
           ┌──────────────────┐
           │ LLM 辅助推理      │
           │                  │
           │ 默认信任融合排名  │
           │ 告警语义提供      │
           │ 补充判断          │
           └────────┬─────────┘
                    ▼
           最终 IP 列表
           [ip1, ip2, ip3, …]
```

### 绘图要点

- 四条数据流**平行进入**证据组织模块，每条标注数据类型
- "告警权重表"出现两次：一次流入拓扑 PageRank（做 personalization），一次流入告警匹配（筛选重要告警）——用同一方块或用两个标注同源的方块均可
- "重要告警"的确定逻辑用一个小方框展开：设备告警名 → 查权重表 → 命中为"重要"，未命中为"普通"
- 箭头标注数据类型，如 `PR 排名列表 [{ip, score, role, cross}, …]`
- LLM 输出是一条新的 IP 列表（第四条），颜色与三条算法列表不同
- 不出现任何准确率数字

### AI 绘图提示词 (英文)

```
Technical architecture diagram for a data center network Root Cause Analysis system. Clean engineering style. No metrics/percentages. All arrows labeled with data types.

LAYOUT (top to bottom, with parallel branches):

══════════════ TOP SECTION ═══════════════

1. "Pingmesh Alert" box → "Data Collection" box
   Output arrow labeled: "Device data: {role, mgmt_ip, alarms[], logs[], linked_from[], linked_to[], cross}"

2. "Alarm Weight Table" as a standalone box (bottom-left of data collection, connected with arrow). Label: "Learned offline: P(root_cause | alarm_name) × 100"

══════════════ MIDDLE SECTION (3 parallel columns) ═══════════════

Data collection output fans out to THREE parallel modules:

LEFT COLUMN - "Topology PageRank":
  Steps: "Lookup alarm weight per device" → "Build personalization vector (weight + cross + endpoint proximity)" → "Directed graph PageRank → normalize [0,1]"
  Alarm weight table arrow flows in here
  OUTPUT arrow going right: "PR Ranking List: [{ip, score, role, cross}, ...]"

MIDDLE COLUMN - "Temporal Scoring":
  Steps: "ref_time = info.alarm_time" → three sub-boxes: "Burst (0.40): ±5min concentration" / "Early Bird (0.35): 1/rank of 1st alarm" / "Density (0.25): alarms/min (cap 20)" → "Weighted sum → normalize [0,1]"
  OUTPUT arrow going right: "Temporal Ranking List: [{ip, score, burst, early, density}, ...]"

RIGHT COLUMN - "Alarm Matching":
  Steps: "Device alarm names" → "Lookup in Alarm Weight Table" → "Match = important alarm / No match = ordinary"
  OUTPUT arrow going right: "Important Alarm List: [{ip, matched_alarms, max_weight}, ...]"

BETWEEN middle and bottom: "Score Fusion" box that takes PR and Temporal lists, outputs "Combined Ranking List: [{ip, combined_score, role}, ...]"

══════════════ BOTTOM SECTION ═══════════════

Four data flows (4 arrows) enter "Evidence Organization" box:
  Incoming arrows labeled: "PR Ranking List", "Temporal Ranking List", "Combined Ranking List", "Important Alarm List + all alarm names"
  Inside: "Align by IP → Structured JSON prompt"
  Small annotation: "~6000 → ~1500 chars"

Arrow down to "LLM-Assisted Review" box:
  "Default: trust combined ranking. Intervene only when important alarms provide clear contrary evidence."

Arrow down to output box: "Root Cause IP List [ip1, ip2, ...]" (different color from algorithm lists)

STYLING:
- Blue: data stages | Green: algorithm stages | Orange: fusion/organization | Purple: LLM | Red: final output
- Each algorithm output box should visually show it's a ranked LIST (small table icon or bracket notation)
- "Alarm Weight Table" box connects to BOTH PageRank module AND Alarm Matching module
- All arrows labeled with data types, not just connection lines
- No accuracy numbers anywhere
```
