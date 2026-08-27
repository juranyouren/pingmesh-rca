# 论文流程图统一绘图风格与 2stage 提示词

更新日期：2026-08-17  
用途：论文流程图、系统架构图和模块说明图的统一视觉母版。除非单次任务明确要求其他风格，后续绘图均使用本文的“固定风格母版提示词”。

## 1. 参考图的风格总结

### 1.1 整体定位

- 论文级系统架构图，而不是宣传海报或产品 UI；
- 超宽横向画布，信息严格从左向右流动；
- 每个主要阶段放入独立的纵向圆角大框，阶段之间使用水平实线箭头连接；
- 画面信息丰富，但依靠规则对齐、模块分区和大面积留白保持清楚；
- 采用接近手绘感的简洁矢量线稿，但结构、间距和对齐必须精确。

### 1.2 形状语言

- 外层阶段：白底、黑色细描边、较大圆角矩形；
- 内层证据组或候选组：黑色虚线圆角矩形；
- 普通过程框：白底、黑色细描边、轻微圆角；
- 决策节点：菱形，使用橙色描边；
- 设备节点：白色小圆，内部为极简网络设备符号；
- 文档、告警、时钟、用户、数据库等均采用统一单色线性图标；
- 主流程箭头：黑色实线、实心三角箭头，方向明确；
- 不使用阴影、渐变、立体效果、照片纹理或大面积色块。

### 1.3 配色规则

只允许以下视觉层级：

- 主色：近黑色 `#111111`，用于文字、边框、图标和主流程；
- 背景：白色或极浅暖灰 `#FCFCFB`；
- 辅助灰：`#E9E9E9`，仅用于时间窗、次要区域或极轻的层次区分；
- 拓扑/结构证据蓝：`#1457FF`；
- 时间/根因/关键决策橙红：`#FF4B1F`。

蓝色与橙色只用于强调少量关键节点、边框、排名第一项或决策门，不能铺满整个模块。禁止引入紫、绿、青等额外强调色。

### 1.4 线条与字体

- 外层框线约 2 px，内部框线约 1.5–2 px；
- 所有图标和拓扑边使用同一线宽体系；
- 字体使用清晰的现代无衬线字体，接近 Arial、Helvetica 或 Inter；
- 阶段标题粗体、居中，允许分成两行；
- 小模块标题使用中等粗体；正文使用常规字重；
- 英文标签采用 Title Case，短语化表达，避免长段落；
- 不使用斜体、艺术字体、手写字体或衬线字体；
- 最小字号必须保证缩放到论文双栏页面后仍可读。

### 1.5 排版与信息密度

- 画布比例约为 `1.9:1`，推荐 `2400 × 1250` 或更高分辨率；
- 四至五个主阶段横向排列，重要阶段可以更宽；
- 每个阶段内部采用小型图形叙事，而不是纯文本清单；
- 内容与外框保持充分内边距；
- 箭头尽量走水平或垂直正交路径，避免交叉、回折和穿过文字；
- 同类卡片等宽、等高、等间距；
- 图例放在相关模块内部，不单独占用大区域；
- 允许用省略号表示 Top-K 或重复结构，但不能制造视觉拥挤。

## 2. 固定风格母版提示词

后续生成任何同系列流程图时，把下面整段作为提示词的固定前缀，再追加具体图内容。

```text
Create a publication-ready scientific system architecture diagram in an ultra-wide landscape canvas, approximately 1.9:1 aspect ratio, at least 2400 × 1250 pixels. Use a clean, precise monoline vector style with a very subtle hand-drawn technical-diagram character. The visual language must match a rigorous computer-networking research paper figure.

Use a white or very light warm-gray background (#FCFCFB). Organize the workflow strictly from left to right. Place every major stage inside a tall white rounded rectangle with a thin near-black outline and generous inner padding. Use dashed rounded rectangles for evidence groups, candidate groups, or optional substructures. Use small white rounded cards for individual items. Use orange-outlined diamonds only for decision gates. Connect major stages with straight black arrows with solid triangular arrowheads. Keep arrows horizontal or orthogonal whenever possible and never let arrows cross labels.

Use a restricted color palette only: near-black #111111 for text, icons, borders, and primary arrows; electric blue #1457FF for topology, structural evidence, or selected propagation structure; vermilion orange #FF4B1F for temporal evidence, root-cause emphasis, uncertainty gates, and the highest-priority item; very light gray #E9E9E9 only for subtle secondary regions. Do not introduce any additional accent colors. Use color sparingly: most of the figure must remain black and white.

Use consistent monoline outline icons for network devices, topology nodes, documents, alarms, clocks, users, databases, and checks. Use modern sans-serif typography similar to Arial, Helvetica, or Inter. Make major stage titles bold, centered, and optionally two lines. Use medium-weight short labels and regular-weight annotations. All text must be correctly spelled, horizontally aligned, and readable at paper scale.

Maintain precise grid alignment, balanced whitespace, consistent corner radii, uniform line weights, and a calm academic information density. Prefer small visual diagrams over long paragraphs. The final result must look like one coherent vector figure created by a professional scientific illustrator.

Do not use gradients, shadows, glossy effects, 3D rendering, photorealism, isometric perspective, dark backgrounds, decorative textures, large colored fills, cartoon characters, extra colors, serif fonts, tiny unreadable text, overlapping elements, curved decorative arrows, or malformed labels.
```

