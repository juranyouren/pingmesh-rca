# M3 — 锚点条件全局骨架重建

M1 输出的是**局部关系似然图** $S$：对每个拓扑可容许的设备对，给出两个**相互独立**的方向分数。局部证据无法决定这些关系统属于哪一个全局结构 —— 两个局部都合理的方向在拼装后可能互相矛盾，一个设备也可能携带着 anchor 根本到不了的那部分网络的强证据。

M3 把这张图收敛成一张传播图 $G_P=(V,E_P)$，并且把这件事分成两个显式分离的步骤：

```
M1 方向证据
    │
    ▼
lift(u→v) = 证据增量（有符号、可加）
    │
    ▼
┌────────────────────────────────────────┐
│ 骨架：虚拟根最大证据树                  │
│   r0 → anchor : 结构性强制为根          │
│   r0 → v      : 空选项（不认领）        │
│   u  → v      : lift(u→v)              │
│   环收缩 / 展开，删 π(v*)               │
└────────────────┬───────────────────────┘
                 ▼
        anchor component = backbone
        （其余 component = unreached）
                 │
                 ▼
┌────────────────────────────────────────┐
│ DAG 增补：恢复单亲限制丢掉的多因关系     │
│   p(e) ≥ augmentation_min_probability  │
│   source(e) ∈ Reach(anchor)            │
│   加后仍无环                            │
└────────────────┬───────────────────────┘
                 ▼
                G_P
```

职责一句话概括：

$$\text{M3} = \text{全局结构选择} + \text{多父证据恢复}$$

**M3 不承担 target ranking 目标。** 这一点是刻意的，理由见 §3。

## 代码位置

| 文件 | 职责 |
| --- | --- |
| `Sys/RootCauseAnalyze/propagation/m3/arborescence.py` | 纯图算法：Chu–Liu/Edmonds + 虚拟根。零领域知识，纯标准库 |
| `Sys/RootCauseAnalyze/propagation/m3/decode.py` | 领域映射：M1 → 加权有向图 → 骨架 → 增补 → 图行 |
| `Sys/RootCauseAnalyze/propagation/m2/infer.py` | 在 per-anchor 循环中按 `backbone_method` 路由 |

`arborescence.py` 不认识 device、prize、alarm，只认 `(nodes, weighted_edges, root)`，因此可以独立单测，也可以拿 `networkx` 当预言机对拍（见 §8）。

## 1. 输入：为什么权重必须可加

M3 的目标是 $\max\sum_e w(e)$，这只有在 $w$ 可加时才有意义。`logit_evidence_v1` 在 log-odds 空间累加证据：

$$z(\text{direction}) = \underbrace{\operatorname{logit}(p_0(\text{edge\_type}))}_{prior\_logit} + \sum_i A_i\big(q_{s,i}\log LR_{s,i} + q_{t,i}\log LR_{t,i}\big)$$

定义**证据增量**（lift）：

$$\boxed{lift(u\to v) = a\_to\_b\_logit - prior\_logit = \sum_i (\cdots)}$$

即"观测到的证据相对无证据基线抬高了多少"。

**恰好减一次 prior。** `evidence_logit.py` 中 `logit_a = prior_logit + Σ log_contribution`，所以上式等于 $\sum \log\text{contribution}$。实现上 `decode.py` 直接读 `probability_details` 里已记录的 `prior_logit` 与 `*_logit` 相减，不再重新查表，因此不存在重复扣减 prior 的路径。

减 prior 的作用是让 $lift=0$ 具有确定含义：**该方向的证据不比基线更强**。这是空选项的零点。

> 注意：`lift = 0` 对应的*概率*随 edge_type 变化（$p = prior$）。这是 §6 要讨论的标定问题。

## 2. 骨架：虚拟根最大证据树

### 2.1 为什么不能直接用最大树

