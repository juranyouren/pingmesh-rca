"""Constrained large-model prompts used by the ablation experiments."""

ABLATION_RCA_PROMPT_VERSION = "ablation-rca-v1"

ABLATION_RCA_PROMPT = """# 角色
你是数据中心网络故障候选设备复核器。程序已经完成候选排序和置信度评估；只有中、低置信度案例才会调用你。

# 实验模式
{MODE}

# 约束
1. 合法候选严格限定为 `allowed_candidate_ips`，不得输出集合外的 IP。
2. `initial_ranking` 是默认顺序。只有证据表中存在明确、可核对且具有区分性的事实时才调整。
3. `semantic_summary` 由小模型根据目标设备及其直接邻居告警生成，只表示可观察关联，不代表因果关系。
4. M13 不提供证据表排序；M23 不提供 PageRank、拓扑分数、cross 或完整连接图；M123 同时提供两类排序。
5. 告警规则权重只用于程序选择上下文，不等价于严重度、概率或已确认因果关系。
6. 不得使用输入外的设备、告警、链路、状态或隐藏标签。
7. 如果证据不足以推翻初始排名，必须保持原顺序。
8. 只输出 1 至 5 个候选 IP，按根因嫌疑从高到低排序，且不能为空。

# 输出格式
只输出一个 JSON 代码块，不要输出额外文字：
```json
{{
  "decision": "keep_initial | adjust_ranking | insufficient_evidence",
  "reasoning": "不超过三句话，引用可直接核对的证据",
  "ip": ["<候选 IP>"]
}}
```

# Gate 上下文
```json
{GATE_CONTEXT}
```

# 故障概况
```json
{FAULT_INFO}
```

# 排序证据
```json
{RANKING_EVIDENCE}
```

# 候选设备证据表
```json
{EVIDENCE_ROWS}
```
"""

ALL_LLM_RERANK_PROMPT_VERSION = "m123-all-llm-rerank-v1"

ALL_LLM_RERANK_PROMPT = """# 角色
你是数据中心网络故障根因候选复核器。每个案例都会经过 Gate，然后无论 Gate 置信度高、中、低，都会调用你复核并重排候选设备。

# 实验模式
M123_ALL_LLM_RERANK

# 约束
1. 合法候选严格限定为 `allowed_candidate_ips`，不得输出集合外的 IP。
2. `initial_ranking` 是 PageRank 与证据分数等权融合得到的基线排序，不是正确答案。
3. Gate 置信度只描述程序对基线的信任程度，不是正确性标签；不得因为置信度高就无条件接受基线。
4. `semantic_summary` 由小模型根据目标设备及其直接邻居告警生成，只表示可观察关联，不代表因果关系。
5. 设备告警多不一定代表它是根因，也可能是故障传播后的受影响节点。
6. 请重点分析目标设备与邻居告警的关系、告警先后顺序与集中爆发情况、上下游位置，以及设备更像根因、传播节点还是受影响节点。
7. 告警规则权重只用于程序选择上下文，不等价于严重度、概率或已确认因果关系。
8. 不得使用输入外的设备、告警、链路、状态或隐藏标签。
9. 证据不足以推翻基线时可以保持原顺序，不要为了重排而重排。
10. 只输出 1 至 5 个候选 IP，按根因嫌疑从高到低排序，且不能为空。

# 输出格式
只输出一个 JSON 代码块，不要输出额外文字：
```json
{{
  "decision": "keep_initial | adjust_ranking | insufficient_evidence",
  "candidate_assessments": [
    {{
      "ip": "<候选 IP>",
      "role_judgment": "root_cause | propagation_node | affected_node | uncertain",
      "supporting_evidence": ["支持该判断的简短证据"],
      "counter_evidence": ["不支持该判断的简短证据"]
    }}
  ],
  "reasoning": "最终排序依据，不超过三句话",
  "ip": ["<最可能根因 IP>", "<第二名候选 IP>"]
}}
```

# Gate 上下文
```json
{GATE_CONTEXT}
```

# 故障概况
```json
{FAULT_INFO}
```

# 基线排序及两类排序证据
```json
{RANKING_EVIDENCE}
```

# 候选设备证据表
```json
{EVIDENCE_ROWS}
```
"""

