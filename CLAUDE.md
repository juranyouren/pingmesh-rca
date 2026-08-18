# AGENT.md

## Project

This repository is a DCN root-cause analysis research prototype for Huawei Cloud
Pingmesh-triggered incidents. The target paper pipeline is:

`Pingmesh case data -> PC-STGR Stage 1 Top-K -> Stage 2/M1 root-independent hypothesis graph -> Stage 2/M2 root-conditioned graphs and reranking`

PC-STGR is the Stage 1 design recorded in `docs/PC-STGR设计方案.md`. The current
`stage1/neural_*` implementation has migrated to PC-STGR, but a fresh grouped
OOF evaluation is still pending. The existing 159-case scores remain historical
IC-STGR artifacts and must not be reported as PC-STGR results.

## Non-Negotiables

- Internal fault data is not publishable. Do not move `data/` into tracked code.
- Do not call external LLM APIs for project experiments. The intended runtime is local vLLM on Ascend NPU servers.
- Do not let inference code read `label.json`; labels are only for evaluation.
- Run tests with `python -m pytest`, not bare `pytest`, unless a local `PYTHONPATH` is already configured.

## Key Paths

### Core pipeline
- `Sys/RootCauseAnalyze/stage1/`: current PC-STGR implementation and deterministic Stage 1 baselines.
- `Sys/RootCauseAnalyze/propagation/`: Stage 2 M1/M2 reconstruction and reranking.
- `Sys/RootCauseAnalyze/propagation_pipeline.py`: label-free Stage 1 → Stage 2 entrypoint.

### Evaluation
- `Sys/Score/Score_N.py`: Top-K hit-rate evaluation for canonical rankings and response payloads.
- `Sys/Score/evaluate_propagation.py`: Stage 2 validity and optional label-aware evaluation.
- `Sys/Score/score_utils.py`: backward-compat shim → real implementations in `Sys/utils/io_utils.py`.

### Utilities & config
- `Sys/config.py`: single Python-side config reading env vars set by `scripts/common.sh`.
- `Sys/utils/io_utils.py`: canonical I/O helpers (`load_json`, `save_json`, `write_jsonl`, `write_csv`, `case_id_from_dir`, `dedupe`, `hit_at`). **Prefer this over `score_utils`.**
- `Sys/utils/npu_utils.py`: Ascend NPU memory inspection and waiting (`get_npu_memory_info`, `wait_npu_memory`).
- `Sys/utils/case_utils.py`: case file discovery, node/info loading, ground-truth reading.
- `Sys/utils/alarm_utils.py`: alarm/event extraction and weight helpers.
- `Sys/utils/ranking_utils.py`: stable score sorting and fusion helpers.

### Prompts, scripts, data
- `prompts/`: baseline and ablation prompt templates; do not recreate root-level `utils/`.
- `scripts/common.sh`: single source of default server paths and model parameters.
- `scripts/run_paper_05_pc_stgr.sh`: current executable Stage 1 paper workflow.
- `scripts/run_stage2_edge_probability_ablation.sh`: Stage 2 edge-probability ablation.
- `Baseline/`: TraceRCA, NetEventCause, and BiAn baseline adapters.
- `docs/project_overview.md`: detailed project state and roadmap.

## Data And Artifacts

- `data/` is ignored and should stay local.
- `docs/papers/` keeps text extractions and summaries only.

## Common Commands

```bash
python -m pytest -q
source scripts/common.sh
python Sys/RootCauseAnalyze/stage1/pipeline.py --help
python Sys/RootCauseAnalyze/stage1/neural_pipeline.py --help
python Sys/RootCauseAnalyze/propagation_pipeline.py --help
```