Chu–Liu/Edmonds 的最大树要求**每个非根节点恰有一条入边**。但本项目 M1 明确保留了 `no_direct_propagation` 状态，`logit_evidence_v1` 刻意不把两个方向归一化 —— "没有证据"和"有证据"是两回事。若直接拿正权重跑最大树，"没观测到"会被强制变成"断言有一条边"，直接违反 *No silent zero-filling*。

### 2.2 归约

引入虚拟根 $r_0$：

```
节点   V ∪ {anchor} ∪ {r0}
实边   u → v : lift(u→v)          仅在拓扑校验通过的候选对上，两个方向各一条
虚边   r0 → v : null_weight        每个 v（空选项：不认领这个设备）
       r0 → a : BIG                 锁定根，BIG = 1 + Σ|w|
```

设备只有在某条真实关系**严格强于** `null_weight` 时才会被 anchor 的树认领；其余挂在 $r_0$ 上，输出为 `unreached`，而不是获得一条证据从未支持过的边。

默认 `backbone_null_weight = 0.0`，读作"需要净正证据"。

### 2.3 为什么不用 prize-collecting（关键设计决策）

一个自然的想法是把 `target_prize` 折进实边权重：

$$w(u\to v) = lift(u\to v) + \lambda\,prize(v)$$

**这个归约在本项目里不成立。**

标准 prize-collecting Steiner tree 的虚拟根归约之所以在 min-cost 版本下正确，是因为**死子树被支配**：把 $t$ 挂到一个未被 anchor 到达的节点 $x$ 上要付 $cost(x,t)>0$，而直接排除 $t$ 只付 $prize(t)$，所以最优解不会出现死子树。

本项目的符号是反的：$lift>0$ 恰恰是好事，死子树**有利可图** —— 白拿 $lift(x,t)$ 和 $t$ 的 prize，没有任何项惩罚"$t$ 不在 anchor component 里"。归约需要的是

$$\mathbf 1[\text{real parent}(v)] = \mathbf 1[a \leadsto v]$$

这是**全局连通性**条件，不是逐边函数能表达的。而且 prize-collecting rooted arborescence 包含 directed Steiner tree，是 NP-hard —— 指望"CLE + 一个局部变换"精确表达本来就不现实。

因此 v1 不引入 target prize。代价是 §7 的第一条限制。

### 2.4 anchor 条件化是结构自带的

以 $a$ 为根的 arborescence 中，每条边的父向都背离根，所以**方向是结构隐含的**。这不同于 beam search 路径里 `outward = dist[target] > dist[source]` 的距离门控 —— 后者是在权重之外额外施加方向约束，而前者把它吸收进了结构约束。M3 中不再有独立的 $\phi_{\text{anchor}}$ 项，因此也不存在重复计一次 anchor 的问题。

同理，**不需要方向门控**：同一对的两个方向互为 2-环，acyclicity 自动排除。M1 保留的双向假设在 M3 收敛。

## 3. 环收缩与展开

标准 CLE：反复为每个非根节点选 $\pi(v)=\arg\max$ 入边（并列按 `(-w, from, to)` 定序，保证确定性）；若 $\pi$ 图有环则收缩该环并重权，递归；无环则结束。

收缩时对进入边 $u\to v^*$（$v^*\in C$）：

$$w'(u, C) = w(u, v^*) - w(\pi(v^*))$$

（reduced 形式；常数 $W(C)=\sum_{v\in C}w(\pi(v))$ 只是目标值偏移，逐层加回即可。）

### 3.1 展开删的是 $\pi(v^*)$，不是环内最轻边

这是 CLE 实现里最容易写错的地方。当收缩后的解选择了进入边 $u\to C$（对应原图 $u\to v^*$），展开必须删除

$$\boxed{\pi(v^*)}$$

即原环中**进入 $v^*$ 的那条被选中入边**，因为 $u\to v^*$ 替代了它。

反例（本项目 `tests/test_arborescence.py` 固化）：

```
B→C : 10    C→D : 9    D→B : 8        外部进入边 A→C
```

