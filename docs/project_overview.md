# Pingmesh RCA Project Overview

## 2026-08-18 Stage 1 Design Update

The next Stage 1 target design is **PC-STGR (Path-Conditioned
Spatio-Temporal Graph Ranker)**. It uses a Device-Event graph, direct endpoint
and path-corridor device features, fixed two-dimensional node-type one-hot
encoding, a 16-dimensional event-name embedding, a 42-to-64-dimensional node
encoder, two relation-aware attention layers, and a single-root case-wise
softmax loss. The complete decision record and target tensor specification are
in [`docs/PC-STGR设计方案.md`](./PC-STGR设计方案.md).

The `stage1/neural_*` implementation has now migrated to this PC-STGR design.
This is still not a relabeling of existing results: the documented 159-case OOF
scores and old checkpoints remain IC-STGR artifacts until PC-STGR completes an
independent grouped OOF evaluation. Do not report the existing IC-STGR metrics
as PC-STGR results.

## Active Paper Branch

`2stage` is the primary working branch for the current paper proposal, method
implementation, and experiment workflow. Unless a task explicitly specifies
another target, paper-related development, experiment results, and documentation
must use `2stage` as the source of truth and should be committed to this branch.
Other branches are not the default basis for the current paper.

## 1. Project Positioning

This project studies automated root-cause localization for large-scale data
center network incidents triggered by Pingmesh alarms. The working assumption is
that Pingmesh reliably detects network-side symptoms, but cannot identify the
physical root-cause device because ECMP and high fan-out DCN topologies obscure
the actual forwarding path.

The target paper system is a two-stage pipeline:

1. Parse one incident case from full-link node data and `info.json`.
2. Stage 1 uses **PC-STGR (Path-Conditioned Spatio-Temporal Graph Ranker)** to
   construct a path-conditioned Device-Event graph and learn a high-recall
   root-cause candidate ranking.
3. Stage 2/M1 builds one root-independent hypothesis propagation graph.
4. Stage 2/M2 evaluates every Stage 1 candidate against that shared graph and
   emits the final ranking plus root-conditioned propagation graphs.
5. Evaluate Stage 1 with grouped out-of-fold Top-1/Top-3/Top-5 and MRR; evaluate
   Stage 2 validity or path accuracy separately according to label availability.

The executable neural pipeline now implements PC-STGR. Its independent grouped
OOF evaluation is still pending, so the existing IC-STGR metrics remain only a
historical neural reference. The deterministic topology + temporal fusion
remains a strong white-box Stage 1 baseline. Deprecated orchestration and review
paths are not part of the executable pipeline.

## 2. Current Constraints

- The production dataset is internal Huawei Cloud fault data and cannot be
  published.
- Experiments are designed for an internal/offline environment. External LLM API
  calls should not be part of the experiment path.
- The intended LLM runtime is local vLLM with DeepSeek-R1-Distill-Qwen-32B on
  Ascend NPU servers.
- Server defaults are centralized in `scripts/common.sh`; Python config reads
  equivalent environment variables through `Sys/config.py`.
- Use `python -m pytest`, because bare `pytest` may not include the repository
  root on `sys.path` in this Windows workspace.

## 3. Active Repository Structure

| Path | Role |
| --- | --- |
| `Sys/config.py` | Central Python config derived from environment variables. |
| `Sys/Preprocess/Preprocessor.py` | RAW merge, validation, and NODE data extraction. |
| `Sys/RootCauseAnalyze/stage1/neural_graph.py` | PC-STGR path-conditioned Device-Event graph construction. |
| `Sys/RootCauseAnalyze/stage1/neural_model.py` | PC-STGR 42-to-64 encoder, relation-aware graph layers, root head, and single-root loss. |
| `Sys/RootCauseAnalyze/stage1/neural_pipeline.py` | Grouped OOF training and label-free PC-STGR inference. |
| `Sys/RootCauseAnalyze/stage1/pipeline.py` | Deterministic temporal + alarm-topology Stage 1 baseline. |
| `Sys/Score/` | Stage 1, Stage 2, propagation, and baseline evaluation scripts. |
| `Sys/utils/` | Shared case, alarm, ranking, and I/O utilities. |
| `prompts/` | Prompt templates retained for baseline and ablation experiments. |
| `Baseline/` | Adapted TraceRCA, NetEventCause, and BiAn baselines. |
| `scripts/` | Supported server-side experiment entrypoints and shared configuration; see `scripts/README.md`. |
| `tests/` | Local-only ignored regression tests; they are retained in this workspace but not shipped by Git. |
| `docs/PC-STGR设计方案.md` | Target PC-STGR decisions, feature schema, tensor dimensions, network structure, loss, and migration checklist. |
| `docs/papers/` | Paper text extractions and summaries. Original PDFs live outside the repo. |
| `tmp/` | Ignored generated outputs only; reusable diagnostics belong under `Sys/` and historical tools under `archive/`. |

