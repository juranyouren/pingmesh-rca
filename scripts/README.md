# Experiment Scripts

> The active paper system is a two-stage pipeline: PC-STGR first ranks root
> candidates, then P0 reconstructs a root-conditioned propagation DAG. P0 is the
> approved primary method. P4 is a supervised optimization track; P1 is retired
> from the active experiment matrix.

## Full root + propagation experiment

Run preprocessing, grouped-OOF root training, P0 reconstruction, grouped-OOF
P4 optimization, and unified evaluation with one command:

```bash
bash scripts/run_full_experiment.sh
```

The run ID is generated automatically as
`full_<variant>_<YYYYMMDD_HHMMSS>_<git-short-sha>`. If that directory already
exists, `_01`, `_02`, and so on are appended. The latest run pointer is written
to `$PINGMESH_RESULTS/latest_full_run.json`.

Useful variants:

```bash
# Fold-local self-supervised pretraining before root fine-tuning
bash scripts/run_full_experiment.sh --root-variant self_supervised

# Also report metrics without structural-equivalence node aggregation
bash scripts/run_full_experiment.sh --with-raw-node-metrics

# Check paths, arguments, and resolved commands without training
bash scripts/run_full_experiment.sh --dry-run

# Continue a partially completed run; completed stages are skipped
bash scripts/run_full_experiment.sh --resume "$PINGMESH_RESULTS/<full-run-dir>"
```

The main output is `summary.json`. Its `root_location` section contains Stage-1
OOF and post-reconstruction root metrics; `graph_rebuild` contains directed-edge,
node, exact-match, and validity metrics for P0 and P4. `summary.csv` places both
metric groups in one table. The primary predicted graph is stored at
`propagation/p0/selected_propagation_paths.json`; P4 optimization artifacts are
stored under `propagation/p4/`. Each stage has a log and a completion marker, so
a failed run can resume without retraining completed stages.

For direct reading, `summary.md` renders the same Root Location and Graph Rebuild
metrics as one Markdown table.

## Runnable heterogeneous V0

The V0 builds a typed Device/Event/Symptom graph, produces interpretable root and
DD/EE relation potentials, enumerates single-device roots, decodes a
topology-valid device DAG, and attaches event/evidence explanations. It is a
baseline scaffold; Relation-aware GAT, calibrated learned heads, CP-SAT, link
roots, and multi-root reconstruction are not implemented yet.

Run one case:

```bash
python Sys/RootCauseAnalyze/heterogeneous_propagation_pipeline.py \
  --case-dir /path/to/case \
  --output-dir "$PINGMESH_RESULTS/heterogeneous_v0"
```

Run all discoverable cases:

```bash
bash scripts/run_heterogeneous_v0.sh
```

The command never reads `label.json` or a root-result file. It writes compact
case summaries to `res.json` and full graphs to `heterogeneous_graphs.json`.
The wrapper first backfills and verifies raw topology contexts. Set
`PINGMESH_HETERO_BACKFILL_TOPOLOGY=0` only when the sidecars have already been
verified. Run IDs are generated automatically; `--workdir` is reserved for a
parent workflow that needs to control the output directory.

`scripts/common.sh` is the single source of server paths, model settings, NPU
cards, and default Top-K values. Override it with environment variables instead
of editing individual runners.

Set `PINGMESH_RAW_DATA` to the directory containing the original full-link JSON
files whose `full_link.task_topo.value` corresponds to `PINGMESH_DATA` cases.

## Supported experiment entrypoints

| Script | Purpose |
| --- | --- |
| `run_full_experiment.sh` | Primary entrypoint: root OOF, P0 paper system, optimized P4 comparison, and unified root/graph metrics. |
| `run_heterogeneous_v0.sh` | Historical root-input-free heterogeneous V0 prototype. |
| `run_root_oof.sh` | Deterministic root baseline plus supervised or self-supervised PC-STGR grouped OOF training. |
| `run_dd_edge_ablation.sh` | Compare the P0 paper method with leakage-safe P4 supervised optimization. |
| `run_rca_baselines.sh` | TraceRCA, NetEventCause, and BiAn Pipeline 1 baselines. |
| `../Sys/RootCauseAnalyze/stage1/pipeline.py` | Deterministic topology + temporal Stage 1 baseline. |
| `../Sys/RootCauseAnalyze/stage1/neural_pipeline.py` | Current PC-STGR OOF training and label-free inference implementation. |
| `../Sys/RootCauseAnalyze/stage1/neural_ssl_pipeline.py` | Optional fold-local self-supervised pretraining, supervised fine-tuning, OOF evaluation, and label-free inference. |
| `../Sys/Preprocess/backfill_topology_context.py` | Backfill and verify per-case topology contexts from raw `task_topo`. |
| `../Sys/RootCauseAnalyze/propagation_pipeline.py` | Current device-level, label-free propagation prototype with compatibility root-candidate input. |
| `../Sys/Score/evaluate_propagation.py` | Propagation validity and optional path-label evaluation. |

The Gate, Trust-Tree, Skill Pipeline, candidate-summary path, and their old
paper-01 through paper-04 wrappers have been removed. They are not part of the
runtime or supported comparison workflow.

