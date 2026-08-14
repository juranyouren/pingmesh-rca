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

The current system combines deterministic ranking and local LLM review:

1. Parse one incident case from full-link node data and `info.json`.
2. Run two deterministic rankers:
   - topo ranker: directed PageRank over physical topology with alarm weights,
     source/sink proximity, and cross-path evidence.
   - temporal ranker: burst, early-bird, and temporal-density scoring around
     the fault reference time.
3. Fuse ranker outputs into a compact candidate evidence table.
4. Route the case through a trust-tree gate.
5. Bypass the LLM only when the selected policy produces a complete safety
   certificate; otherwise fail closed to the local LLM.
6. Evaluate with `Score_N` Top-1/Top-3/Top-5 metrics.

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
| `Sys/RootCauseAnalyze/skill_pipeline.py` | Deterministic topo+temporal evaluation path. |
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

| Method | Top-1 | Top-3 | Top-5 |
| --- | ---: | ---: | ---: |
| topo+temporal, manual alarm weights | 76.10% | 85.53% | 91.19% |
| topo+temporal, LLM-learned weights | 66.67% | 88.05% | 93.71% |
| temporal only, manual weights | 62.89% | 88.05% | 94.34% |
| topo only, manual weights | 50.31% | 74.21% | 84.28% |

For the LLM review path based on manual-weight fused evidence:

| Layer | Top-1 | Top-3 | Top-5 |
| --- | ---: | ---: | ---: |
| pure skill evaluation | 76.10% | 84.91% | 91.19% |
| LLM reranking evaluation | 75.47% | 86.79% | 86.79% |

Interpretation: the deterministic fused rankers are already strong. The LLM
should act as a reviewer for close or semantically rich cases, not as an
unconstrained reranker.

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

This is a confirmed research task, not yet an implemented capability. Its target
is an evidence-grounded device-level propagation DAG with ranked chains and
alarm-event provenance. Engineer annotation of a path-labeling subset is in
scope because the current labels identify root-cause devices but do not contain
ordered nodes or directed propagation edges. Evaluation metrics will remain
configurable during the labeling pilot; both strict matching and a fully
specified tolerant/rounded case-level path accuracy are candidates. Before path
labels exist, topology validity, temporal consistency, and evidence grounding
must be reported as validity checks rather than causal-path accuracy.

Research memo:

- `docs/故障传播路径还原调研.md`
- `docs/故障传播路径标注规范_v0.md`
- `docs/故障传播路径重构方案_v0.md`

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

python Sys/RootCauseAnalyze/skill_pipeline.py \
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
```

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
