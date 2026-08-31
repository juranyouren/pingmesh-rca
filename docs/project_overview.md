# Pingmesh Heterogeneous Fault-Propagation Graph Project Overview

## Active Direction

As of 2026-08-28, the paper has one primary task: **reconstruct a globally
consistent, evidence-grounded heterogeneous fault-propagation graph from each
Pingmesh incident**.

```text
Pingmesh context + raw task_topo + alarms/logs
  -> M1 candidate Device/Event/Symptom evidence graph
  -> M2 root potentials + local DD/EE relation probabilities
  -> M3 joint root-and-graph constrained reconstruction
  -> root + device propagation DAG + event explanation + uncertainty
```

The root is not required as an upstream input in the target setting. It is a
latent source variable selected together with the graph. An oracle root can be
injected only for controlled evaluation that isolates propagation-reconstruction
quality.

The detailed and authoritative design is
[`docs/论文方案.md`](./论文方案.md). The former device-only and PC-STGR-first plans
are retained only as implementation history and baselines.

## 1. Output Semantics

The final heterogeneous explanation graph has three clearly separated layers:

| Layer | Relation | Role |
| --- | --- | --- |
| Device backbone | directed Device → Device propagation edges | Primary reconstructed propagation DAG; every edge must exist in raw `task_topo` |
| Event explanation | directed Event → Event dependency/evolution edges | Explains temporal and semantic development without overstating causality |
| Evidence grounding | Device ↔ Event observed-on/ownership links | Connects inferred structure to raw alarms and logs; not a propagation edge |

The output also includes a root device or root link, edge confidence, evidence
references, Top-K near-optimal alternatives, and an identifiability/abstention
decision. The method may return a partial graph when the evidence is
insufficient.

## 2. Problem Boundary

Pingmesh observes end-to-end reachability symptoms rather than the internal
fault process. Raw physical topology, timestamps, alarm semantics, and peer
relations constrain the possible explanation, but none independently proves a
propagation direction. ECMP, missing alarms, timestamp uncertainty, repeated
alarm templates, and concurrent faults can make multiple graphs observationally
equivalent.

The task therefore does not claim to recover the true packet-by-packet path. It
seeks the best supported global explanation while exposing ambiguity instead of
inventing certainty.

## 3. Method Modules

| Module | Input | Core operation | Output |
| --- | --- | --- | --- |
| **M1 Evidence modeling and candidate graph** | Pingmesh source/destination and time window, raw `task_topo`, alarms/logs | Normalize records into event episodes; select endpoint corridor, event-bearing devices, necessary connectors, and symptoms | Candidate heterogeneous graph `G_c` with Device/Event/Symptom nodes and typed evidence edges |
| **M2 Heterogeneous relation learning** | `G_c` and node/edge evidence features | Relation-aware graph encoding plus root, device-device, and event-event prediction heads | Root potentials; `A→B / B→A / No Direct`; `Ei→Ej / Ej→Ei / No Dependency`; calibrated probabilistic graph `H` |
| **M3 Globally constrained reconstruction** | `H`, raw topology constraints, evidence coverage requirements, optional oracle root | Joint combinatorial optimization over root, selected nodes, DD edges, EE edges, and symptom coverage | Root + topology-valid device DAG + event explanation + evidence traces + alternatives/identifiability |

### M1: candidate heterogeneous evidence graph

Node types are `Device`, `Event`, and `Symptom`. Candidate edges distinguish raw
physical adjacency, event ownership/observation, endpoint association, and
event-event candidate relations. M1 only restricts the search space; its edges
must never be drawn as confirmed propagation.

M1 should preserve high recall for engineer-labeled required nodes and edges.
That recall is a hard upper bound on all downstream results and is evaluated
separately from M2 and M3.

### M2: local probabilistic relations

The proposed encoder is a two-layer relation-aware GAT with four 16-dimensional
heads per layer, residual connections, LayerNorm, and a feed-forward block. Its
three heads predict:

1. a unary root potential for every device and virtual link-root candidate;
2. a swap-equivariant three-state relation for every candidate device pair;
3. a three-state dependency/evolution relation for every candidate event pair.

The root potential is an input to M3, not an independently finalized ranking.
Device relation prediction must not receive the selected root identity. Event
relations are auxiliary until reliable event-dependency labels exist.

### M3: joint global reconstruction

The first implementation target is CP-SAT or an equivalent constrained integer
optimizer. It maximizes calibrated relation/root scores and evidence coverage,
while penalizing unsupported graph size, bridge use, conflicts, and excessive
roots. Constraints enforce raw-topology validity, one direction per physical
edge, root reachability, non-root parent support, acyclicity, symptom coverage,
and evidence consistency.