## Stage 1 root-location model

PC-STGR is the first stage of the active paper system. Its implementation
contract is recorded in `docs/PC-STGR设计方案.md`; the complete paper plan is
`docs/论文方案.md`. The current `stage1/neural_*` code and `run_root_oof.sh`
implement PC-STGR. A new
grouped OOF run is still required for any candidate-quality claim; do not rename
the historical IC-STGR 73.58/93.71/97.48 Top-1/Top-3/Top-5 result as PC-STGR or
as a propagation-graph result.

Run the root-candidate workflow in the server PyTorch environment:

```bash
bash scripts/run_root_oof.sh
```

The default remains the original supervised PC-STGR. Select the optional
self-supervised-pretrained variant with either form:

```bash
bash scripts/run_root_oof.sh --variant self_supervised

# Equivalent environment-variable form
PINGMESH_NEURAL_VARIANT=self_supervised \
  bash scripts/run_root_oof.sh
```

PC-STGR-SSL pretrains only on the current fold's training cases reloaded without
labels, then fine-tunes on their root labels. Validation-fold cases are excluded
from the vocabulary and pretraining data.

It produces two root-ranking rows:

- `deterministic`: topology + temporal white-box baseline;
- `pc_stgr_oof`: grouped OOF PC-STGR predictions.

The run directory contains `summary.json`, `summary.csv`, fold checkpoints,
training histories, OOF `res.json`, and
`pc_stgr_oof/final_model.pt`. Candidate-ranking scores must use
`pc_stgr_oof/res.json`; the final model is trained on all labeled cases only for
later unseen-case inference. Use `run_full_experiment.sh` to feed those OOF
predictions into propagation reconstruction and joint reporting.

When `self_supervised` is selected, the corresponding directories are
`pc_stgr_ssl_oof`, and the checkpoint is stored as
`pc_stgr_ssl_oof/final_model.pt`. Self-supervised hyperparameters are configured
through the `PINGMESH_NEURAL_PRETRAIN_*` variables in `scripts/common.sh`.

The deterministic baseline can also be run directly:

```bash
source scripts/common.sh
python Sys/RootCauseAnalyze/stage1/pipeline.py \
  --data-root "$PINGMESH_DATA" \
  --output-dir deterministic_manual \
  --rankers topology temporal \
  --top-k "$PINGMESH_TOP_K" \
  --weight-file "$PINGMESH_WEIGHTS_MANUAL"
```

Stage 1 code uses the `stage1/` package, `rank_root_causes`,
`run_stage1_pipeline`, and `--rankers`. The former `skill_pipeline.py` and
`skills/` package no longer exist.

All supported result writers expose `ranked_ips`; Stage 1 also emits
`ranking_details`, `stage1.root_rankings`, and `initial_root_rankings`. Stage 2
adds `final_root_rankings`. `Score_N.py` stores direct ranking metrics under
`ranking_evaluation` and parsed response metrics under `response_evaluation`.

### Propagation-augmented root-ranking ablation

Two optional, independently switchable root-ranking additions are available:

1. `--include-propagation-edge-probabilities` appends the root-independent
   `A->B / B->A / No Direct` probability triplet to each oriented physical edge
   in PC-STGR. Missing candidate relations are all-zero masked, not negatives.
2. `propagation_reranker_pipeline.py` reconstructs one P0 DAG per Stage-1 Top-K
   root, extracts auditable graph statistics, and trains a small residual MLP
   with an incident-listwise softmax loss. Each outer reranker fold trains on
   predictions from the corresponding Stage-1 outer-training model and evaluates
   only its OOF Stage-1 validation predictions; epoch selection stays inside the
   outer training partition.

Run the five-way grouped-OOF ablation with identical folds and seeds:

```bash
source scripts/common.sh
bash scripts/run_root_graph_ablation.sh --variant supervised
```

The run compares the original PC-STGR, edge-probability PC-STGR, a
Stage-1-score-only MLP control, the full propagation-statistics MLP, and the
combined model, then writes `summary.json/csv`. The score-only MLP separates
ordinary score recalibration from incremental propagation-graph information.
MLP directories also
contain `candidate_features.json`, fold checkpoints, `final_model.pt`, and a
training summary with candidate recall, correction/corruption counts, NLL, and
Brier score. The MLP requires only root labels; propagation labels are not read.

For later label-free inference:

```bash
python Sys/RootCauseAnalyze/stage1/propagation_reranker_pipeline.py infer \
  --data-root "$PINGMESH_DATA" \
  --root-results ROOT_RESULTS/res.json \
  --checkpoint RERANKER/final_model.pt \
  --output-dir RERANKED_ROOT_RESULTS
```

When `propagation_pipeline.py` consumes `reranked_root_rankings`, it preserves
the learned order and disables the legacy hand-weighted reranking for that case.
This experiment remains separate from the approved deterministic P0 paper
method until its grouped-OOF improvement is established.

## Active root-conditioned graph-rebuild workflow

