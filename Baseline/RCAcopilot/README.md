# RCACopilot Pingmesh Baseline

This directory contains the single RCACopilot-style pipeline requested for the
Pingmesh root-cause device localization experiment.

```text
case parsing
  -> diagnostic information construction
  -> FastText embedding
  -> time-aware nearest-neighbor demonstrations
  -> 120-140 word diagnostic summary
  -> local vLLM root-cause prediction
  -> Top-1/3/5 and latency evaluation
```

The paper-compatible defaults are `K=5` and `alpha=0.3`. The default split is
75% train and 25% test with seed 42. Query evidence is label-free; labels are
used only to create the offline evaluation target and to annotate the
training-set demonstrations.

## Server command

From the repository root:

```bash
python Baseline/RCAcopilot/run.py \
  --data-root "$PINGMESH_DATA" \
  --output-dir "$PINGMESH_RESULTS/rcacopilot" \
  --model-path "$PINGMESH_MODEL_PATH" \
  --npu-cards "$PINGMESH_NPU_CARDS"
```

The output directory contains:

- `summary.json`: split, Top-1/3/5, and latency summaries;
- `records.json`: one prediction record per test case;
- `run_config.json`: reproducibility parameters.

If `fasttext` or `vllm` is unavailable, the runner uses deterministic hashing
embeddings and a retrieval fallback so the data path can be smoke-tested. A
server result intended for the paper should report `embedding_backend=fasttext`
and `backend=vllm` in `summary.json`.