Two evaluation modes share the same decoder:

- **Oracle-root:** fix the root to measure graph reconstruction independently.
- **Joint:** infer a device or link root together with the graph; this is the
  target system setting.

Top-K near-optimal solutions are retained so observational equivalence becomes
an explicit result rather than a hidden model error.

## 4. Labels and Leakage Control

The current case root labels are insufficient for the main paper claim. A pilot
annotation set should include root device/link, required and allowed device
nodes, required and allowed directed DD edges, event dependencies where
identifiable, acceptable alternatives, explicit no-direct relations, and
unidentifiable cases.

Local relation labels use four annotation states:

- `definite`: one direction is supported;
- `possible`: a set of states remains acceptable;
- `explicit_no_direct`: evidence supports no direct propagation/dependency;
- `unknown`: insufficient evidence; mask it from supervised loss.

Split by incident group. Use fold-local vocabularies, negative sampling,
training, calibration, and threshold selection. Normalize loss per case so
large topologies do not dominate merely because they contain more edges.

## 5. Evaluation

Evaluation follows the error decomposition `M1 recall -> M2 relation quality ->
M3 graph quality -> joint root-and-graph quality`.

- **M1:** required-node/edge coverage, candidate reduction ratio, candidate
  size, and construction time.
- **M2:** DD/EE Macro-F1 and per-state PR, root Top-K/MRR as an auxiliary head,
  calibration error, Brier/NLL, and case-macro metrics.
- **M3 oracle-root:** directed-edge and node Precision/Recall/F1, graph edit
  distance, exact/tolerant match, DAG/topology validity, symptom coverage,
  evidence grounding, and coverage-risk.
- **M3 joint:** root Top-K/MRR, joint root-and-graph success, device-root versus
  link-root accuracy, alternative-set coverage, and identifiability quality.

Without engineer graph labels, DAG rate, topology validity, evidence coverage,
and graph size are diagnostics only—not path accuracy.

## 6. Scientific Challenges

1. **Latent Propagation Inference from Circumstantial Evidence:** observations
   constrain propagation but do not directly identify it.
2. **Globally Consistent Reconstruction from Locally Uncertain Relations:**
   locally plausible directions can conflict, create cycles, or fail to connect
   root and symptoms.
3. **Identifiability under Observational Equivalence:** several root/graph
   explanations can generate nearly the same observations.

These challenges map directly to the paper design: heterogeneous evidence
modeling, probabilistic local relation learning plus constrained decoding, and
near-optimal alternatives with calibrated abstention.

## 7. Current Implementation Boundary

The repository now contains a runnable heterogeneous V0 under
`Sys/RootCauseAnalyze/propagation/heterogeneous/` and a root-input-free CLI at
`Sys/RootCauseAnalyze/heterogeneous_propagation_pipeline.py`. It implements:

- typed Device/Event/Symptom candidate graph construction;
- internal interpretable device-root potentials;
- reusable DD three-state probabilities and heuristic EE three-state relations;
- bounded enumeration of single-device roots with topology-valid DAG decoding;
- event explanations, evidence grounding, alternatives, and a score-margin
  identifiability result.

V0 is an end-to-end engineering baseline, not the final paper model. It does not
yet implement:

- a learned Relation-aware GAT over the heterogeneous graph;
- supervised/calibrated root and event-relation heads;
- exact CP-SAT joint optimization;
- link-root or multi-root reconstruction;
- posterior-quality Top-K near-optimal heterogeneous explanations.

`scripts/README.md` documents the legacy/prototype entrypoints. Historical
PC-STGR, PC-STGR-SSL, IC-STGR, deterministic rankers, and external RCA baselines
remain useful comparisons but do not define the new method.

## 8. Immediate Priorities

1. Run V0 on full server data and audit schema failures, graph sizes, missing
   topology/events, runtime, and output validity.
2. Finalize the annotation protocol and label a small, diverse pilot set.
3. Measure M1 candidate recall and identify evidence lost before learning.
4. Train and calibrate M2 with incident-grouped OOF evaluation.
5. Implement/evaluate M3 in oracle-root mode, then add joint device/link-root
   inference and near-optimal alternatives.

## Maintenance Rules

- Keep generated data, checkpoints, and result artifacts out of Git.
- Keep this file and `AGENT.md` aligned with `docs/论文方案.md`.
- Do not turn preprocessing, annotation tooling, or baselines into extra paper
  modules.
- Do not equate observation, ownership, topology, or temporal order with a
  confirmed causal edge.
- Use `docs/论文流程图统一绘图风格与传播图重构提示词.md` for method figures.
