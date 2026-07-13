#!/usr/bin/env bash
# Paper Exp 05a: precompute candidate-node summaries for cached LLM experiments.
#
# Research question:
#   Can a small local model compress node evidence before main LLM arbitration?
#
# Optional overrides: PINGMESH_SUMMARY_CACHE_DIR, PINGMESH_SUMMARY_MODEL_PATH.
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

echo "============================================"
echo "  Paper Exp 05a: Precompute Summary Cache"
echo "  data:       ${PINGMESH_DATA}"
echo "  cache:      ${PINGMESH_SUMMARY_CACHE_DIR}"
echo "  model:      ${PINGMESH_SUMMARY_MODEL_PATH}"
echo "  npu_cards:  ${PINGMESH_SUMMARY_NPU_CARDS}"
echo "  kv_cache:   ${PINGMESH_SUMMARY_KV_CACHE_GB} GiB per NPU"
echo "  kv_blocks:  ${PINGMESH_SUMMARY_NUM_GPU_BLOCKS} (old vLLM fallback)"
echo "============================================"

python scripts/precompute_node_summaries.py \
    --data-root "${PINGMESH_DATA}" \
    --out-cache "${PINGMESH_SUMMARY_CACHE_DIR}" \
    --npu-cards "${PINGMESH_SUMMARY_NPU_CARDS}" \
    --model-path "${PINGMESH_SUMMARY_MODEL_PATH}" \
    --kv-cache-gb "${PINGMESH_SUMMARY_KV_CACHE_GB}" \
    --num-gpu-blocks-override "${PINGMESH_SUMMARY_NUM_GPU_BLOCKS}" \
    --top-k "${PINGMESH_TOP_K}"
