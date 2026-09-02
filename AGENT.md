# AGENT.md

## Project

This repository studies **Pingmesh fault-propagation graph reconstruction**.
The active paper design is:

`Pingmesh anomaly + raw task_topo + alarms/logs -> Stage 1 PC-STGR root ranking -> Stage 2 P0 root-conditioned propagation-DAG reconstruction`

The output is an evidence-grounded heterogeneous explanation graph containing:

- a device-level directed propagation DAG as the primary result;
- a root device selected from the Stage-1 Top-K ranking and optionally reranked
  by graph explanation quality;
- an event-evolution/dependency layer that explains the device path;
- device-event observation links that ground conclusions in raw evidence;
- alternative hypotheses and an identifiability/abstention decision.

P0 deterministic evidence normalization is the approved paper method. P4 is a
supervised optimization track and must be reported separately until it exceeds
P0 on graph-reconstruction quality. P1 is retired from the active experiment
matrix. Use `docs/论文方案.md` as the active source of truth and
`docs/PC-STGR设计方案.md` as the Stage-1 implementation contract.

## Non-Negotiables

- Internal fault data is not publishable. Do not move `data/` into tracked code.
- Do not call external LLM APIs for project experiments. The intended runtime is
  local vLLM on Ascend NPU servers.
- Runtime inference must not read `label.json`, root labels, or propagation-path
  labels.
- Every emitted device-device propagation edge must correspond to an edge in
  the case's raw `task_topo`.
- Physical adjacency, device-event ownership, timestamp order, and alarm
  semantics are circumstantial evidence, not deterministic causal edges.
- Event-event outputs are dependency/evolution hypotheses unless stronger
  causal labels are available.
- Unknown relations must be masked rather than treated as negative labels.
- Without engineer propagation labels, validity checks must not be reported as
  root or path accuracy.
- Split and calibrate by incident group. No event, edge, or device instance from
  a held-out incident may leak into training or threshold selection.
- Run tests with `python -m pytest`, not bare `pytest`, unless `PYTHONPATH` is
  already configured.

## Active Paper Modules

- **Stage 1 — Root location:** PC-STGR produces a calibrated Top-K device
  ranking from Pingmesh context, topology, alarms, and event timing.
- **Stage 2 — Graph rebuild:** P0 constructs root-independent device-pair
  evidence, conditions it on each Top-K root, and decodes a topology-valid,
  root-reachable, acyclic propagation DAG.
- **Final selection:** combine Stage-1 root evidence and graph explanation
  quality to select the reported root and graph while retaining alternatives.

The oracle-root setting remains a controlled evaluation of graph reconstruction.

## Current Implementation Status

The active implementation is under `stage1/`, `propagation/`, and
`propagation_pipeline.py`. The heterogeneous V0 remains a historical prototype.
P4 uses a grouped-OOF supervised three-state edge classifier with fold-local
probability calibration and conservative edge admission; it is an optimization
experiment, not the paper method.

Useful prototype paths:

- `Sys/RootCauseAnalyze/propagation/episodes.py`: event normalization.
- `Sys/RootCauseAnalyze/propagation/topology_context.py`: raw topology context.
- `Sys/RootCauseAnalyze/propagation/candidates.py`: device candidate subgraph.
- `Sys/RootCauseAnalyze/propagation/scorer.py` and `propagation/m1/`: current
  device-edge probability prototype.
- `Sys/RootCauseAnalyze/propagation/solver.py`: current constrained decoder.
- `Sys/RootCauseAnalyze/propagation_pipeline.py`: current compatibility entry.
- `Sys/RootCauseAnalyze/heterogeneous_propagation_pipeline.py`: root-input-free
  V0 heterogeneous entrypoint.
- `Sys/Score/evaluate_propagation.py`: graph validity and optional label metrics.

Compatibility names `m1` and `m2` remain in code, but the paper uses the simpler
Stage-1 root-location / Stage-2 graph-rebuild terminology. PC-STGR is active;
IC-STGR and deterministic root rankers are baselines.

## Current Priority

1. Treat P0 as the paper system and reproduce its grouped-OOF root and graph
   metrics through `scripts/run_full_experiment.sh`.
2. Optimize P4 precision without using held-out labels for threshold selection.
3. Report root-location and graph-rebuild metrics together in `summary.json/csv`.
4. Add oracle-root evaluation and analyze error propagation from Stage 1.
5. Consider link-root and multi-root extensions only after the single-root
   system is stable.

## Figure Style

Use `docs/论文流程图统一绘图风格与传播图重构提示词.md`. Figures must distinguish
physical/observation relations from inferred propagation relations and show the
explicit Stage-1 ranking to Stage-2 graph-rebuild dependency.

## Common Commands

```bash
python -m pytest -q
source scripts/common.sh
python Sys/Preprocess/backfill_topology_context.py --help
python Sys/RootCauseAnalyze/heterogeneous_propagation_pipeline.py --help
python Sys/RootCauseAnalyze/propagation_pipeline.py --help
python Sys/Score/evaluate_propagation.py --help
```
