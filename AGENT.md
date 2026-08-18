# AGENT.md

## Project

This repository is a DCN root-cause analysis research prototype for Huawei Cloud
Pingmesh-triggered incidents. The `2stage` branch is the primary branch for the
current paper. Its active paper pipeline is:

`Pingmesh case data -> IC-STGR Device-Event-Incident graph ranking -> Stage 1 Top-K -> M1 root-independent hypothesis graph -> M2 root-conditioned graphs + explanation scores -> final ranking`

IC-STGR (Incident-Conditioned Spatio-Temporal Graph Ranker) is the fixed Stage 1
method. Continue Stage 1 optimization on IC-STGR; treat deterministic
topology+temporal fusion as the strong white-box baseline and LambdaMART as a
pending learning-to-rank baseline. Do not claim that the current IC-STGR result
improves Top-1: its demonstrated advantage is Top-3/Top-5 candidate coverage.

Trust-tree and optional local-LLM review remain historical/comparison experiment
paths, not the selected Stage 1 method.

## Non-Negotiables

- Internal fault data is not publishable. Do not move `data/` into tracked code.
- Do not call external LLM APIs for project experiments. The intended runtime is local vLLM on Ascend NPU servers.
- Do not let inference code read `label.json`; labels are only for evaluation.
- Run tests with `python -m pytest`, not bare `pytest`, unless a local `PYTHONPATH` is already configured.

## Key Paths

- `Sys/RootCauseAnalyze/stage1/`: IC-STGR graph/model/OOF pipeline plus deterministic temporal, alarm-topology, and fusion baselines.
- `Sys/RootCauseAnalyze/skills/`: compatibility adapters for legacy Gate/LLM experiments; Stage 1 implementations do not live here.
- `Sys/RootCauseAnalyze/gate/`: evidence builder, trust-tree decision, summarizer, bypass response.
- `Sys/RootCauseAnalyze/trust_trees/`: auditable topo/temporal trust tree rules.
- `Sys/RootCauseAnalyze/SkilledAnalyzer.py`: LLM review path and gate integration.
- `Sys/RootCauseAnalyze/propagation/`: Stage 2 root-independent hypothesis graph reconstruction (M1), root-conditioned propagation graphs and explanation-based reranking (M2), and path-validity logic.
- `Sys/RootCauseAnalyze/propagation_pipeline.py`: label-free propagation reconstruction entrypoint.
- `Sys/Score/evaluate_propagation.py`: propagation validity and optional label-aware evaluation.
- `Sys/Score/`: evaluation, trust-gate application, and failure analysis.
- `prompts/`: active LLM prompt templates; do not recreate root-level `utils/`.
- `scripts/common.sh`: single source of default server paths and model parameters.
- `scripts/run_rca_experiments.sh`: current main experiment driver.
- `Baseline/`: TraceRCA, NetEventCause, and BiAn baseline adapters.
- `docs/project_overview.md`: detailed project state and roadmap.

## Data And Artifacts

- `data/` is ignored and should stay local.
- `docs/papers/` keeps text extractions and summaries only.

## Figure Style

- Unless a task explicitly requests another visual language, use the reusable
  paper-diagram style prompt in `docs/论文流程图统一绘图风格与2stage提示词.md`.
- Keep research workflow figures as black-and-white monoline diagrams with
  sparse blue/orange accents, rounded stage panels, dashed evidence groups, and
  a left-to-right information flow.

## Common Commands

```bash
python -m pytest -q
source scripts/common.sh
python Sys/RootCauseAnalyze/stage1/neural_pipeline.py --help
python Sys/Score/evaluate_trust_gate.py --help
```
