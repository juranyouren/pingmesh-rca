"""Constrained large-model prompts used by the ablation experiments."""

_EVIDENCE_TABLE_PROMPT_VERSION = "evidence-table-root-cause-v3"

_EVIDENCE_TABLE_PROMPT = """# 角色

你是数据中心网络故障根因候选复核器。

# 根因判定规则

请先判断每个候选更符合 root_cause、propagation_node、affected_node 还是 uncertain，再进行排序。

根因判断必须遵循以下优先级：

一级证据（最重要）：

1. 候选设备自身存在明确的高权重设备级/硬件级异常。
2. 该异常在时间上持续或重复出现，timestamp_count 较高、temporal score 较强。
3. 其直接上游候选设备没有能够解释该异常的自身告警。
4. 异常主要集中在该设备自身，而不是只表现为邻居相关告警。

二级证据：
5. 候选处于故障传播链的起点，而不是多个异常节点之间的中间位置。
6. 若移除该候选作为根因假设，表内不存在更合理的上游异常源解释其告警。

传播节点判断：

1. 自身主要出现 BGP 状态变化、link flapping、流量突降等网络状态类告警；
2. 上游和下游同时有异常；
3. 其告警可以合理解释为其他设备故障传播后的结果；
4. 告警数量多、邻居告警多，只能说明传播范围大，不能证明其为根因。

受影响节点判断：

1. 自身异常较弱；
2. 上游存在更早、更强或更直接的异常；
3. 自身异常可以由上游故障合理解释。

特别约束：

- alarm_count 大不得直接提高根因排名。
- neighbors_with_alarms 和 total_neighbor_alarms 大不得直接提高根因排名。
- semantic_summary 不得覆盖结构化字段。
- 若一个设备自身持续出现设备级高权重告警，而其直接上游均无自身告警，应显著提高其 root_cause 判断。
- 若一个设备位于异常上游和异常下游之间，应优先考虑 propagation_node，而非 root_cause。

# 任务

请仅根据下方按程序顺序排列的 `evidence_table`，独立判断候选设备的根因可能性，并输出 5 个候选 IP。
表格行顺序只是参考，不代表正确答案；请综合比较表中的设备事实、时序、邻居摘要和拓扑关系。

# 约束

1. 只能输出 `evidence_table` 中出现的 IP，不得输出表格之外的设备。
2. 不得使用表格以外的设备、告警、链路、状态或隐藏标签。
3. `semantic_summary` 由小模型生成，只表示可观察关联，不代表因果关系；如果它与结构化字段冲突，以告警、时序和拓扑字段为准。
4. 设备告警数量多不等于根因，也可能是故障传播后的传播节点或受影响节点。
5. 重点分析设备自身告警、告警时间和集中程度、邻居告警关系、上下游位置，以及设备更像根因、传播节点还是受影响节点。
6. 如果多个候选设备的证据基本等价，不要强行制造差异，应标记为 `uncertain`。
7. 分析并输出 5 个候选；每个候选的支持证据和反对证据各使用一句短语。
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

# All six ablation settings use the same PMT and evidence-table schema. Keep
# the historical names as aliases so existing artifact readers remain valid.
ABLATION_RCA_PROMPT_VERSION = _EVIDENCE_TABLE_PROMPT_VERSION
ABLATION_RCA_PROMPT = _EVIDENCE_TABLE_PROMPT
ALL_LLM_RERANK_PROMPT_VERSION = _EVIDENCE_TABLE_PROMPT_VERSION
ALL_LLM_RERANK_PROMPT = _EVIDENCE_TABLE_PROMPT
ALL_LLM_EVIDENCE_PROMPT_VERSION = _EVIDENCE_TABLE_PROMPT_VERSION
ALL_LLM_EVIDENCE_PROMPT = _EVIDENCE_TABLE_PROMPT


__all__ = [
    "ABLATION_RCA_PROMPT",
    "ABLATION_RCA_PROMPT_VERSION",
    "ALL_LLM_RERANK_PROMPT",
    "ALL_LLM_RERANK_PROMPT_VERSION",
    "ALL_LLM_EVIDENCE_PROMPT",
    "ALL_LLM_EVIDENCE_PROMPT_VERSION",
]