$\pi(C)=B\to C$。展开必须删 $B\to C$ —— **即使它是环里最重的一条**。若按"删最轻边"处理会删掉 $D\to B$，得到 $C$ 有两个父节点、$B$ 没有父节点的非 arborescence 结构。

实现上，收缩时必须记录 provenance（contracted entering edge ↦ original $u\to v^*$ ↦ $\pi(v^*)$）。本项目用一个更简洁的等价机制：每条收缩边携带 **payload** —— 选中它时应当产出的**基图边集合**。展开即 payload 展平，嵌套收缩自然被归纳覆盖，无需单独的展开遍历。

### 3.2 收缩权重绝不外泄

重权后的 $w'$ 已经不是证据：它可以为负、可以跑出 $[0,1]$。所以

> **CLE 是结构选择器，不是评分器。**

`decode.py` 在输出每一行时回填的是该方向的**原始概率与原始 lift**，重权值只在求解器内部存在。输出行把两者分开存放：

- `support_score` / `support_level` / `state_probability` ← 原始方向概率
- `features.evidence_lift` ← 实际驱动结构决策的量

下游 `trust.py` 的 `supported_edges_majority` 等检查按 `support_level` 切分，依赖这个区分。

## 4. DAG 增补

树给每个设备恰一个父节点，但真实事故里一个下游设备可能有**多个独立上游**。增补不是装饰，是**多因场景的承载者**。

三条约束，缺一不可：

### 4.1 阈值取边自身的直接传播证据

$$\boxed{p(e) \ge \texttt{augmentation\_min\_probability}}$$

**不能**用 $lift(e) + \lambda\,prize(v)$ 这类含 prize 的量。否则取 $lift=-0.3$、$prize=1$、$\lambda=1$ 时会得到 $0.7>0.405$，把一个**负证据的传播边**作为增补边加回来 —— 恰好违反 M3 存在的意义。

### 4.2 阈值在概率空间，不做换算

配置项存**概率**，实现直接比较该方向的 `state_probability`：

$$\texttt{state\_probability} \ge \texttt{augmentation\_min\_probability} \iff lift + prior\_logit \ge \operatorname{logit}(p) \iff lift \ge \operatorname{logit}(p) - prior\_logit$$

这恰好是 $\tau_{\text{aug}} = \operatorname{logit}(p)-prior\_logit$ 的等价形式，但**天然按 edge\_type 生效**，不需要任何换算函数，也就不存在"prior 变了导致阈值静默失配"的风险。

（对比：若把阈值硬编码成 lift 常量，`physical` / `protocol_context` / `_default` 三者的 prior_logit 分别是 $-2.944$ / $-3.476$ / $-3.892$，同一个 lift 值对应的概率完全不同。）

### 4.3 source 必须已被 anchor 到达，且逐轮生长

```python
for e in candidates sorted by (-lift, from, to):
    if p(e) < threshold:            continue
    if source(e) not in Reach(a):   continue
    if adding e creates a cycle:    continue
    add e
```

`source(e) ∈ Reach(a)` 这一条很重要：

- 它阻止一个 anchor 根本到不了的、证据很强的孤岛靠增补把自己接进来；
- 它让增补成为 **evidence-supported outward expansion**；
- 它同时缓解 §7.1 的"孤儿环"问题（anchor 到得了的组件会被捞回）。

**必须迭代到不动点**，不能单趟降序扫描。接受 $a\to b$ 会让 $b$ 变成可达，从而让一条从 $b$ 出发、在排序中位置更靠前的边重新获得资格。实现为不动点循环，结果不依赖候选的排序位置。

## 5. 图行输出契约

`decode_backbone` 返回与 beam search 相同的字段集，供既有评测与可视化消费。

**一个必须遵守的约束**：`trust._root_reachable` 要求 `nodes` 中每个节点都能从 anchor 到达。因此

> `nodes` 只包含 anchor component；未被认领的设备只进 `diagnostics.unreached_nodes`。

