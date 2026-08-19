# RCA Experiment Scripts

`scripts/common.sh` is the single source of server paths, model settings, NPU
cards, and default Top-K values. Override it with environment variables instead
of editing individual runners.

## Supported entrypoints

| Script | Purpose |
| --- | --- |
| `run_paper_05_pc_stgr.sh` | Current executable Stage 1 paper workflow: deterministic baseline, grouped 5-fold OOF PC-STGR, then Stage 2 reranking. |
| `run_stage2_edge_probability_ablation.sh` | Compare P0, P1 Logit/Softmax, and leakage-safe P4 supervised edge probabilities with one Stage 1 result. |
| `run_baselines.sh` | TraceRCA, NetEventCause, and BiAn Pipeline 1 baselines. |
| `../Sys/RootCauseAnalyze/stage1/pipeline.py` | Deterministic topology + temporal Stage 1 baseline. |
| `../Sys/RootCauseAnalyze/stage1/neural_pipeline.py` | Current PC-STGR OOF training and label-free inference implementation. |
| `../Sys/RootCauseAnalyze/propagation_pipeline.py` | Stage 1 → Stage 2 (M1 + M2) label-free pipeline. |
| `../Sys/Score/evaluate_propagation.py` | Propagation validity and optional path-label evaluation. |

The Gate, Trust-Tree, Skill Pipeline, candidate-summary path, and their old
paper-01 through paper-04 wrappers have been removed. They are not part of the
paper runtime or supported comparison workflow.

## Stage 1 status

The Stage 1 method is **PC-STGR (Path-Conditioned Spatio-Temporal Graph
Ranker)**, specified in `docs/PC-STGR设计方案.md`. The current
`stage1/neural_*` code and `run_paper_05_pc_stgr.sh` implement PC-STGR. A new
grouped OOF run is still required; do not rename the historical IC-STGR
73.58/93.71/97.48 Top-1/Top-3/Top-5 result as PC-STGR.

Run the current reproducible workflow in the server PyTorch environment:

```bash
bash scripts/run_paper_05_pc_stgr.sh
```

It produces three comparable rows:

- `deterministic`: topology + temporal white-box baseline;
- `pc_stgr_oof`: grouped OOF PC-STGR predictions;
- `pc_stgr_stage2`: the same OOF candidates after Stage 2 reranking.

The run directory contains `summary.json`, `summary.csv`, fold checkpoints,
training histories, OOF `res.json`, Stage 2 validity metrics, and
`pc_stgr_oof/final_model.pt`. Scored paper results must use
`pc_stgr_oof/res.json`; the final model is trained on all labeled cases only for
later unseen-case inference.

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

## Stage 2 workflow

Stage 2/M1 builds one root-independent probabilistic hypothesis graph. Stage
2/M2 explains that shared graph with every Stage 1 root candidate, constructs
the corresponding root-conditioned DAG, and reranks roots using the Stage 1 and
explanation scores.

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