## 4. Current Performance Snapshot

The latest documented production-data setting uses 159 manually labeled cases.
Learned Stage 1 results must use grouped 5-fold out-of-fold predictions.

| Stage 1 method | Evaluation | Cases | Top-1 | Top-3 | Top-5 | Paper role |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| deterministic topology + temporal fusion | deterministic | 159 | **77.36%** | 89.94% | 94.34% | strong white-box baseline |
| **IC-STGR** | grouped 5-fold OOF | 159 | 73.58% | **93.71%** | **97.48%** | implemented historical neural reference |

The supported claim is improved candidate coverage, not improved Top-1. IC-STGR
changes Top-1 by -3.78 percentage points, Top-3 by +3.77 points, and Top-5 by
+3.14 points versus the deterministic baseline. Top-5 misses fall from 9 to 4
cases (55.6% fewer misses). Its full-data `final_model.pt` is for later unseen
inference and must not be scored back on these 159 labeled cases as a paper result.

### 4.1 Stage 1 Target Decision

PC-STGR is the fixed Stage 1 implementation. IC-STGR remains a historical neural
reference and its existing metrics remain valid only under that name. The
comparison plan is:

| Method | Role | Status |
| --- | --- | --- |
| PC-STGR | main method; path-conditioned Device-Event spatio-temporal ranking | implementation complete; grouped OOF pending |
| IC-STGR | historical reference; Device-Event-Incident ranking | first OOF result complete |
| deterministic topology + temporal fusion | strong interpretable baseline | complete |
| LambdaMART | learned ranking baseline over researcher-defined, automatically computed device features | pending |
| device-only GAT/GCN | graph-structure baseline | pending |
| PC-STGR path/type/event/time removals | required component ablations | pending |

PC-STGR is a project method name, not the name of an existing paper. The paper
claim is scoped to the Pingmesh path-conditioned Device-Event construction,
explicit spatio-temporal relations, and case-wise single-root ranking, not to a
new general attention operator. See `docs/PC-STGR设计方案.md` for the exact
feature, tensor, loss, and evaluation contract.

## 5. Supporting Directions

### 5.1 Alarm Weight And Semantic Coverage

Alarm weights are maintained manually in `data/weights/classified_alarms/all_alarms.json`.
Earlier experiments with LLM-based alarm scoring and classification showed that semantic
classification can help temporal-only ranking, but can hurt fused ranking when coverage
is partial. The next useful work is broader alarm-name normalization and coverage
analysis before applying semantic weights globally.

Main files:

- `Sys/utils/alarm_utils.py`
- `data/weights/classified_alarms/all_alarms.json`

### 5.2 Public Dataset / NIKA Direction

The `main` branch is for internal company datasets. The `nika` branch is the
intended public-dataset adaptation path. Work for public release should avoid
Huawei-internal raw data and should replace private labels and alarm names with
publishable equivalents.

### 5.3 Fault Propagation Path Reconstruction

The `2stage` branch is the primary working branch for the current paper. It
contains the PC-STGR implementation and the Stage 2 joint-inference
implementation. Stage 2 consumes the stable `initial_root_rankings` contract
and remains compatible with PC-STGR output.

Supported result writers use one neutral ranking schema:

- `ranked_ips`: ordered device IPs for direct Top-K evaluation;
- `ranking_details`: method-specific ranking evidence and diagnostics;
- `stage1.root_rankings` and `initial_root_rankings`: canonical scored candidate
  records passed from Stage 1 to Stage 2;
- `final_root_rankings`: Stage 2 reranked candidates when Stage 2 is present.

`Sys/Score/Score_N.py` evaluates one canonical root device per case and reports
the result as `ranking_evaluation`; parsed response payloads are reported
separately as `response_evaluation`. The retired
`skill_ips`, `skill_details`, and `skill_evaluation` names are not supported.

Stage 2 first builds a root-independent weighted relation graph over
the incident-conditioned undirected topology, retaining inactive, forward,
reverse, ambiguous, and common-cause states. This single graph is the M1 output
and does not depend on root candidates or their scores. M2 then evaluates each
Stage 1 Top-K root against the same hypothesis graph, constructs its corresponding
device-level propagation graph, and produces one explanation score. The final
ranking is a weighted sum of only the normalized Stage 1 score and the
normalized Stage 2 explanation score; insufficient path evidence falls back to
the Stage 1 order.
Interface fields are optional and their absence is not a quality penalty.
Cases supported only by topology are marked `unidentifiable`; M2 then falls
back to the Stage 1 order and emits an empty selected propagation graph.

Engineer annotation of a path-labeling subset remains the next stage because
the current labels identify root-cause devices but do not contain ordered nodes
or directed propagation edges. Evaluation metrics remain configurable; strict
matching, component scores, and a fully specified tolerant/rounded case-level
accuracy are supported. Before path labels exist, topology validity, temporal
consistency, and evidence grounding are validity checks rather than causal-path
accuracy.

