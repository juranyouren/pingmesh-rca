# AGENT.md

## Project

This repository is a DCN root-cause analysis research prototype for Huawei Cloud
Pingmesh-triggered incidents. The `2stage` branch is the primary branch for the
current paper. Its target paper pipeline is:

`Pingmesh case data -> PC-STGR path-conditioned Device-Event graph ranking -> Stage 1 Top-K -> M1 root-independent hypothesis graph -> M2 root-conditioned graphs + explanation scores -> final ranking`

PC-STGR (Path-Conditioned Spatio-Temporal Graph Ranker) is the target Stage 1
design in `docs/PC-STGR设计方案.md`. The current `stage1/neural_*` implementation
and the 159-case OOF results are still IC-STGR artifacts. Do not rename its
checkpoints or 73.58/93.71/97.48 result as PC-STGR before the migration and a
new grouped OOF evaluation are complete. The deterministic topology+temporal
fusion is the strong white-box baseline.

## Non-Negotiables

- Internal fault data is not publishable. Do not move `data/` into tracked code.
- Do not call external LLM APIs for project experiments. The intended runtime is local vLLM on Ascend NPU servers.
- Do not let inference code read `label.json`; labels are only for evaluation.
- Run tests with `python -m pytest`, not bare `pytest`, unless a local `PYTHONPATH` is already configured.

## Key Paths

- `Sys/RootCauseAnalyze/stage1/`: current IC-STGR graph/model/OOF implementation plus deterministic temporal, alarm-topology, and fusion baselines; PC-STGR migration is pending.
- `Sys/RootCauseAnalyze/propagation/`: Stage 2 root-independent hypothesis graph reconstruction (M1), root-conditioned propagation graphs and explanation-based reranking (M2), and path-validity logic.
- `Sys/RootCauseAnalyze/propagation_pipeline.py`: label-free propagation reconstruction entrypoint.
- `Sys/Score/evaluate_propagation.py`: propagation validity and optional label-aware evaluation.
- `Sys/Score/`: Stage 1, Stage 2, propagation, and baseline evaluation tools.
- `prompts/`: baseline and ablation prompt templates; do not recreate root-level `utils/`.
- `scripts/common.sh`: single source of default server paths and model parameters.
- `scripts/run_paper_05_spatiotemporal_graph.sh`: current executable Stage 1 paper workflow (deterministic baseline + IC-STGR OOF + Stage 2).
- `scripts/run_stage2_edge_probability_ablation.sh`: Stage 2 P0/P1/P4 edge-probability comparison.
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
python Sys/RootCauseAnalyze/stage1/pipeline.py --help
python Sys/RootCauseAnalyze/stage1/neural_pipeline.py --help
python Sys/RootCauseAnalyze/propagation_pipeline.py --help
```
