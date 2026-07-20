from __future__ import annotations

import json
from typing import Any, Mapping, Sequence


PROMPT_VERSION = "sys-v1-root-review-v1"


def build_review_prompt(
    *,
    variant: str,
    info: Mapping[str, Any],
    preliminary_ranking: Sequence[Mapping[str, Any]],
    gate: Mapping[str, Any],
    evidence_rows: Sequence[Mapping[str, Any]],
    legal_candidate_ips: Sequence[str],
) -> str:
    payload = {
        "prompt_version": PROMPT_VERSION,
        "ablation": variant,
        "legal_candidate_ips": list(legal_candidate_ips),
        "fault_info": dict(info),
        "preliminary_ranking": list(preliminary_ranking),
        "gate": dict(gate),
        "candidate_evidence": list(evidence_rows),
    }
    return f"""你是数据中心网络 Pingmesh 故障的受约束根因复核器。

任务：检查初始设备排名是否应当调整。只能使用输入中的事实，不能读取或猜测标签。

约束：
1. 只能输出 legal_candidate_ips 中的设备。
2. 默认保持 preliminary_ranking 的相对顺序。
3. 只有明确、可核验且能区分候选的反证才能调整排名。
4. 禁止编造接口、状态、告警、时间或因果关系。
5. 证据不足时返回 insufficient_evidence，并保留初始排名。
6. 输出 1 到 5 个去重后的候选 IP。
7. 只输出一个 JSON 代码块，不要输出其他文字。

输出格式：
```json
{{
  "decision": "keep_baseline | adjust_ranking | insufficient_evidence",
  "reason_code": "<short stable code>",
  "supporting_evidence": [{{"ip": "<candidate ip>", "fact": "<verifiable fact>"}}],
  "counter_evidence": [],
  "reasoning": "<no more than three sentences>",
  "ip": ["<ranked candidate ip>"]
}}
```

输入：
```json
{json.dumps(payload, ensure_ascii=False, indent=2)}
```
"""
