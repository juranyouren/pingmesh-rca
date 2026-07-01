# AGENT.md

## Project

This repository is a DCN root-cause analysis research prototype for Huawei Cloud
Pingmesh-triggered incidents. The active pipeline is:

`Pingmesh case data -> topo ranker + temporal ranker -> fused evidence -> trust-tree gate -> optional local LLM review -> Score_N evaluation`

## Non-Negotiables

- Internal fault data is not publishable. Do not move `data/` into tracked code.
- Do not call external LLM APIs for project experiments. The intended runtime is local vLLM on Ascend NPU servers.
- Do not let inference code read `label.json`; labels are only for evaluation.
- Run tests with `python -m pytest`, not bare `pytest`, unless a local `PYTHONPATH` is already configured.

## Key Paths

- `Sys/RootCauseAnalyze/skill_pipeline.py`: deterministic topo/temporal skill pipeline.
- `Sys/RootCauseAnalyze/skills/`: built-in topo, temporal, and fusion logic.
- `Sys/RootCauseAnalyze/gate/`: evidence builder, trust-tree decision, summarizer, bypass response.
- `Sys/RootCauseAnalyze/trust_trees/`: auditable topo/temporal trust tree rules.
- `Sys/RootCauseAnalyze/SkilledAnalyzer.py`: LLM review path and gate integration.
- `Sys/Score/`: evaluation, trust-gate application, and failure analysis.
- `prompts/`: active LLM prompt templates; do not recreate root-level `utils/`.
- `scripts/common.sh`: single source of default server paths and model parameters.
- `scripts/run_gate_pipe_experiments.sh`: current main experiment driver.
- `Baseline/`: TraceRCA, NetEventCause, and BiAn baseline adapters.
- `docs/project_overview.md`: detailed project state and roadmap.

## Data And Artifacts

- `data/` is ignored and should stay local.
- `docs/papers/` keeps text extractions and summaries only.

## Common Commands

```bash
python -m pytest -q
source scripts/common.sh
python Sys/RootCauseAnalyze/skill_pipeline.py --help
python Sys/Score/evaluate_trust_gate.py --help
```
