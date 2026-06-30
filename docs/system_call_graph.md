# System Call Graph

This document summarizes the key function path for running one RCA case after
the modularization pass.

## Online LLM Inference

```mermaid
flowchart TD
  A["SkilledAnalyzer.generate_prompts()"] --> B["Sys.utils.case_utils.find_full_link_file()"]
  B --> C["SkilledAnalyzer.distribute_inference_tasks()"]
  C --> D["SkilledAnalyzer.worker_process()"]
  D --> E["SkilledAnalyzer.batch_infer()"]
  E --> F["SkilledAnalyzer._build_final_prompt()"]
  F --> G["gate.evidence.build_fused_evidence()"]
  G --> H["skills.fusion.rank_devices_by_skills()"]
  H --> I["skills.topo_ranker.score_topo()"]
  H --> J["skills.temporal_ranker.score_temporal()"]
  I --> K["trust_trees.topo_tree.assess_topo_tree()"]
  J --> L["trust_trees.temporal_tree.assess_temporal_tree()"]
  G --> M["gate.decision.assess_gate()"]
  M --> N{"gate decision"}
  N --> O["gate.response.make_bypass_response()"]
  N --> P["SkilledAnalyzer._ensure_llm() + vLLM.chat()"]
  O --> Q["Sys.utils.io_utils.save_json()"]
  P --> Q
```

Key idea: `gate.evidence` prepares algorithm evidence for the LLM, while
`gate.decision` decides whether the case should bypass LLM, invoke LLM, or be
sent to operator review.

## Offline Skill Pipeline

```mermaid
flowchart TD
  A["skill_pipeline.run_skill_pipeline()"] --> B["Sys.utils.case_utils.load_case_nodes()"]
  A --> C["Sys.utils.case_utils.load_case_info()"]
  B --> D["skills.fusion.rank_devices_by_skills()"]
  C --> D
  D --> E["skills.topo_ranker.score_topo()"]
  D --> F["skills.temporal_ranker.score_temporal()"]
  E --> G["trust_trees.topo_tree.assess_topo_tree()"]
  F --> H["trust_trees.temporal_tree.assess_temporal_tree()"]
  D --> I["Sys.utils.case_utils.read_gt_ips()"]
  I --> J["Sys.utils.io_utils.save_json()"]
```

The offline path no longer loads dynamic skill files. Skill 1 and Skill 2 are
built-in Python modules under `Sys/RootCauseAnalyze/skills/`.

## Main Modules

| Module | Responsibility |
| --- | --- |
| `Sys/utils/io_utils.py` | JSON, JSONL, CSV, and parent directory helpers |
| `Sys/utils/case_utils.py` | Case file discovery, node/info loading, ground-truth reading |
| `Sys/utils/alarm_utils.py` | Alarm/log name, timestamp, and weight helpers |
| `Sys/utils/ranking_utils.py` | Stable score sorting and score fusion helpers |
| `Sys/RootCauseAnalyze/skills/topo_ranker.py` | Topology PageRank scoring and topo trust evidence |
| `Sys/RootCauseAnalyze/skills/temporal_ranker.py` | Temporal Burst/EarlyBird/Density scoring and evidence |
| `Sys/RootCauseAnalyze/skills/fusion.py` | Runs selected built-in skills and builds combined ranking |
| `Sys/RootCauseAnalyze/skills/provider.py` | Compatibility provider for analyzer code |
| `Sys/RootCauseAnalyze/gate/evidence.py` | Builds LLM-facing evidence from skill outputs |
| `Sys/RootCauseAnalyze/gate/decision.py` | Trust-tree gate routing |
| `Sys/RootCauseAnalyze/gate/response.py` | Score-compatible bypass/operator response |
