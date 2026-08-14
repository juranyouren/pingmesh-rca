# RCA Experiment Scripts

`scripts/common.sh` is the single source of paths, model settings, NPU cards,
and default Top-K values. Override its values with environment variables rather
than editing individual runners.

## Supported entrypoints

| Script | Purpose |
| --- | --- |
| `run_rca_experiments.sh` | Canonical deterministic → gate search → gate verification → optional local-LLM pipeline. |
| `run_rca_inference.sh` | One inference job using a previously selected gate policy. |
| `run_paper_01_skill_ablation.sh` | Topology, temporal, and fused deterministic ablation. |
| `run_paper_02_gate_routing.sh` | Offline safe-gate selection and routing evaluation. |
| `run_paper_03_llm_arbitration.sh` | Full local LLM versus gated local LLM. |
| `run_paper_04_summary_ablation.sh` | Precompute/reuse node summaries and compare cached-summary LLM variants. |
| `run_paper_05_spatiotemporal_graph.sh` | Grouped 5-fold OOF evaluation of the unified neural event-graph Stage 1, followed by Stage 2 reranking. |
| `run_baselines.sh` | TraceRCA, NetEventCause, and BiAn Pipeline1 baselines. |
| `precompute_node_summaries.py` | Low-level summary-cache builder used by paper experiment 04. |
| `../Sys/RootCauseAnalyze/propagation_pipeline.py` | Stage 1 → Stage 2 (M1 + M2) label-free pipeline. |
| `../Sys/Score/evaluate_propagation.py` | Propagation validity and optional path-label evaluation. |

## Main RCA workflow

```bash
source scripts/common.sh
PINGMESH_EXPERIMENTS="pipe gate_auto pipe_llm gate_llm" \
  ./scripts/run_rca_experiments.sh
```

`gate_auto` always runs after deterministic results exist. It searches policies,
applies the selected configuration, asserts zero unsafe bypasses and the target
error recall, and emits the gate evaluation reports. Gated LLM runs use the
selected JSON through `PINGMESH_GATE_POLICY_CONFIG`.

For a later inference run:

```bash
source scripts/common.sh
export PINGMESH_GATE_POLICY_CONFIG="$PINGMESH_RESULTS/<run>/gate_search/selected_gate_policy.json"
PINGMESH_ENABLE_GATE=1 ./scripts/run_rca_inference.sh
```

## Paper workflow

```bash
./scripts/run_paper_01_skill_ablation.sh
./scripts/run_paper_02_gate_routing.sh
./scripts/run_paper_03_llm_arbitration.sh
./scripts/run_paper_04_summary_ablation.sh
./scripts/run_paper_05_spatiotemporal_graph.sh
./scripts/run_baselines.sh
```

## Neural spatio-temporal Stage 1

The neural paper experiment produces three directly comparable Score_N rows:

- `deterministic`: the existing topology + temporal score fusion;
- `neural_oof`: grouped out-of-fold predictions from the learned event graph;
- `neural_stage2`: the same OOF candidates after propagation-constrained reranking.

Run it in the server PyTorch environment:

```bash
bash scripts/run_paper_05_spatiotemporal_graph.sh
```

The run directory contains `summary.json`, `summary.csv`, every fold checkpoint,
training histories, OOF `res.json`, Stage 2 validity metrics, and
`neural_oof/final_model.pt`. The final checkpoint is trained after OOF scoring
and is intended for later label-free inference:

```bash
python Sys/RootCauseAnalyze/stage1/neural_pipeline.py infer \
  --data-root "$PINGMESH_DATA" \
  --checkpoint "$PINGMESH_RESULTS/<run>/neural_oof/final_model.pt" \
  --output-dir "$PINGMESH_RESULTS/<run>/neural_inference" \
  --top-k "$PINGMESH_TOP_K"
```

Scored paper results must use `neural_oof/res.json`, not predictions from the
checkpoint trained on all labeled cases.

Use `./scripts/run_paper_04_summary_ablation.sh --reuse-cache` after the cache
has already been generated.

Historical M1/M2/M3 evidence-table experiments and the old policy wrappers live
under `archive/experiments/`. They are not supported runtime entrypoints.

## 2stage workflow

Stage 1 uses the parallel temporal and alarm-topology rankings. Stage 2/M1 builds
one root-independent probabilistic hypothesis graph. Stage 2/M2 explains that
same graph with every root candidate, reconstructs the corresponding DAG, and
reranks roots using only the weighted Stage 1 and explanation scores:

```bash
PINGMESH_EXPERIMENTS="pipe propagation" \
  ./scripts/run_rca_experiments.sh 2stage

# Or run the Stage 1 + Stage 2 entrypoint directly:
python Sys/RootCauseAnalyze/propagation_pipeline.py \
  --data-root "$PINGMESH_DATA" \
  --root-results "$PINGMESH_RESULTS/<run>/pipe/res.json" \
  --output-dir "$PINGMESH_RESULTS/<run>/propagation" \
  --stage1-weight 0.5

python Sys/Score/evaluate_propagation.py \
  --predictions "$PINGMESH_RESULTS/<run>/propagation/res.json" \
  --out "$PINGMESH_RESULTS/<run>/propagation/validity.json"
```

The runtime path never reads root or propagation labels. Add `--labels-root`
only to the separate evaluator after engineer path labels exist.
