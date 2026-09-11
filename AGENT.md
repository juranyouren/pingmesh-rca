# AGENT.md

Updated: 2026-09-11. Project state incorporates the 2026-09-10 research and
validation record. Follow the user's latest instructions when scope changes.

## Project

This repository studies **RPG-Recon: incident-specific, root-conditioned
device fault-propagation graph reconstruction**, targeting WWW 2027.
The primary task is graph recovery; root ranking supplies competing origins.
The active implementation is:

`Pingmesh anomaly + raw task_topo + alarms/logs -> Stage 1 PC-STGR root ranking -> Stage 2 P0 root-conditioned propagation-DAG reconstruction`

The primary output is a device-level directed explanation DAG, with a selected
device origin, available evidence references, alternatives, and unresolved
relations. Event dependency/evolution and device-event observation links are
supporting evidence layers, not the primary graph-recovery target.

Use a **single-device-root** model. Top-K denotes alternative single-root
hypotheses, not simultaneous roots. Multi-root and link-root extensions remain
deferred. Do not force uncertain or multi-root labels into a confirmed single
root by selecting the first listed device.

P0 deterministic evidence normalization is the approved paper method. P4 is a
supervised optimization track and must be reported separately until it exceeds
P0 on graph-reconstruction quality. P1 is retired from the active experiment
matrix. Further P4 tuning is not the immediate priority.

## Read These Sources

- [Root README](README.md) and [docs index](docs/README.md): navigation entry points.
- [Paper index](docs/conferences/WWW2027/README.md): current manuscript and research.
- [Execution record](docs/conferences/WWW2027/2026-09-10_后续任务执行记录.md): completed
  work, evidence gaps, and current task order.
- [Graph evaluation protocol](docs/conferences/WWW2027/故障传播图指标调研与最终评价方案.md):
  selected metrics, label semantics, and implementation gaps.
- [Challenge design](docs/conferences/WWW2027/Challenge设计：从普通根因定位转向故障图恢复.md)
  and [case design](docs/conferences/WWW2027/论文引入设计：从工程师排障现场到传播图恢复.md):
  current scientific argument and illustrative opening.
- [Implementation overview](docs/project_overview.md) and
  [PC-STGR contract](docs/PC-STGR设计方案.md): method and code organization.
- [Baseline contract](Baseline/README.md): supported tasks, adapters, and reproduction limits.

Use the dated execution record and evaluation protocol for priorities and
scoring decisions; the implementation overview now defers to them instead of
carrying its own priority list.
Retired design and figure documents were intentionally deleted. Do not restore
them or treat dangling references in older notes as active requirements.

## Paper Argument and Evidence

- Submission positioning from the 2026-09-10 WWW 2024-2026 research is
  **Web Infrastructure and Agentic Systems**. Explain the concrete Web service
  dependency and diagnostic problem on the first page. Recheck the official
  CFP when making submission decisions; industry papers are not Research Track
  precedents. Adding an LLM or Web terminology does not establish relevance.
- **C1:** origin uncertainty changes the space of reconstructable graphs.
  Candidate generation and conditional graph assembly jointly address it;
  ordinary RCA difficulty, Top-K, or topology/time fusion alone is not novelty.
- **C2:** incomplete evidence leaves direct relations and directions ambiguous.
- **C3:** locally supported relations may not form one coherent incident graph.
- The user has no field investigation record available. The opening uses
  synthetic `DEMO_001` observations and an illustrative operator workflow.
  A troubleshooting tree organizes questions/actions; the output DAG organizes
  device influence hypotheses. They are not interchangeable graph labels.
- For the opening, use only the demo's `info.json` and `nodes.json` observations.
  The historical `demo_predictions.json` contains constructed events/scores
  absent from those observations; it is not evidence or ground truth.
- Do not invent production incidents, operator actions, Web request failures,
  SLO/MTTR improvements, or user-study results. Existing figure PNGs are drafts;
  follow the updated case specification rather than their outdated C1 labels.

## Non-Negotiables

- Internal fault data is not publishable. Do not move `data/` into tracked code.
- Do not call external LLM APIs for project experiments. The intended runtime is
  local vLLM on Ascend NPU servers.
- Runtime inference must not read `label.json`, root labels, or propagation-path
  labels. Training may use authorized training-fold labels; only the explicit
  Oracle evaluation wrapper may inject a confirmed test root. Propagation
  test labels remain evaluation-only.
- Every emitted device-device propagation edge must correspond to an edge in
  the case's raw `task_topo`.
