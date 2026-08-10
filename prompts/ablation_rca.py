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

ALL_LLM_EVIDENCE_PROMPT_VERSION = "m123-all-llm-evidence-v2"

ALL_LLM_EVIDENCE_PROMPT = """# 角色
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

# 两种全量 LLM 模式都使用同一份精简证据复核提示；保留独立版本号和
# prompt_variant，便于在实验结果中区分 rerank 与 evidence 两条流水线。
ALL_LLM_RERANK_PROMPT = ALL_LLM_EVIDENCE_PROMPT


__all__ = [
    "ABLATION_RCA_PROMPT",
    "ABLATION_RCA_PROMPT_VERSION",
    "ALL_LLM_RERANK_PROMPT",
    "ALL_LLM_RERANK_PROMPT_VERSION",
    "ALL_LLM_EVIDENCE_PROMPT",
    "ALL_LLM_EVIDENCE_PROMPT_VERSION",
]
