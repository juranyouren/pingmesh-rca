# AGENT.md

## Project

This repository studies **Pingmesh fault-propagation graph reconstruction**.
The active paper design is:

`Pingmesh anomaly + raw task_topo + alarms/logs -> M1 candidate heterogeneous evidence graph -> M2 root potentials and local relation probabilities -> M3 jointly constrained root-and-graph reconstruction`

The output is an evidence-grounded heterogeneous explanation graph containing:

- a device-level directed propagation DAG as the primary result;
- a root device or root link inferred together with the graph;
- an event-evolution/dependency layer that explains the device path;
- device-event observation links that ground conclusions in raw evidence;
- alternative hypotheses and an identifiability/abstention decision.

The previous device-only, externally root-conditioned implementation remains a
prototype and baseline. It does not define the new paper architecture. Use
`docs/论文方案.md` as the only active source of truth. Treat
`docs/PC-STGR设计方案.md` as a historical implementation record.

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

- **M1 — Evidence modeling and candidate heterogeneous graph:** normalize
  alarms/logs into event episodes and select devices, events, symptoms, physical
  links, and observation links relevant to the incident.
- **M2 — Heterogeneous relation learning:** use a relation-aware graph encoder
  to predict root potentials, device-device three-state probabilities
  (`A→B / B→A / No Direct`), and event-event three-state probabilities
  (`Ei→Ej / Ej→Ei / No Dependency`).
- **M3 — Globally constrained reconstruction:** jointly select the root and a
  topology-valid, root-reachable, acyclic device propagation graph, then attach
  event explanations, evidence traces, alternatives, and uncertainty.

The oracle-root setting fixes the root only for controlled evaluation. Joint
root-graph inference is the target system setting.

## Current Implementation Status

The code now contains two implementation levels:

- `Sys/RootCauseAnalyze/propagation/heterogeneous/` implements the runnable V0
  heterogeneous baseline: typed Device/Event/Symptom construction, internal
  root potentials, DD/EE probabilistic relations, bounded single-device-root
  joint search, event explanations, and identifiability output.
- The older files under `Sys/RootCauseAnalyze/propagation/` remain the reusable
  device-level probability and DAG-decoding substrate.

V0 is not the final learned method. Root and EE potentials are interpretable
heuristics, the decoder enumerates a bounded set of device roots, and link-root,
multi-root, Relation-aware GAT, calibrated probabilities, and CP-SAT remain to
be implemented.

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

Compatibility names such as `stage1`, `stage2`, `m1`, `m2`, and `two-stage-*`
do not define the paper modules. PC-STGR, PC-STGR-SSL, IC-STGR, and deterministic
root rankers are supporting baselines or optional candidate generators only.

## Current Priority

1. Run V0 on full server data and audit schema failures, candidate sizes,
   topology availability, empty-event cases, and runtime.
2. Finalize the relation-label schema and annotate a representative pilot set.
3. Measure M1 candidate-subgraph recall before optimizing downstream models.
4. Replace V0 root/DD/EE heuristics with incident-grouped learned heads and
   calibrated OOF probabilities.
5. Replace bounded device-root enumeration with CP-SAT device/link-root decoding
   and Top-K near-optimal alternatives.

## Figure Style

Use `docs/论文流程图统一绘图风格与传播图重构提示词.md`. Figures must distinguish
physical/observation relations from inferred dependency and final propagation
relations, and must show the root as a joint output rather than a mandatory
upstream ranking.

## Common Commands

```bash
python -m pytest -q
source scripts/common.sh
python Sys/Preprocess/backfill_topology_context.py --help
python Sys/RootCauseAnalyze/heterogeneous_propagation_pipeline.py --help
python Sys/RootCauseAnalyze/propagation_pipeline.py --help
python Sys/Score/evaluate_propagation.py --help
```
