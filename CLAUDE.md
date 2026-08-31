# AGENT.md

## Project

The active paper task is **Pingmesh heterogeneous fault-propagation graph
reconstruction**:

`observations -> M1 candidate heterogeneous evidence graph -> M2 root/relation probabilities -> M3 joint root-and-graph constrained reconstruction`

The main output contains a device propagation DAG, a jointly inferred root
device or link, an event-evolution explanation layer, evidence-grounding links,
and explicit alternatives/abstention. The device propagation DAG is the primary
quantitative object; events explain why its edges and root are selected.

The current device-only, externally root-conditioned code is a prototype and
baseline, not the new method architecture. Use `docs/论文方案.md` as the only
active paper-plan source. `docs/PC-STGR设计方案.md` is historical.

## Non-Negotiables

- Do not publish or track internal fault data.
- Do not call external LLM APIs in experiments.
- Runtime inference must not read root or propagation labels.
- Device propagation edges must exist in raw `task_topo`.
- Physical, ownership, temporal, and semantic relations are evidence, not
  deterministic causality.
- Unknown relations are masked, not labeled negative.
- Event-event outputs are dependency/evolution hypotheses unless causally
  labeled.
- Without engineer labels, report validity diagnostics, never root/path
  accuracy.
- Use incident-grouped splits and leakage-safe calibration.
- Run tests with `python -m pytest`.

## Active Paper Modules

- **M1:** evidence episodes plus candidate Device/Event/Symptom graph.
- **M2:** relation-aware encoder with a root-potential head, device-device
  three-state head, and event-event three-state head.
- **M3:** constrained joint root-and-graph decoder with topology, reachability,
  acyclicity, evidence coverage, alternatives, and identifiability.

Oracle-root decoding is a controlled evaluation mode. Joint root-graph inference
is the target setting.

## Current Code Status

`Sys/RootCauseAnalyze/propagation/heterogeneous/` now provides a runnable V0:
typed Device/Event/Symptom construction, internal heuristic root potentials,
DD/EE relations, bounded single-device-root joint search, event explanations,
and identifiability output. The older propagation files provide the reusable
device probability and DAG-decoding substrate.

V0 is not the final learned method. Relation-aware GAT, calibration, CP-SAT,
link roots, and multi-root reconstruction remain unimplemented.

PC-STGR and other `stage1` rankers are supporting baselines only. Compatibility
names such as `stage1`, `stage2`, `m1`, `m2`, and `two-stage-*` do not define the
paper structure.

## Current Priority

1. Run V0 on server data and audit heterogeneous evidence/schema failures.
2. Finalize labels and annotate a pilot set.
3. Verify M1 candidate recall.
4. Replace heuristic potentials with incident-grouped OOF learning/calibration.
5. Replace bounded enumeration with CP-SAT joint device/link-root inference.

## Common Commands

```bash
python -m pytest -q
source scripts/common.sh
python Sys/Preprocess/backfill_topology_context.py --help
python Sys/RootCauseAnalyze/heterogeneous_propagation_pipeline.py --help
python Sys/RootCauseAnalyze/propagation_pipeline.py --help
python Sys/Score/evaluate_propagation.py --help
```
