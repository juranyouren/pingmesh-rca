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
| `run_baselines.sh` | TraceRCA, NetEventCause, and BiAn Pipeline1 baselines. |
| `precompute_node_summaries.py` | Low-level summary-cache builder used by paper experiment 04. |

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
./scripts/run_baselines.sh
```

Use `./scripts/run_paper_04_summary_ablation.sh --reuse-cache` after the cache
has already been generated.

Historical M1/M2/M3 evidence-table experiments and the old policy wrappers live
under `archive/experiments/`. They are not supported runtime entrypoints.
