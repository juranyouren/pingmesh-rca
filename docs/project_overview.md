# Pingmesh RCA Project Overview

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
5. Bypass the LLM for high-trust cases, send ambiguous cases to a local LLM, or
   mark weak-signal cases for operator review.
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
| `tests/` | Unit tests for modularization, ranker determinism, trust gate, summarizer, and failure analysis. |
| `docs/papers/` | Paper text extractions and summaries. Original PDFs live outside the repo. |
| `tmp/` | One-off diagnostics, labeling helpers, and data repair scripts. Keep these out of the runtime path. |

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
trees. The active policy is `trust_tree_v1`:

- accept combined ranking when topo and temporal rankers are near agreement;
- accept temporal ranking when temporal evidence is strong and topo is not;
- defer topo-strong conflicts to the LLM because topo confidence can be diluted
  by topology shape and incomplete alarm semantics;
- route both-weak cases to operator review.

Main files:

- `Sys/RootCauseAnalyze/gate/decision.py`
- `Sys/RootCauseAnalyze/trust_trees/router.py`
- `Sys/Score/evaluate_trust_gate.py`
- `Sys/Score/apply_trust_gate.py`

### 5.2 Small-Model Candidate Summarization

`run_gate_pipe_experiments.sh` now contains experiment modes for candidate-node
summary before main LLM review, such as `pipe_summary_llm` and
`gate_pipe_summary_llm`. The goal is to reduce prompt size while preserving the
evidence needed for semantic arbitration.

Main files:

- `Sys/RootCauseAnalyze/gate/node_summarizer.py`
- `Sys/RootCauseAnalyze/SkilledAnalyzer.py`
- `scripts/run_gate_pipe_experiments.sh`

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
  --res "$PINGMESH_RESULTS/<run>/res.json" \
  --out-dir "$PINGMESH_RESULTS/<run>/gate_eval"

python Sys/Score/apply_trust_gate.py \
  --res "$PINGMESH_RESULTS/<run>/res.json" \
  --out "$PINGMESH_RESULTS/<run>/gate_pipe/res.json"
```

For the current combined experiment driver:

```bash
source scripts/common.sh
PINGMESH_EXPERIMENTS="pipe gate_eval gate_pipe" ./scripts/run_gate_pipe_experiments.sh
```

For thesis experiments, use the split wrappers documented in
`docs/实验脚本说明.md`:

```bash
source scripts/common.sh
./scripts/run_paper_01_skill_ablation.sh
./scripts/run_paper_02_gate_routing.sh
./scripts/run_paper_03_llm_arbitration.sh
```

## 8. Testing

Run the local unit suite with:

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