被 `unreached` 的设备留在 `nodes` 里会让 `diagnosability` 直接降级。

`diagnostics` 新增（M3 专属）：`anchor_device`、`anchor_candidates`、`backbone_method`、`backbone_edge_count`、`augmented_edge_count`、`cycle_contraction_count`、`backbone_objective`、`backbone_arborescence_weight`、`backbone_unreached_nodes`、`unreached_nodes`。

## 6. 阈值语义与标定（未完成事项）

### 6.1 两个阈值在不同空间，不可直接比较

| 参数 | 空间 | 默认值 | 概率空间等价 |
| --- | --- | --- | --- |
| `backbone_null_weight` | lift | `0.0` | $p > prior$（physical 为 0.05，`_default` 为 0.02） |
| `augmentation_min_probability` | 概率 | `0.60` | — |
| beam search 的 `min_edge_support` | 概率 | `0.25` | — |

`backbone_null_weight` 在 lift 空间意味着**同一个数值在不同 edge_type 下对应不同的概率门槛**：要与 `p ≥ 0.25` 对齐，`physical` 需要 `null_weight = 1.846`，`protocol_context` 需要 `2.378`，`_default` 需要 `2.793`。单一标量无法表达统一概率门槛。

`decode_backbone` 强制要求 `edge_probability_method = 'logit_evidence_v1'`，因为其余方法输出的是单纯形概率，不可加，$\max\sum w$ 无意义。

### 6.2 本地实测（未标定证据模型）

在 `data/node/nodes_max_labeled` 的两个事件上（证据来源为规则路径），方向证据分布：

| 事件 | 方向数 | lift 范围 | lift>0 | p 范围 | p≥0.25 | p≥0.60 |
| --- | --- | --- | --- | --- | --- | --- |
| 23041865 | 18 | [−0.223, 1.099] | 1 | [0.040, 0.136] | 0 | 0 |
| 8294294 | 26 | [0.000, 1.330] | 4 | [0.050, 0.166] | 0 | 0 |

结论：

1. **增补在现有证据上结构性为空**（最高概率 0.166 ≪ 0.60）。`augmented_edge_count = 0` 不是实现问题，是标定问题。
2. 概率被钉在 0.04–0.17 区间，根源是 `configs/propagation/evidence_logit_v1.json` 中的 prior 是**未标定占位值**（该文件自述："no LR or prior here has been estimated from incident history"）。prior_logit ≈ −2.94 主导了累加结果。
3. 另一个收紧上限的因素：`_UNSTATED_MAPPING_CONFIDENCE = 0.5`，若 episode 未携带 `quality.mapping_confidence`，语义项质量系数封顶 0.5，最强组合（explicit_cause + temporal）的上限约为 $0.5\times\log 12 + 1.0\times\log 6 \approx 3.03$，仍低于物理边 $\operatorname{logit}(0.60)-prior\_logit = 3.35$。

> **因此：在证据模型标定完成前，不要固化 `augmentation_min_probability` 与 `backbone_null_weight`。** 先跑一遍全量事件的 lift 分布，再定这两个值。

### 6.3 消融表需要对齐阈值

实测（两个本地事件）：

| variant | `--backbone-method` | edges | coverage | unreached |
| --- | --- | --- | --- | --- |
| beam | `beam_search_v1` | 0 / 0 | 0.167 / 0.143 | — |
| arbo（默认 `null_weight=0`） | `maximum_evidence_arborescence_v1` | 1 / 2 | 0.333 / 0.429 | 9 / 8 |
| arbo（`null_weight=1.846`，对齐 `p≥0.25`） | 同上 | **0 / 0** | **0.167 / 0.143** | 10 / 10 |

第三行说明：默认配置下 M3 的覆盖率提升**完全来自阈值更松**，不是结构改进。要让

$$\text{Existing M2} \;/\; \text{Backbone only} \;/\; \text{Full M3}$$

