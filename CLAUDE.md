# Project Instructions

Updated: 2026-09-11. Read [AGENT.md](AGENT.md) for the shared project contract.
This file summarizes the same current scope and execution priorities.

## Active Paper Design

The paper system is **RPG-Recon**, studying incident-specific device propagation
graph reconstruction for WWW 2027. Root ranking supplies alternative origins;
the device explanation DAG is the primary output.

```text
Pingmesh context + raw task_topo + alarms/logs
  -> Stage 1 PC-STGR grouped-OOF root Top-K ranking
  -> Stage 2 P0 root-conditioned propagation-DAG reconstruction
  -> final root + device propagation DAG + evidence and alternatives
```

P0 deterministic evidence normalization is the paper method. P4 is a separate
supervised optimization track; P1 is retired. Keep the single-device-root scope:
Top-K denotes competing origins, not multiple simultaneous roots. Multi-root
and link-root extensions remain deferred.

## Current Sources and Paper Argument

- [WWW paper index](docs/conferences/WWW2027/README.md) and
  [2026-09-10 execution record](docs/conferences/WWW2027/2026-09-10_后续任务执行记录.md)
  govern the current writing and task order.
- [Graph metric protocol](docs/conferences/WWW2027/故障传播图指标调研与最终评价方案.md)
  governs new evaluation work. Its implementation is not yet complete.
- [Root README](README.md) and [docs index](docs/README.md) are the navigation
  entry points for the current method, paper, experiment, and run commands.
- [Project overview](docs/project_overview.md) and
  [PC-STGR design](docs/PC-STGR设计方案.md) describe the implementation. They
  defer to the dated execution record rather than listing their own priorities.
- [Baseline README](Baseline/README.md) defines method names, input eligibility,
  reproduction boundaries, and commands. Retired documents remain deleted.

The current WWW positioning is Web Infrastructure and Agentic Systems, based
on the 2026-09-10 research. Establish actual service/network dependencies and
diagnostic value; verify the official CFP when making submission decisions.
Do not use Industry/Companion examples as Research Track evidence.

**C1:** uncertain origins change which graph structures can be reconstructed.
M1 candidate generation and M3 conditional assembly jointly address it;
ordinary RCA, Top-K, and topology/time fusion alone are not novelty.
**C2:** direct device relations and directions remain ambiguous under incomplete
evidence. **C3:** locally supported relations may not form a coherent graph.

The user has no field investigation record available. Use the synthetic
DEMO_001 `info.json`/`nodes.json` and clearly illustrative operator actions.
Its historical demo predictions contain constructed evidence and are not
observations or labels. A troubleshooting tree organizes investigation actions;
the output DAG organizes device influence hypotheses. Do not invent production
cases, manual actions, SLO/MTTR savings, or Web request failures.

## Non-Negotiables

- Do not publish or track internal fault data.
- Do not call external LLM APIs in experiments.
- Runtime inference must not read root or propagation labels. Training uses only
  authorized training-fold labels; the explicit Oracle evaluation wrapper may
  supply a confirmed test root. Test propagation labels are evaluation-only.
- Every emitted propagation edge must exist in raw `task_topo`.
- Unknown relations are masked, never converted to negatives.
- Allowed edges are neutral; engineers must resolve the meaning of `possible`.
- Physical adjacency, timestamp order, alarm semantics, and device-event ownership
  are evidence, not confirmed causal edges. The output is not an ECMP packet route
  or an identified intervention model; event relations are dependency hypotheses.
- Use incident-grouped splits; calibration and thresholds must be selected inside the training fold.
- Verify actual incident groups. OOF predictions require a consistent evaluator;
  full-data checkpoints are for later unseen cases. Previously used development
  data cannot be relabeled as an untouched independent test set.
- Run tests with `python -m pytest`.

## Active Modules

- **M1 = Stage 1 / PC-STGR:** endpoint-conditioned device/event representation
  and Top-K origin hypotheses; no exact forwarding path is assumed.
- **M2 + M3 = Stage 2 / P0:** reusable local directional support followed by
  root-conditioned path selection and DAG assembly. Paper module numbers differ
  from historical `m1/m2` code directories.
- P0 support is not calibrated causal probability. Its strictly increasing
  shortest-hop distance rule is a modeling restriction stronger than a general
  root-reachable DAG and can exclude annotated edges; decoding is not guaranteed
  globally optimal.
