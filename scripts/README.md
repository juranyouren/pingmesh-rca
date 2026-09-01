# Legacy and Device-Level Prototype Experiment Scripts

> The active paper method is the three-module heterogeneous root-and-propagation
> graph design in `docs/论文方案.md`. A dependency-free heterogeneous V0 now runs
> end to end without an external root input. The remaining scripts implement the
> older device-level prototype and historical root-ranking baselines.

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
bash scripts/run_heterogeneous_propagation_v0.sh
```

The command never reads `label.json` or a root-result file. It writes compact
case summaries to `res.json` and full graphs to `heterogeneous_graphs.json`.
The wrapper first backfills and verifies raw topology contexts. Set
`PINGMESH_HETERO_BACKFILL_TOPOLOGY=0` only when the sidecars have already been
verified. The first positional argument changes the run tag.

`scripts/common.sh` is the single source of server paths, model settings, NPU
cards, and default Top-K values. Override it with environment variables instead
of editing individual runners.

Set `PINGMESH_RAW_DATA` to the directory containing the original full-link JSON
files whose `full_link.task_topo.value` corresponds to `PINGMESH_DATA` cases.

## Supported legacy/prototype entrypoints

| Script | Purpose |
| --- | --- |
| `run_heterogeneous_propagation_v0.sh` | Active root-input-free heterogeneous V0: topology backfill, Device/Event/Symptom construction, bounded joint root/DAG reconstruction, and full graph artifacts. |
| `run_paper_05_pc_stgr.sh` | Legacy-compatible runner that generates optional PC-STGR candidates and then invokes propagation reconstruction; not the paper's main experiment definition. |
| `run_stage2_edge_probability_ablation.sh` | Compare P0, P1 Logit/Softmax, and leakage-safe P4 supervised edge probabilities with one replaceable root-candidate file. |
| `run_baselines.sh` | TraceRCA, NetEventCause, and BiAn Pipeline 1 baselines. |
| `../Sys/RootCauseAnalyze/stage1/pipeline.py` | Deterministic topology + temporal Stage 1 baseline. |
| `../Sys/RootCauseAnalyze/stage1/neural_pipeline.py` | Current PC-STGR OOF training and label-free inference implementation. |
| `../Sys/RootCauseAnalyze/stage1/neural_ssl_pipeline.py` | Optional fold-local self-supervised pretraining, supervised fine-tuning, OOF evaluation, and label-free inference. |
| `../Sys/Preprocess/backfill_topology_context.py` | Backfill and verify per-case topology contexts from raw `task_topo`. |
| `../Sys/RootCauseAnalyze/propagation_pipeline.py` | Current device-level, label-free propagation prototype with compatibility root-candidate input. |
| `../Sys/Score/evaluate_propagation.py` | Propagation validity and optional path-label evaluation. |

The Gate, Trust-Tree, Skill Pipeline, candidate-summary path, and their old
paper-01 through paper-04 wrappers have been removed. They are not part of the
runtime or supported comparison workflow.

## Supporting root-candidate status

PC-STGR is an available **supporting root-candidate generator**, not the active
paper method. Its historical implementation contract is recorded in
`docs/PC-STGR设计方案.md`; the active paper plan is `docs/论文方案.md`. The current
`stage1/neural_*` code and `run_paper_05_pc_stgr.sh` implement PC-STGR. A new
grouped OOF run is still required for any candidate-quality claim; do not rename
the historical IC-STGR 73.58/93.71/97.48 Top-1/Top-3/Top-5 result as PC-STGR or
as a propagation-graph result.

Run the compatibility end-to-end workflow in the server PyTorch environment:

```bash
bash scripts/run_paper_05_pc_stgr.sh
```

The default remains the original supervised PC-STGR. Select the optional
self-supervised-pretrained variant with either form:

```bash
bash scripts/run_paper_05_pc_stgr.sh paper_05_pc_stgr_ssl self_supervised

# Equivalent environment-variable form
PINGMESH_NEURAL_VARIANT=self_supervised \
  bash scripts/run_paper_05_pc_stgr.sh paper_05_pc_stgr_ssl
```

PC-STGR-SSL pretrains only on the current fold's training cases reloaded without
labels, then fine-tunes on their root labels. Validation-fold cases are excluded
from the vocabulary and pretraining data.

It produces three compatibility rows:

- `deterministic`: topology + temporal white-box baseline;
- `pc_stgr_oof`: grouped OOF PC-STGR predictions;
- `pc_stgr_stage2`: the same OOF candidates after Stage 2 reranking.

The run directory contains `summary.json`, `summary.csv`, fold checkpoints,
training histories, OOF `res.json`, Stage 2 validity metrics, and
`pc_stgr_oof/final_model.pt`. Candidate-ranking scores must use
`pc_stgr_oof/res.json`; the final model is trained on all labeled cases only for
later unseen-case inference. These rows do not constitute the
propagation-reconstruction main table.

When `self_supervised` is selected, the corresponding directories are
`pc_stgr_ssl_oof` and `pc_stgr_ssl_stage2`, and the checkpoint is stored as
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

## Current device-level prototype workflow

This legacy-compatible implementation first builds one device-level,
root-independent probabilistic relation graph, then decodes a root-conditioned
propagation DAG for every external root candidate. It may compare graph
explanations and rerank roots as an auxiliary output. Existing
`Stage 2/M1/M2` schema names are compatibility labels, not the active paper
structure and not an implementation of the new heterogeneous M1/M2/M3 design.

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

P0 remains the default edge-probability method. P1 can be selected during
label-free inference:

```bash
python Sys/RootCauseAnalyze/propagation_pipeline.py \
  --data-root "$PINGMESH_DATA" \
  --root-results "$PINGMESH_RESULTS/<run>/pc_stgr_oof/res.json" \
  --output-dir "$PINGMESH_RESULTS/<run>/p1" \
  --edge-probability-method logit_softmax_v1
```

P4 training is isolated from runtime and writes JSON classifiers. Scored
results must use the OOF manifest; the final model is only for later
label-free inference:

```bash
export PINGMESH_PROPAGATION_LABELS_ROOT=/path/to/propagation_labels
bash scripts/run_stage2_edge_probability_ablation.sh \
  "$PINGMESH_RESULTS/<paper_05_run>/pc_stgr_oof/res.json"
```

## Baselines

```bash
bash scripts/run_baselines.sh
```

TraceRCA and NetEventCause are local statistical runs. BiAn additionally needs
the configured local LLM/NPU environment.