Main files:

- `Sys/RootCauseAnalyze/propagation/`
- `Sys/RootCauseAnalyze/propagation_pipeline.py`
- `Sys/Score/evaluate_propagation.py`
- `Sys/Preprocess/Preprocessor.py` (`topology_context.json` sidecar)

Design source:

- `docs/论文方案.md`

## 6. Deprecated Or Removed Areas

- The Gate, Trust-Tree, Skill Pipeline, `skills/` compatibility package,
  `SkilledAnalyzer.py`, and candidate-summary path were removed. Active
  deterministic Stage 1 implementations live only in
  `Sys/RootCauseAnalyze/stage1/`.
- `SkillNRefineAnalyzer.py`, `RootCauseAnalyzer.py`, and old confidence/
  credence calibration scripts are removed. Any remaining `.pyc` files from
  those modules are stale generated artifacts and must not be restored.
- `docs/毕业论文/` was obsolete and removed.
- Original paper PDFs were moved to `../pingmeshPaper_papers_pdf/`; keep only
  text extracts and summaries in `docs/papers/`.

## 7. Experiment Commands

Use these from the repository root on the server. The executable neural
workflow is PC-STGR:

```bash
source scripts/common.sh
bash scripts/run_paper_05_pc_stgr.sh
```

It produces deterministic-baseline, PC-STGR OOF, and PC-STGR-plus-Stage-2 rows
under `pc_stgr_oof` and `pc_stgr_stage2`. These rows receive paper metrics only
after a new grouped OOF run; historical IC-STGR rows and checkpoints remain
separate.

The deterministic baseline and Stage 2 can also be run directly:

```bash
python Sys/RootCauseAnalyze/stage1/pipeline.py \
  --data-root "$PINGMESH_DATA" \
  --output-dir deterministic_manual \
  --rankers topology temporal \
  --top-k "$PINGMESH_TOP_K" \
  --weight-file "$PINGMESH_WEIGHTS_MANUAL"

python Sys/RootCauseAnalyze/propagation_pipeline.py \
  --data-root "$PINGMESH_DATA" \
  --root-results "$PINGMESH_RESULTS/<paper_05_run>/pc_stgr_oof/res.json" \
  --output-dir "$PINGMESH_RESULTS/<run>/propagation"

python Sys/Score/evaluate_propagation.py \
  --predictions "$PINGMESH_RESULTS/<run>/propagation/res.json" \
  --selected-paths "$PINGMESH_RESULTS/<run>/propagation/selected_propagation_paths.json" \
  --out "$PINGMESH_RESULTS/<run>/propagation/validity.json"
```

Stage 2 keeps `res.json` compact and writes each selected graph to the sibling
`selected_propagation_paths.json`. That file follows the JSON-array prediction
contract of `pingmesh-propagation-labeler`; `res.json` links records to it with
`selected_path_ref`. The evaluator also resolves these references automatically.
Every emitted propagation edge must match an edge ID in the case's raw
`task_topo` context. If that raw topology sidecar is unavailable, Stage 2 emits
no propagation edges and preserves the Stage 1 ranking.

Use `scripts/run_stage2_edge_probability_ablation.sh` for the P0/P1/P4 Stage 2
comparison and `scripts/run_baselines.sh` for TraceRCA, NetEventCause, and BiAn.
The removed Gate/Trust-Tree/Skill/LLM orchestration paths have no supported
runtime entrypoints.

## 8. Testing

The root `tests/` directory is intentionally ignored. In a workspace that keeps
the local test bundle, run:

```bash
python -m pytest -q
```

Current module-level coverage includes:

- no active Stage 1 dependency on the removed Skill/Gate/Trust-Tree paths;
- deterministic ranker tie behavior and ranking details;
- topology-context preservation, alarm episode normalization, propagation DAG
  reconstruction, abstention, and propagation evaluation;
- neural Stage 1 graph/model contracts and Stage 2 joint inference.

Obsolete tests for removed script wrappers, including the old propagation
labeler, are not part of the maintained test bundle.

## 9. Maintenance Rules

- Keep generated files out of Git: `__pycache__/`, `.pytest_cache/`, local JSON
  outputs, and large binary paper PDFs.
- Keep source-of-truth docs small:
  - `AGENT.md` is the concise agent entrypoint.
  - `docs/project_overview.md` is the detailed project state document.
- Prefer adding small utilities under `Sys/utils/` instead of duplicating JSON,
  case-loading, or ranking helpers in new scripts. Do not restore the removed
  root-level `utils/` package.
- If a script needs labels, keep it clearly in the evaluation or diagnostic
  path. Runtime inference must not read labels.
- Update `scripts/common.sh` first when changing default server paths, then let
  Python config consume the environment.