- Final root/graph selection follows the actual frozen configuration. Report
  corrections and corruptions; neither improved root accuracy nor reliable
  abstention/fallback is guaranteed by the proposed design.
- P4 replaces local support with supervised three-state probabilities and uses
  the same decoder; keep its supervision and results separate from P0.

## Evaluation

The proposed `graph-eval-v2` protocol is specified, not fully implemented.
`Sys/Score/evaluate_propagation.py` retains legacy possible/allowed, uncertain
root, implicit-node, and exact-match behavior. `Baseline/common/evaluation.py`
already has masks/failure accounting but still needs integration and protocol
checks. Unify these before presenting comparative paper scores.

- Core: case-macro directed-edge P/R/F1; separate complete and partially reviewed
  labels and attach each metric's denominator. Explicit nodes include an isolated
  root. Exact-Graph/Joint-Exact require complete reviewed labels.
- Show raw and structural-equivalence views side by side, using the same frozen,
  label-independent map. This is not Markov equivalence; projected negatives
  require all raw possibilities to be confirmed negative.
  Root correctness remains on raw device IDs, including joint metrics.
- Separate successful empty graphs, partial outputs, abstention, failure, and
  missing labels. Keep failures in the applicable denominator; unknown scope
  does not receive an empty-set perfect score.
- Root reports Top-K/MRR and actual candidate coverage. Oracle uses a confirmed
  root; Shared uses the same frozen OOF predicted root; Full uses each method's
  own root/graph and reports Top-1, Edge-F1, and Joint-Edge-F1.
- Candidate Oracle and Direct Oracle were already run in the 2026-09-08 record.
  Re-score them consistently; Candidate Oracle is still Top-K limited.
- Validity/traceability/coverage are diagnostics. SHD-1 and ancestor-reachability
  F1 are complete-label auxiliary metrics; SID is inappropriate for the current
  explanation semantics. Use paired bootstrap over verified incident groups.
- Freeze data, labels, folds, adapters, thresholds, and evaluator versions;
  report scoring/label revisions separately from algorithm improvements.

## Baseline State and Immediate Priorities

New baselines use `Baseline/common/` with `SkyNetVoting/`, `BiAnAdapt/`,
`NetEventCauseDevice/`, `PCMCIPlus/`, and `DYNOTEARS/`. Retain inspired/adapt/reimpl
names. Do not substitute legacy scripts, silently fill missing time bins, borrow
P0 as an external method's adapter, or attribute `X + P0` graphs to root-only X.
Preserve native/projected/adapted graphs and all input-ineligible/failure records.
SkyNetVoting/BiAnAdapt are root-only; NEC supports root, graph, and Full tasks.
PCMCI+/DYNOTEARS support eligible Oracle/Shared graph tasks, not own-root Full.

Last recorded validation on 2026-09-10: 206 main tests, 22 labeler tests, and
synthetic NEC 6/6 predictions across three folds. This is functional acceptance,
not reproduced paper accuracy. BiAn's real local backend was unavailable then;
probe it before use. Time-series input coverage must be verified.

1. Audit and freeze label semantics, confirmed single-root scope, completeness,
   and true incident groups with engineers; do not silently rewrite labels.
2. Unify main-method/baseline scoring, explicit nodes, masks, projection rules,
   output statuses, and failure denominators.
3. Re-score existing predictions and Oracle outputs; add the Shared predicted-root
   control and isolate root selection from graph reconstruction.
4. Verify baseline inputs and local BiAn service, then run matched comparisons.
5. Obtain a real incident, service-to-endpoint evidence, and measured operator
   tasks before claiming operational benefits.

Broad P4 tuning, additional LLM reranking, and multi-root work are deferred.
Use the current Chinese outline and linked case design for figures; existing
PNGs contain older illustrative content and do not prove implemented behavior.

## Common Commands

From the Windows repository root, reuse the existing CPU validation environment:

```powershell
& tmp/baselines-venv/Scripts/python.exe -m pytest tests -q
& tmp/baselines-venv/Scripts/python.exe -m pytest pingmesh-propagation-labeler/tests -q
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common --help
```

In the configured Linux/NPU environment:

```bash
source scripts/common.sh
bash scripts/run_full_experiment.sh --dry-run
```

The full-experiment entrypoint runs P0/P4 and writes root/graph summaries; its
existing evaluator must be reconciled with the new protocol before paper use.