## 3. 2stage 路径重建流程图提示词

这张图作为原 RCA 流程图之后的独立图，只表达三个核心动作：从全拓扑圈定候选范围、将无向边变成概率关系、让多个根因分别解释概率图并排序。不要加入信任门、人工复核、告警文档卡片或其他工程细节。

下面的提示词已经包含固定风格和具体内容，可直接用于图像生成：

```text
Create a publication-ready scientific system architecture diagram in an ultra-wide landscape canvas, approximately 1.9:1 aspect ratio, at least 2400 × 1250 pixels. Use a clean, precise monoline vector style with a very subtle hand-drawn technical-diagram character. The visual language must match a rigorous computer-networking research paper figure.

Use a white or very light warm-gray background (#FCFCFB). Organize the workflow strictly from left to right. Place each of the three major stages inside a large white rounded rectangle with a thin near-black outline and generous inner padding. Connect the three panels with straight black arrows with solid triangular arrowheads. Use black dashed rounded boundaries for selected regions inside a topology. Keep arrows horizontal or orthogonal whenever possible and never let arrows cross labels.

Use a restricted color palette only: near-black #111111 for text, icons, topology nodes, borders, and primary arrows; electric blue #1457FF for the selected connected subgraph and probability-directed edges; vermilion orange #FF4B1F for suspected root-cause devices and the highest-ranked root explanation; very light gray #E9E9E9 for de-emphasized topology and disconnected/no-propagation states. Do not introduce any additional accent colors. Use color sparingly: most of the figure must remain black and white.

Use modern sans-serif typography similar to Arial, Helvetica, or Inter. Make the three stage titles bold and centered. Use medium-weight short labels and regular-weight probability annotations. All text and numeric probability values must be correctly spelled, horizontally aligned, and readable at paper scale. Maintain precise grid alignment, balanced whitespace, consistent corner radii, and uniform line weights. The same device identities and local topology layout must remain visually recognizable across all three panels so that viewers can track the transformation from one graph to the next.

Draw exactly three large panels, arranged left to right, with equal height. Panel 1 is moderately wide, Panel 2 is the widest, and Panel 3 is moderately wide. Use one bold right-pointing arrow between Panel 1 and Panel 2, and another between Panel 2 and Panel 3.

PANEL 1 — title: “Incident-Conditioned Subgraph Selection”.
Show a large complete Pingmesh device topology with approximately 25–35 small circular network-device nodes arranged as a multi-tier data-center network. Use thin black undirected links and no arrowheads. Most devices are ordinary white circles with black outlines. Mark exactly three suspected root-cause devices with orange outlines and short labels “R1”, “R2”, and “R3”; make R1 slightly more prominent with a double orange outline. Inside the full topology, enclose a connected subset of approximately 9–12 devices with one irregular but clean blue dashed boundary. Highlight the nodes and undirected links inside this boundary in blue, while all topology outside it remains light black or gray. The blue region must be visibly connected and must include all three orange suspected root devices. Add a small blue label beside the boundary: “Connected Undirected Subgraph”. Add a tiny legend at the bottom: orange outlined node “Suspected Root Cause”; blue dashed boundary “Affected Candidate Region”. The visual story must clearly communicate: select one connected undirected subgraph from the complete Pingmesh topology.

PANEL 2 — title: “Probabilistic Edge Relation Graph”.
Redraw only the selected connected undirected subgraph from Panel 1, using the same node identities and approximately the same local arrangement. For every undirected adjacency {A,B}, represent the three mutually exclusive edge states: P(A→B), P(B→A), and P(Disconnected), where “Disconnected” means no fault-propagation relation in this incident, not physical topology disconnection.

Show probabilities directly beside each edge using compact three-part labels in this exact visual form: “→ 0.65   ← 0.20   × 0.15”. Use the arrow pointing from the first endpoint toward the second endpoint for the first value, the opposite arrow for the second value, and a small × symbol for the no-propagation value. Every triplet must sum to 1.00. Use varied realistic examples such as “→ 0.70   ← 0.18   × 0.12”, “→ 0.24   ← 0.61   × 0.15”, and “→ 0.12   ← 0.08   × 0.80”.

Visually encode the most likely state while retaining all three numbers: draw a blue directional arrow when one propagation direction has the highest probability; use line thickness proportional to that direction’s probability; draw a light gray dotted connection with a small × at its center when P(Disconnected) is highest; use two thin opposing arrows when the two direction probabilities are close. Keep the three suspected root nodes orange. Do not remove low-probability states from the numeric labels. Add a compact legend at the bottom with three entries: “Directional Probability”, “Reverse Probability”, and “No Propagation”. Add the small caption “For each physical edge: P(A→B) + P(B→A) + P(Disconnected) = 1”. The visual story must clearly communicate: the undirected candidate subgraph becomes a probabilistic directed relation graph before any root is fixed.

PANEL 3 — title: “Root-Conditioned Explanation Ranking”.
Show a vertical ranked list of three root explanations, each inside a rounded white card. Every card contains a miniature directed acyclic graph derived from the same probabilistic graph in Panel 2, with arrows spreading outward from its assumed orange root. The selected paths and edge directions should differ between candidates because each candidate explains the probabilistic graph from a different root.

The first card is outlined in orange and labeled “1   Root R2   Final Score 0.83”. Its miniature DAG should explain most high-probability directed edges with few disconnected or reversed choices. Add exactly two component scores beneath it: “Stage 1 Score 0.72” and “Explanation Score 0.94”.

The second card is labeled “2   Root R1   Final Score 0.70”, with “Stage 1 Score 0.90” and “Explanation Score 0.50”.

The third card is labeled “3   Root R3   Final Score 0.49”, with “Stage 1 Score 0.60” and “Explanation Score 0.38”.

At the top of Panel 3, above the ranked cards, place two compact formula-like captions: “Explanation Score = Explained Edge Probability / Total Active Edge Probability” and “Final Score = α · Stage 1 Score + (1 − α) · Explanation Score”. Keep them readable and do not add any other scoring terms. At the bottom place the short output label “Ranked Root + Propagation DAG Hypotheses”. The highest-ranked explanation may differ from R1, visually demonstrating that path evidence can rewrite the initial root ranking.

Use these exact English labels and spell them correctly:
“Incident-Conditioned Subgraph Selection”
“Connected Undirected Subgraph”
“Suspected Root Cause”
“Affected Candidate Region”
“Probabilistic Edge Relation Graph”
“Directional Probability”
“Reverse Probability”
“No Propagation”
“For each physical edge: P(A→B) + P(B→A) + P(Disconnected) = 1”
“Root-Conditioned Explanation Ranking”
“Explanation Score = Explained Edge Probability / Total Active Edge Probability”
“Final Score = α · Stage 1 Score + (1 − α) · Explanation Score”
“Ranked Root + Propagation DAG Hypotheses”

Do not use gradients, shadows, glossy effects, 3D rendering, photorealism, isometric perspective, dark backgrounds, decorative textures, large colored fills, cartoon characters, extra colors, serif fonts, tiny unreadable text, overlapping elements, curved decorative arrows, or malformed labels. Do not add a fourth panel. Do not add confidence gates, LLM arbitration, operator review, raw alarm cards, interface-level information, or extra ranking terms beyond the two stated scores. Do not confuse P(Disconnected) with removal of the physical topology edge: it only represents no active fault-propagation relation in this incident. Do not draw cycles inside the ranked propagation DAGs.
```

## 4. 推荐图注

```text
Two-stage overview. Stage 1 uses IC-STGR to rank high-recall root-cause candidates from an incident-conditioned Device-Event-Incident spatio-temporal heterogeneous graph. Stage 2 first reconstructs one root-independent probabilistic hypothesis graph, then evaluates root-conditioned propagation DAG explanations and reranks candidates by a weighted sum of the learned Stage 1 score and propagation explanation score.
```

## 5. 后续使用约定

1. 同系列图统一使用英文标签，减少生成式绘图中的中文字符错误；
2. 每张图先复制第 2 节母版，再追加该图的具体阶段和元素；
3. 后续调整内容时不得改变黑白线稿、蓝橙强调、圆角分区、虚线证据框和左到右信息流；
4. 图过宽时拆成独立子图，不通过压缩字体或减少留白强行塞入原图；
5. 生成后重点复核文字拼写、箭头方向、是否存在意外有向环，以及最终排序是否只保留 Stage 1 分数和解释性分数两个加权项。
6. 后续图中的 Stage 1 统一指 IC-STGR；确定性拓扑+时序融合只在基线或消融图中出现。
