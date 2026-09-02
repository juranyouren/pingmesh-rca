# Pingmesh Root-Conditioned Fault-Propagation Graph Project Overview

## Active Direction

As of 2026-09-02, the paper uses an explicit two-stage system:

```text
Pingmesh context + raw task_topo + alarms/logs
  -> Stage 1 PC-STGR grouped-OOF root Top-K ranking
  -> Stage 2 P0 root-conditioned propagation-DAG reconstruction
  -> final root + device propagation DAG + evidence and alternatives
```

The primary task is propagation-graph reconstruction. Root ranking is the
required upstream stage that provides a small set of source hypotheses. P0 is
the approved paper method. P4 is a supervised optimization track; P1 is retired.

The authoritative design is [`论文方案.md`](./论文方案.md). The Stage-1 contract
is [`PC-STGR设计方案.md`](./PC-STGR设计方案.md).

## Output

The system outputs:

- a final root device selected from the Stage-1 Top-K candidates;
- a directed, topology-valid, root-reachable, acyclic device propagation graph;
- raw topology edge IDs and alarm/event evidence for selected edges;
- alternative root-conditioned paths and diagnosability information.

The system reconstructs an evidence-consistent device-level explanation. It
does not claim to recover the actual packet-level ECMP route.

## Stage 1: Root Location

PC-STGR builds a path-conditioned Device–Event graph and produces case-local
root probabilities. The paper uses incident-grouped OOF predictions and reports
Top-1, Top-3, Top-5, MRR, and candidate recall. The all-data checkpoint is only
for later unseen incidents.

## Stage 2: Graph Rebuild

P0 builds a root-independent device-pair evidence graph over raw physical
adjacency. For each Top-K root it:

1. computes device distance from the root;
2. keeps evidence-supported directions that move outward from the root;
3. searches root-to-symptom paths;
4. merges compatible paths into a propagation DAG;
5. combines graph explanation quality with Stage-1 root evidence.

Every emitted edge must map to at least one raw `task_topo` edge ID.

## P4 Optimization

P4 replaces P0's direct evidence normalization with a grouped-OOF three-state
classifier: `A→B / B→A / No Direct`. Unknown labels remain masked. Fold-local
validation selects temperature, a minimum directional probability, and a
minimum margin over `No Direct`. Directional F0.5 is used for selection because
false-positive edges rapidly expand the decoded graph.

P4 remains an optimization experiment until its graph-rebuild metrics exceed
P0. Historical pre-optimization P4 results must not be reused after threshold
changes.

## Evaluation

The unified result separates but co-locates two metric groups:

- **Root Location:** Stage-1 Top-K/MRR and post-graph selected-root accuracy;
- **Graph Rebuild:** directed-edge P/R/F1, node P/R/F1, strict exact rate,
  topology validity, DAG validity, root reachability, coverage, and graph size.

Predictions and labels are projected through the same evidence-free exact
structural-equivalence map for the default metrics. Raw-device metrics can be
requested separately.

## Entry Points

| Entry point | Purpose |
| --- | --- |
| `scripts/run_full_experiment.sh` | Root OOF, P0 primary result, P4 optimization, unified metrics |
| `scripts/run_root_oof.sh` | PC-STGR and deterministic root-location experiments |
| `scripts/run_dd_edge_ablation.sh` | Focused P0 versus P4 comparison |
| `Sys/Score/summarize_full_experiment.py` | Build unified `summary.json/csv` |
| `Sys/Score/evaluate_propagation.py` | Per-case and aggregate graph evaluation |
| `scripts/run_heterogeneous_v0.sh` | Historical heterogeneous V0 prototype |

## Immediate Priorities

1. Re-run the unified grouped-OOF experiment after P4 admission optimization.
2. Compare P0 and P4 predicted/annotated edge-count ratios and exact matches.
3. Add oracle-root evaluation to isolate Stage-2 performance.
4. Audit P4 `No Direct` confusion and per-fold selected thresholds.
5. Consider link-root and multi-root extensions after the single-root system is stable.

## Maintenance Rules

- Keep internal data, generated checkpoints, labels, and result artifacts out of Git.
- Keep this file, `AGENT.md`, `CLAUDE.md`, and `论文方案.md` aligned.
- Runtime inference must not read root or propagation labels.
- Unknown relations must never be converted to negative labels.
- Hyperparameters and thresholds must be selected without held-out leakage.
- Use `docs/论文流程图统一绘图风格与传播图重构提示词.md` for figures.