- Physical adjacency, device-event ownership, timestamp order, and alarm
  semantics are circumstantial evidence, not deterministic causal edges.
- Event-event outputs are dependency/evolution hypotheses unless stronger
  causal labels are available.
- Unknown relations must be masked rather than treated as negative labels.
  `allowed` is neutral, not required. Audit `possible` with engineers rather
  than mechanically converting it into a positive, allowed, or negative edge.
- Without engineer propagation labels, validity checks must not be reported as
  root or path accuracy.
- Split and calibrate by incident group. No event, edge, or device instance from
  a held-out incident may leak into training or threshold selection.
- Incident groups must be verified; a case ID alone is not a verified group.
  Keep already-used development data distinct from new independent evaluation.
- Run tests with `python -m pytest`, not bare `pytest`, unless `PYTHONPATH` is
  already configured.

## Active Paper Modules

- **M1 / Stage 1 — Root hypotheses:** PC-STGR ranks devices using incident
  context, endpoint-relative topology, and device events; it passes Top-K
  hypotheses to reconstruction. Path conditioning is topology context, not
  an observed packet-level ECMP route.
- **M2 / part of Stage 2 — Local support:** P0 constructs root-independent
  support for `A->B / B->A / No Direct` on raw physical neighbors. This is
  normalized evidence support, not calibrated causal probability.
- **M3 / part of Stage 2 — Conditional reconstruction:** for each candidate
  root, select evidence-supported paths and merge them into a DAG. Current P0
  requires shortest-hop distance from the root to strictly increase along
  admitted directions. This is stronger than general root reachability and
  acyclicity; it can exclude valid annotated edges. It is a modeling restriction,
  not a propagation law or a guarantee of globally optimal recovery.
- **Final selection:** describe the actual frozen configuration for root/graph
  scoring. Measure root corrections and corruptions separately; do not assume
  graph reranking improves root accuracy or that a reliable abstention/fallback
  policy is implemented merely because a manuscript or figure proposes one.

Conceptual **Stage 1 = M1; Stage 2 = M2 + M3**. Historical `m1`/`m2` code
directories use a different numbering scheme and must not redefine the paper.

## Current Implementation Status

The active implementation is under `Sys/RootCauseAnalyze/`: `stage1/`,
`propagation/`, and `propagation_pipeline.py`. The heterogeneous V0 remains a
historical prototype.
P4 uses a grouped-OOF supervised three-state edge classifier with fold-local
probability calibration and conservative edge admission; it is an optimization
experiment, not the paper method.

Useful prototype paths:

- `Sys/RootCauseAnalyze/propagation/episodes.py`: event normalization.
- `Sys/RootCauseAnalyze/propagation/topology_context.py`: raw topology context.
- `Sys/RootCauseAnalyze/propagation/candidates.py`: device candidate subgraph.
- `Sys/RootCauseAnalyze/propagation/scorer.py` and
  `Sys/RootCauseAnalyze/propagation/m1/`: current device-edge support prototype.
- `Sys/RootCauseAnalyze/propagation/solver.py`: current constrained decoder.
- `Sys/RootCauseAnalyze/propagation_pipeline.py`: current compatibility entry.
- `Sys/RootCauseAnalyze/heterogeneous_propagation_pipeline.py`: root-input-free
  V0 heterogeneous entrypoint.
- `Sys/Score/evaluate_propagation.py`: graph validity and optional label metrics.

PC-STGR is active; IC-STGR and deterministic root rankers are baselines.

## Baselines and Validation State

Use the new `Baseline/common/` framework with `SkyNetVoting/`, `BiAnAdapt/`,
`NetEventCauseDevice/`, `PCMCIPlus/`, and `DYNOTEARS/`. Legacy `BiAn/`,
`NetEventCause/`, and `TraceRCA/` scripts are not interchangeable reproductions.
Retain the inspired/adapt/reimpl distinctions and original input requirements.
SkyNetVoting and BiAnAdapt support root ranking; NEC also supports graph/Full
tasks. PCMCI+ and DYNOTEARS support Oracle/Shared graphs only when inputs qualify,
not autonomous root ranking or Full inference.

The last recorded acceptance run (2026-09-10) passed 206 main tests and 22
labeler tests; synthetic NEC completed three folds and 6/6 predictions. These
are historical functional checks, not reproduced paper accuracy or new results.
BiAn's real local model backend was unavailable at that validation; probe it
before use. Time-series baselines require known collection coverage and
sufficient observations; preserve unknown bins and input-ineligible outcomes.

