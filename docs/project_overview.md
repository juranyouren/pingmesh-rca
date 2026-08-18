# Pingmesh RCA Project Overview

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

The current paper system is a two-stage pipeline:

1. Parse one incident case from full-link node data and `info.json`.
2. Stage 1 uses **IC-STGR (Incident-Conditioned Spatio-Temporal Graph Ranker)**
   to construct a Device-Event-Incident heterogeneous graph and learn a
   high-recall root-cause candidate ranking.
3. Stage 2/M1 builds one root-independent hypothesis propagation graph.
4. Stage 2/M2 evaluates every Stage 1 candidate against that shared graph and
   emits the final ranking plus root-conditioned propagation graphs.
5. Evaluate Stage 1 with grouped out-of-fold Top-1/Top-3/Top-5 and MRR; evaluate
   Stage 2 validity or path accuracy separately according to label availability.

The deterministic topology + temporal fusion remains a strong white-box Stage 1
baseline. Trust-tree and local-LLM review code is retained for historical and
comparison experiments, but it is not the selected Stage 1 method in the current
paper proposal.

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
| `Sys/RootCauseAnalyze/stage1/neural_graph.py` | IC-STGR Device-Event-Incident graph construction. |
| `Sys/RootCauseAnalyze/stage1/neural_model.py` | Relation-aware graph encoder, root-ranking head, and training loss. |
| `Sys/RootCauseAnalyze/stage1/neural_pipeline.py` | Grouped OOF training and label-free IC-STGR inference. |
| `Sys/RootCauseAnalyze/stage1/pipeline.py` | Deterministic temporal + alarm-topology Stage 1 baseline. |
| `Sys/RootCauseAnalyze/skills/` | Built-in skill implementation replacing the old SkillBank runtime. |
| `Sys/RootCauseAnalyze/gate/` | Evidence construction, node summarization, routing response, and trust gate integration. |
| `Sys/RootCauseAnalyze/trust_trees/` | Auditable rule trees for topo and temporal ranker trust. |
| `Sys/RootCauseAnalyze/SkilledAnalyzer.py` | LLM inference path, gate support, and optional candidate-node summarization. |
| `Sys/Score/` | Scoring, gate evaluation, gate application, and failure analysis scripts. |
| `Sys/utils/` | Shared case, alarm, ranking, and I/O utilities. |
| `prompts/` | Active LLM prompt templates used by `SkilledAnalyzer`. |
| `Baseline/` | Adapted TraceRCA, NetEventCause, and BiAn baselines. |
| `scripts/` | Server-side experiment entrypoints; `run_paper_*.sh` are thesis experiment wrappers. |
| `tests/` | Local-only ignored regression tests; they are retained in this workspace but not shipped by Git. |
| `docs/papers/` | Paper text extractions and summaries. Original PDFs live outside the repo. |
| `tmp/` | Ignored generated outputs only; reusable diagnostics belong under `Sys/` and historical tools under `archive/`. |

## 4. Current Performance Snapshot

The latest documented production-data setting uses 159 manually labeled cases.
Learned Stage 1 results must use grouped 5-fold out-of-fold predictions.

| Stage 1 method | Evaluation | Cases | Top-1 | Top-3 | Top-5 | Paper role |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| deterministic topology + temporal fusion | deterministic | 159 | **77.36%** | 89.94% | 94.34% | strong white-box baseline |
| **IC-STGR** | grouped 5-fold OOF | 159 | 73.58% | **93.71%** | **97.48%** | **selected main method** |

The supported claim is improved candidate coverage, not improved Top-1. IC-STGR
changes Top-1 by -3.78 percentage points, Top-3 by +3.77 points, and Top-5 by
+3.14 points versus the deterministic baseline. Top-5 misses fall from 9 to 4
cases (55.6% fewer misses). Its full-data `final_model.pt` is for later unseen
inference and must not be scored back on these 159 labeled cases as a paper result.

### 4.1 Fixed Stage 1 Method Decision

IC-STGR is the fixed Stage 1 technology for the current paper. Future Stage 1
work should optimize this model rather than reopen the main-method selection.
The comparison plan is:

| Method | Role | Status |
| --- | --- | --- |
| IC-STGR | main method; incident-conditioned heterogeneous spatio-temporal ranking | first OOF result complete |
| deterministic topology + temporal fusion | strong interpretable baseline | complete |
| LambdaMART | learned ranking baseline over researcher-defined, automatically computed device features | pending |
| device-only GAT/GCN | graph-structure baseline | pending |
| IC-STGR relation/node/loss removals | component ablations and optimization | pending |

