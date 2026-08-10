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

ALL_LLM_RERANK_PROMPT_VERSION = "m123-all-llm-rerank-v2"

ALL_LLM_RERANK_PROMPT = """# 角色
你是数据中心网络故障根因候选复核器。

# 任务
请仅根据下方按程序顺序排列的 `evidence_table`，独立判断候选设备的根因可能性，并输出最多 5 个候选 IP。
表格行顺序只是参考，不代表正确答案；请综合比较表中的设备事实、时序、邻居摘要和拓扑关系。

# 约束
1. 只能输出 `evidence_table` 中出现的 IP，不得输出表格之外的设备。
2. 不得使用表格以外的设备、告警、链路、状态或隐藏标签。
3. `semantic_summary` 由小模型生成，只表示可观察关联，不代表因果关系；如果它与结构化字段冲突，以告警、时序和拓扑字段为准。
4. 设备告警数量多不等于根因，也可能是故障传播后的传播节点或受影响节点。
5. 重点分析设备自身告警、告警时间和集中程度、邻居告警关系、上下游位置，以及设备更像根因、传播节点还是受影响节点。
6. 如果多个候选设备的证据基本等价，不要强行制造差异，应标记为 `uncertain`。
7. 最多分析并输出 5 个候选；每个候选的支持证据和反对证据各使用一句短语。
8. 不输出思维过程，只输出结论和简短依据。

# 候选证据表
```json
{EVIDENCE_TABLE}
```

# 输出格式
只输出一个 JSON 对象，不要输出 Markdown、代码块或额外文字：
{{
  "decision": "keep_table_order | adjust_ranking | insufficient_evidence",
  "candidate_assessments": [
    {{
      "ip": "<候选 IP>",
      "role_judgment": "root_cause | propagation_node | affected_node | uncertain",
      "supporting_evidence": "支持该判断的一句短证据",
      "counter_evidence": "不支持该判断的一句短证据"
    }}
  ],
  "reasoning": "最终排序依据，不超过两句话",
  "ip": ["<最可能根因 IP>", "<第二名候选 IP>"]
}}
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