Save native graph, device projection, final adapter output, and deletion
reasons. Do not silently use P0 as an external baseline's adapter. A root-only
method combined with P0 must be named `X + P0`. Keep internal records/checkpoints
in ignored data/output locations; only synthetic fixtures and anonymized
validation summaries belong in tracked artifacts.

## Evaluation Contract and Remaining Work

The proposed `graph-eval-v2` protocol is **specified, not fully implemented**.
`Sys/Score/evaluate_propagation.py` still has legacy possible/allowed, uncertain
root, node-set, and exact-match semantics. `Baseline/common/evaluation.py` has
explicit masks and failure accounting but still needs integration and the
protocol's additional checks. Do not merge their scores into a fair comparison
or relabel old outputs as v2 until the evaluation paths are unified.

- Core graph metrics: case-macro directed-edge P/R/F1 with each metric's valid
  annotation denominator. Partial and complete annotations are separate tables.
- Keep explicit nodes, including an isolated root. Report node metrics and graph
  sizes; Exact-Graph/Joint-Exact require complete, reviewed graph annotations.
- Report raw-device and structural-equivalence results side by side, using one
  frozen, label-independent map. Projection is not causal Markov equivalence.
  A projected negative requires all corresponding raw possibilities to be
  confirmed negative; a negative plus unknown is still unknown.
  Root correctness uses raw device IDs; an equivalent graph does not excuse a
  wrong device root in the joint score.
- Distinguish a successful empty graph, a partial graph, abstention, execution
  failure, and missing labels. Keep failures in the applicable task denominator;
  an unannotated scope does not earn an empty-graph perfect score.
- Root: Top-K/MRR and actual candidate coverage. Oracle: confirmed root supplied
  only as an evaluation condition. Shared: the same frozen OOF predicted root.
  Full: own root plus graph, reporting root Top-1, Edge-F1, and Joint-Edge-F1.
- Candidate Oracle and Direct Oracle already appear in the 2026-09-08 records;
  the next task is consistent re-scoring, not claiming their first execution.
  Candidate Oracle remains limited by Top-K recall.
- Structural validity, evidence traceability, and coverage are diagnostics, not
  graph accuracy. SHD-1 and ancestor-reachability F1 are complete-label auxiliary
  metrics. SID does not match the current evidence-based explanation semantics.
- Freeze labels, inputs, folds, thresholds, adapters, and evaluator versions.
  Use paired incident-group bootstrap for method differences only with verified
  groups. Separate label/scoring corrections from algorithm improvements.

## Current Priority

1. Audit and freeze single-root scope, relation semantics, annotation completeness,
   and actual incident groups with engineer input; do not silently change labels.
2. Unify the main method and baselines under the same evaluation contract,
   including explicit nodes, masks, raw/equivalent projections, and failure counts.
3. Re-score frozen existing predictions and Oracle outputs; add the Shared
   predicted-root control and report root-ranking versus graph-selection effects.
4. Audit baseline input eligibility, verify the local BiAn backend, and run
   matched real-data comparisons after labels and evaluation are ready.
5. Obtain a reviewable real incident and service-to-endpoint dependency evidence;
   measure operator tasks before claiming operational or Web-service gains.

Only then choose targeted P4/decoder changes from observed error patterns.
Do not resume broad tuning, LLM reranking, or multi-root work by default.

## Figure Style

Use the figure specifications in
`docs/conferences/WWW2027/Introduction_提纲_讨论稿.md` and its linked case design.
Distinguish physical links, observations, operator actions, and inferred device
relations. Show the Stage-1-to-Stage-2 dependency and M1/M2/M3 grouping.

## Common Commands

Windows workspace; the existing CPU validation environment is
`tmp/baselines-venv`. Run commands from the repository root:

```powershell
& tmp/baselines-venv/Scripts/python.exe -m pytest tests -q
& tmp/baselines-venv/Scripts/python.exe -m pytest pingmesh-propagation-labeler/tests -q
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common --help
& tmp/baselines-venv/Scripts/python.exe Sys/Score/evaluate_propagation.py --help
```

Use the configured Linux/NPU environment for full experiments; shell scripts
are not native PowerShell commands. The existing entrypoint still runs P0/P4,
but its current scores retain the legacy evaluation limitations above.

```bash
source scripts/common.sh
bash scripts/run_full_experiment.sh --dry-run
```