IC-STGR is a project method name, not the name of an existing paper. It adapts
relation-aware heterogeneous graph attention and learning-to-rank ideas to the
Pingmesh Device-Event-Incident formulation. The paper should claim novelty in
the incident-conditioned graph construction, explicit spatio-temporal relations,
and multi-positive root-ranking adaptation, not in inventing a new general
attention operator.

## 5. Active Exploration Directions

### 5.1 Trust-Tree Gate

The old continuous confidence direction was replaced by auditable logical trust
trees. The active router is `configurable_gate_v1`:

- search named and parameterized strict/balanced policies after deterministic
  results have been generated;
- reject any policy with an unsafe bypass, a known-badcase bypass, or error
  recall below the configured target globally or in a deterministic fold;
- choose the passing policy with the highest bypass coverage;
- emit only the combined Top-1 on bypass and fall back to `always_llm` when no
  useful policy is safe.

Main files:

- `Sys/RootCauseAnalyze/gate/decision.py`
- `Sys/RootCauseAnalyze/trust_trees/router.py`
- `Sys/Score/evaluate_trust_gate.py`
- `Sys/Score/evaluate_gate_recall.py`
- `Sys/Score/search_gate_policy.py`
- `Sys/Score/apply_trust_gate.py`

### 5.2 SECL Evidence Organization And Device-State Summarization

The evidence sent to the main LLM is organized from the union of the topology
Top-K and temporal Top-K device rankings, rather than only the fused Top-K.
This preserves candidates supported strongly by either independent view. The
fused ranking remains the deterministic evaluation baseline and is not replaced
by the union.

The optional small model only compresses the observable state of each device.
Its prompt explicitly forbids root-cause, symptom, causality, ranking,
confidence, or remediation judgments. Root-cause comparison is reserved for
the main LLM after it receives both rankings and all device-state summaries.
Summary caches are versioned by the evidence-organization strategy and Top-K
value so stale fused-only caches are not reused.

Main files:

- `Sys/RootCauseAnalyze/gate/node_summarizer.py`
- `Sys/RootCauseAnalyze/SkilledAnalyzer.py`
- `scripts/run_rca_experiments.sh`

### 5.3 Alarm Weight And Semantic Coverage

Alarm weights are maintained manually in `data/weights/classified_alarms/all_alarms.json`.
Earlier experiments with LLM-based alarm scoring and classification showed that semantic
classification can help temporal-only ranking, but can hurt fused ranking when coverage
is partial. The next useful work is broader alarm-name normalization and coverage
analysis before applying semantic weights globally.

Main files:

- `Sys/utils/alarm_utils.py`
- `data/weights/classified_alarms/all_alarms.json`

### 5.4 Failure Analysis And Gate Design

Failure analysis now focuses on understanding when the skill pipeline fails:
flat rankings, missing time data, weak alarm coverage, topology dilution, and
ranker disagreement. These outputs should feed trust-tree rules and data repair
work rather than prompt-only tuning.

Main files:

- `Sys/Score/analyze_skillpipe_failures.py`
- `Sys/Score/evaluate_gate_selection.py`
- `Sys/Score/evaluate_trust_gate.py`
- `archive/tmp_tools/diagnose_pipeline.py` (archived diagnostic helper)

### 5.5 Public Dataset / NIKA Direction

The `main` branch is for internal company datasets. The `nika` branch is the
intended public-dataset adaptation path. Work for public release should avoid
Huawei-internal raw data and should replace private labels and alarm names with
publishable equivalents.

### 5.6 Prompt Stability

Prompt design is deliberately conservative. The current prompt tells the LLM to
trust the algorithm ranking by default and only adjust when candidate alarms
provide explicit contrary evidence. This guards against the model "doing work"
by unnecessarily changing a strong deterministic ranking.

Main file:

- `prompts/rca.py`
- `prompts/skilled.py`

### 5.7 Fault Propagation Path Reconstruction

The `2stage` branch is the primary working branch for the current paper and
contains the IC-STGR Stage 1 plus the Stage 2 joint-inference implementation.
Stage 2 first builds a root-independent weighted relation graph over
the incident-conditioned undirected topology, retaining inactive, forward,
reverse, ambiguous, and common-cause states. This single graph is the M1 output
and does not depend on root candidates or their scores. M2 then evaluates each
Stage 1 Top-K root against the same hypothesis graph, constructs its corresponding
device-level propagation graph, and produces one explanation score. The final
ranking is a weighted sum of only the normalized IC-STGR Stage 1 score and the
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