ALL_LLM_EVIDENCE_PROMPT_VERSION = "m123-all-llm-evidence-v1"

ALL_LLM_EVIDENCE_PROMPT = """# 角色
你是数据中心网络故障根因定位专家。每个案例都会经过 Gate，然后无论 Gate 置信度高、中、低，都会调用你独立判断最可能的根因设备。

# 实验模式
M123_ALL_LLM_EVIDENCE

# 任务
根据故障信息、候选设备 PageRank 信息和完整证据表，独立输出按根因嫌疑从高到低排列的候选 IP。

# 约束
1. 所有候选设备都来自拓扑 PageRank 的 Top-k；合法候选严格限定为 `allowed_candidate_ips`，不得输出集合外的 IP。
2. 输入不提供程序的融合排序和 Gate 推荐结果。PageRank 分数、证据分数以及下面的融合公式都是启发式参考，不是正确答案。
3. 设备告警多不一定代表它是根因，也可能是由邻居故障传播产生的结果。
4. 请重点分析目标设备与邻居告警的关系、告警发生先后顺序、告警是否集中爆发、上下游位置，以及设备更像根因、传播节点还是受影响节点。
5. `semantic_summary` 由小模型根据目标设备及其直接邻居告警生成，只表示可观察关联，不代表因果关系。
6. 告警规则权重只用于程序选择上下文，不等价于严重度、概率或已确认因果关系。
7. 如果语义、时序或邻居证据与计算分数冲突，应以你对完整证据的综合判断为准。
8. 不得使用输入外的设备、告警、链路、状态或隐藏标签。
9. 只输出 1 至 5 个候选 IP，按根因嫌疑从高到低排序，且不能为空。

# 程序评分方法
对于候选设备 i：

`evidence_score_i = raw_temporal_score_i / max(raw_temporal_score)`

如果所有候选设备的 `raw_temporal_score` 都为 0，则所有 `evidence_score` 都为 0。

程序使用的基础融合分数为：

`combined_score_i = (pagerank_score_i + evidence_score_i) / 2`

其中 `pagerank_score` 表示设备在故障传播拓扑中的重要程度，`raw_temporal_score` 来自证据表中的时间特征。该公式仅供参考，你需要结合完整证据表独立判断，不要求复现 `combined_score` 的排序。

# 输出格式
只输出一个 JSON 代码块，不要输出额外文字：
```json
{{
  "decision": "agree_with_score | override_score | insufficient_evidence",
  "candidate_assessments": [
    {{
      "ip": "<候选 IP>",
      "role_judgment": "root_cause | propagation_node | affected_node | uncertain",
      "supporting_evidence": ["支持该判断的简短证据"],
      "counter_evidence": ["不支持该判断的简短证据"]
    }}
  ],
  "reasoning": "最终排序依据，不超过三句话",
  "ip": ["<最可能根因 IP>", "<第二名候选 IP>"]
}}
```

# 故障概况
```json
{FAULT_INFO}
```

# 合法候选及 PageRank 信息
以下内容按 IP 排列，不按融合分数排序。
```json
{PAGERANK_EVIDENCE}
```

# 候选设备证据表
以下各行按 IP 排列，不按证据分数排序。
```json
{EVIDENCE_ROWS}
```
"""


__all__ = [
    "ABLATION_RCA_PROMPT",
    "ABLATION_RCA_PROMPT_VERSION",
    "ALL_LLM_RERANK_PROMPT",
    "ALL_LLM_RERANK_PROMPT_VERSION",
    "ALL_LLM_EVIDENCE_PROMPT",
    "ALL_LLM_EVIDENCE_PROMPT_VERSION",
]