The active implementation first builds one device-level,
root-independent probabilistic relation graph, then decodes a root-conditioned
propagation DAG for every PC-STGR Top-K candidate. P0 uses deterministic evidence
normalization and is the paper method. The graph explanation can rerank the
candidate roots, while the device DAG remains the primary output.

Backfill or verify the raw topology sidecars before reconstruction:

```bash
python Sys/Preprocess/backfill_topology_context.py \
  --cases-root "$PINGMESH_DATA" \
  --raw-root "$PINGMESH_RAW_DATA" \
  --report topology_context_backfill_report.json \
  --write \
  --require-complete
```

The command is dry-run unless `--write` is present. Existing equivalent files
are left unchanged; differing files are reported as conflicts unless
`--overwrite` is explicitly supplied. It never reads or rewrites case labels,
nodes, or info files.

To inspect a cropped Clos topology and emit a conservative recovery overlay:

```bash
python scripts/reconstruct_collapsed_clos_topology.py \
  --input "$PINGMESH_RAW_DATA" \
  --output "$PINGMESH_RESULTS/reconstructed_topology"
```

The output keeps `observed_topology` unchanged and adds `recovered_topology`
with virtual `SPINE_SET` nodes for connected `LEAF--CORE` projections. It also
emits source-oriented `core_forwarding_layers` and adjacent
`core_layer_connections`. Parallel CORE devices occupy one forwarding stage,
but inter-stage links are never completed into a cartesian product: only raw
`task_topo` CORE—CORE pairs are retained. A disconnected source/sink CORE fabric
is reported as a structural gap without a virtual bridge. The output also
records reconstructed paths, Pod-number assignments, and diagnostics. Virtual
SPINE nodes are display/audit hints only; they are not valid propagation-label
devices or edges.

```bash
python Sys/RootCauseAnalyze/propagation_pipeline.py \
  --data-root "$PINGMESH_DATA" \
  --root-results "$PINGMESH_RESULTS/<paper_05_run>/pc_stgr_oof/res.json" \
  --output-dir "$PINGMESH_RESULTS/<run>/propagation" \
  --stage1-weight 0.5

python Sys/Score/evaluate_propagation.py \
  --predictions "$PINGMESH_RESULTS/<run>/propagation/res.json" \
  --selected-paths "$PINGMESH_RESULTS/<run>/propagation/selected_propagation_paths.json" \
  --out "$PINGMESH_RESULTS/<run>/propagation/validity.json"
```

Stage 2 writes compact ranking and trust summaries to `res.json`. The selected
graph for every successful case is stored separately in
`selected_propagation_paths.json`, a JSON array that can be passed directly to
`pingmesh-propagation-labeler --predictions`. Each `res.json` record links to
its graph through `selected_path_ref`; the evaluator resolves this reference
automatically, while `--selected-paths` makes the artifact dependency explicit.

Propagation edges require a `topology_context.json` generated from the case's
raw `task_topo`. Legacy `linked_from`/`linked_to` fallback data may still expose
devices, but it cannot produce propagation edges or change the Stage 1 order.
This makes every emitted edge traceable to at least one raw topology edge ID.

Before DD training/evaluation, the edge-probability ablation also builds a
label-free `topology_equivalence.json` sidecar. Evidence-free internal devices
are merged only when their role, Pod/failure-domain metadata, and exact
upstream/downstream sets match. Labels and predictions are projected through
the same mapping for macro directed-edge F1 and node F1; root Top-K/MRR remain
at raw-device granularity. The mapping can be audited independently:

```bash
python Sys/Preprocess/build_structural_equivalence.py \
  --cases-root "$PINGMESH_DATA" \
  --report "$PINGMESH_RESULTS/topology_equivalence_report.json" \
  --write \
  --require-raw-topology
```

Unmarked physical pairs remain `unknown` during supervised edge training.
Only `explicit_no_direct` supplies the No Direct class; `definite` and
`possible` DD edges are the annotated positive witness path. The evaluator
derives node sets from DD endpoints and reports case-macro F1.

The sidecar can be opened as an overlay without conversion:

```bash
propagation-labeler \
  --data-root "$PINGMESH_DATA" \
  --labels-root "$PINGMESH_PROPAGATION_LABELS_ROOT" \
  --predictions "$PINGMESH_RESULTS/<run>/propagation/selected_propagation_paths.json" \
  --prediction-overlay
```

The runtime path does not read root or propagation labels. Add `--labels-root`
only to the separate evaluator after engineer path labels exist.

P0 remains the paper method and default edge-probability method. P1 is no longer
run or reported. P4 training is isolated from runtime and writes JSON
classifiers. Its fold-local validation data select a conservative directional
probability threshold and a margin over `No Direct` to reduce graph expansion.
Scored results must use the OOF manifest; the final model is only for later
label-free inference:

```bash
export PINGMESH_PROPAGATION_LABELS_ROOT=/path/to/propagation_labels
bash scripts/run_dd_edge_ablation.sh \
  --root-results "$PINGMESH_RESULTS/<root-run>/pc_stgr_oof/res.json"
```

## Baselines

```bash
bash scripts/run_rca_baselines.sh
```

TraceRCA and NetEventCause are local statistical runs. BiAn additionally needs
the configured local LLM/NPU environment.