Research memo:

- `docs/故障传播路径还原调研.md`
- `docs/故障传播路径标注规范_v0.md`
- `docs/故障传播路径重构方案_v0.md`
- `docs/故障传播路径联合推断方案_v1.md`

## 6. Deprecated Or Removed Areas

- `SkillBank` is no longer part of the runtime path. The active replacement is
  `Sys/RootCauseAnalyze/skills/`.
- `SkillNRefineAnalyzer.py`, `RootCauseAnalyzer.py`, and old confidence/
  credence calibration scripts are removed. Any remaining `.pyc` files from
  those modules are stale generated artifacts and must not be restored.
- `docs/毕业论文/` was obsolete and removed.
- Original paper PDFs were moved to `../pingmeshPaper_papers_pdf/`; keep only
  text extracts and summaries in `docs/papers/`.

## 7. Experiment Commands

Use these from the repository root on the server:

```bash
source scripts/common.sh

python Sys/RootCauseAnalyze/stage1/pipeline.py \
  --data-root "$PINGMESH_DATA" \
  --output-dir skillpipe_manual \
  --skills 1 2 \
  --top-k "$PINGMESH_TOP_K" \
  --weight-file "$PINGMESH_WEIGHTS_MANUAL"

python Sys/Score/evaluate_trust_gate.py \
  --res "$PINGMESH_RESULTS/<run>/pipe/res.json" \
  --out-dir "$PINGMESH_RESULTS/<run>/gate_eval" \
  --policy-config "$PINGMESH_RESULTS/<run>/gate_search/selected_gate_policy.json"

python Sys/Score/apply_trust_gate.py \
  --res "$PINGMESH_RESULTS/<run>/pipe/res.json" \
  --out "$PINGMESH_RESULTS/<run>/gate_selected/res.json" \
  --policy-config "$PINGMESH_RESULTS/<run>/gate_search/selected_gate_policy.json"

python Sys/RootCauseAnalyze/propagation_pipeline.py \
  --data-root "$PINGMESH_DATA" \
  --root-results "$PINGMESH_RESULTS/<run>/pipe/res.json" \
  --output-dir "$PINGMESH_RESULTS/<run>/propagation"

python Sys/Score/evaluate_propagation.py \
  --predictions "$PINGMESH_RESULTS/<run>/propagation/res.json" \
  --out "$PINGMESH_RESULTS/<run>/propagation/validity.json"
```

For the current combined experiment driver:

```bash
source scripts/common.sh
PINGMESH_EXPERIMENTS="pipe gate_auto" ./scripts/run_rca_experiments.sh
```

`gate_auto` always runs in this order: deterministic `pipe/res.json`, policy
search, selected-policy application, and recall assertion. Its main outputs are
`gate_search/selected_gate_policy.json`, `gate_selected/res.json`, and
`gate_recall/gate_recall_summary.json`.

For thesis experiments, use the split wrappers documented in
`docs/实验脚本说明.md`:

```bash
source scripts/common.sh
./scripts/run_paper_01_skill_ablation.sh
./scripts/run_paper_02_gate_routing.sh
./scripts/run_paper_03_llm_arbitration.sh
./scripts/run_paper_04_summary_ablation.sh
./scripts/run_paper_05_spatiotemporal_graph.sh
```

`run_paper_05_spatiotemporal_graph.sh` is the primary Stage 1 paper experiment.
It produces deterministic-baseline, IC-STGR OOF, and IC-STGR-plus-Stage-2 rows;
the Stage 1 paper score is the `neural_oof` row.

## 8. Testing

The root `tests/` directory is intentionally ignored. In a workspace that keeps
the local test bundle, run:

```bash
python -m pytest -q
```

The current suite covers:

- no runtime dependency on old SkillBank inside `Sys`;
- deterministic ranker tie behavior and trust-tree details;
- trust-tree router decisions and Score_N-compatible bypass responses;
- applying the trust gate to offline skillpipe records;
- topology-context preservation, alarm episode normalization, propagation DAG
  reconstruction, abstention, and propagation evaluation;
- candidate-node summarization prompt replacement;
- skill-pipeline failure analysis outputs.

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
