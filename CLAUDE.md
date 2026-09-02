# Project Instructions

## Active Paper Design

The active task is Pingmesh fault-propagation graph reconstruction through an explicit two-stage system:

```text
Pingmesh context + raw task_topo + alarms/logs
  -> Stage 1 PC-STGR grouped-OOF root Top-K ranking
  -> Stage 2 P0 root-conditioned propagation-DAG reconstruction
  -> final root + device propagation DAG + evidence and alternatives
```

P0 deterministic evidence normalization is the paper method. P4 is a supervised grouped-OOF optimization track with validation-selected conservative edge admission. P1 is retired. `docs/论文方案.md` is the authoritative design and `docs/PC-STGR设计方案.md` defines Stage 1.

## Non-Negotiables

- Do not publish or track internal fault data.
- Do not call external LLM APIs in experiments.
- Runtime inference must not read root or propagation labels.
- Every emitted propagation edge must exist in raw `task_topo`.
- Unknown relations are masked, never converted to negatives.
- Use incident-grouped splits; calibration and thresholds must be selected inside the training fold.
- OOF predictions provide paper scores; full-data checkpoints are only for later unseen cases.
- Run tests with `python -m pytest`.

## Active Modules

- Stage 1: PC-STGR root location and Top-K candidate output.
- Stage 2: P0 evidence normalization, root conditioning, path search, and DAG merge.
- Final selection: combine normalized Stage-1 evidence with graph explanation quality.
- P4 optimization: supervised three-state edge probabilities using the same decoder.

## Evaluation

`scripts/run_full_experiment.sh` is the unified entrypoint. It runs P0 and P4 and writes root-location plus graph-rebuild metrics into `summary.json` and `summary.csv`. P0 artifacts are the primary paper output.

## Common Commands

```bash
python -m pytest -q
source scripts/common.sh
bash scripts/run_full_experiment.sh --dry-run
python Sys/RootCauseAnalyze/propagation_pipeline.py --help
python Sys/Score/evaluate_propagation.py --help
```