这张消融表成立，必须先做阈值对齐，否则它测的是阈值而不是算法。

## 7. 已知限制

### 7.1 孤儿环 / 整个组件被判为不可达

目标函数定义在**整片虚拟根森林**上，而 M3 只取 anchor component。当一个环的接入代价高于脱离代价时，优化器会把整个环判为不可达。

具体地，环 $C$ 可以经 anchor 侧的 $a\to b$ 接入（丢 $\pi(b)$），也可以挂在 $r_0$ 上（丢进入点处的 $\pi$）。优化器选丢得少的那个。若 anchor 的接入点恰好是环内 $\pi$ 最大的节点，整个环会被判为 unreachable。

最小复现（`tests/test_m3_decode.py` 的早期 fixture）：

```
lift: a→b 1.0, d→b 4.0, b→c 3.0, c→d 2.0
```

- 经 $a\to b$ 接入：丢 $\pi(b)=d\to b$，保留 $\{a\to b, b\to c, c\to d\}$ = 6.0
- 挂 $r_0$ 进入 $d$：丢 $\pi(d)=c\to d$，保留 $\{d\to b, b\to c\}$ = 7.0

后者更优，于是 $b,c,d$ 全部判为不可达。

$lift > 0$ 的全部节点都在 §4.3 的增补环节被逐步捞回（不动点循环），所以最终图不是空的；但**骨架本身可能只剩 anchor 一个点**，`backbone_edge_count` 会显著低于预期。

这是"不引入 prize"的直接代价。若要缓解，需要显式的 anchor reachability 变量，即回到 §2.3 的 NP-hard 问题。

### 7.2 不表达多因之外的结构

骨架入度恒为 1。真实的多因关系全部依赖增补恢复，因此 `augmentation_min_probability` 同时控制增补的精确率/召回率。该值未标定（§6.2）。

### 7.3 仅支持 `logit_evidence_v1`

其余概率方法的输出不可加。`decode_backbone` 会显式报错而不是静默退化。

## 8. 验证

- `tests/test_arborescence.py` — 13 项，含环展开删除 $\pi(v^*)$、空选项不认领无证据节点、并列确定性，以及 **300 个随机图上与 `networkx` 最大分支的目标值对拍**。
- `tests/test_m3_decode.py` — 12 项，含骨架结构、原始分数回填、增补可达性门控、先验相关的阈值、`trust.py` 契约、配置守卫、M2 路由。

`networkx` 只作为**测试预言机**使用，`Sys/RootCauseAnalyze/propagation/` 保持零第三方依赖。

## 9. 配置

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `backbone_method` | `beam_search_v1` | 或 `maximum_evidence_arborescence_v1` |
| `backbone_null_weight` | `0.0` | 空选项（lift 空间）；节点被认领所需的证据量 |
| `dag_augmentation` | `True` | 关闭即得 "Backbone only" 消融变体 |
| `augmentation_min_probability` | `0.60` | 增补边的方向概率门槛 |

CLI：

```bash
# Full M3
python Sys/RootCauseAnalyze/propagation_pipeline.py \
  -d data/node/nodes_max_labeled -o res/m3 \
  --edge-probability-method logit_evidence_v1 \
  --backbone-method maximum_evidence_arborescence_v1

# Backbone only（消融）
python Sys/RootCauseAnalyze/propagation_pipeline.py \
  -d data/node/nodes_max_labeled -o res/m3_backbone_only \
  --edge-probability-method logit_evidence_v1 \
  --backbone-method maximum_evidence_arborescence_v1 --no-dag-augmentation

# Existing M2（对照，默认值）
python Sys/RootCauseAnalyze/propagation_pipeline.py \
  -d data/node/nodes_max_labeled -o res/m2_beam \
  --edge-probability-method logit_evidence_v1
```

旧 solver（`_condition_edges` / `solve_propagation_dags`）**保留至实验冻结**，供上表第一行使用。
