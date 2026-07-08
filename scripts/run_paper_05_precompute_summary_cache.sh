#!/usr/bin/env bash
# Paper Exp 05a: precompute candidate-node summaries for cached LLM experiments.
#
# Research question:
#   Can a small local model compress node evidence before main LLM arbitration?
#
# Required:
#   PINGMESH_SUMMARY_CACHE_DIR=/path/to/cache
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

: "${PINGMESH_SUMMARY_CACHE_DIR:?Set PINGMESH_SUMMARY_CACHE_DIR to a cache output directory.}"

echo "============================================"
echo "  Paper Exp 05a: Precompute Summary Cache"
echo "  data:       ${PINGMESH_DATA}"
echo "  cache:      ${PINGMESH_SUMMARY_CACHE_DIR}"
echo "  model:      ${PINGMESH_SUMMARY_MODEL_PATH}"
echo "  npu_cards:  ${PINGMESH_SUMMARY_NPU_CARDS}"
echo "============================================"

python scripts/precompute_node_summaries.py \
    --data-root "${PINGMESH_DATA}" \
    --out-cache "${PINGMESH_SUMMARY_CACHE_DIR}" \
    --npu-cards "${PINGMESH_SUMMARY_NPU_CARDS}" \
    --model-path "${PINGMESH_SUMMARY_MODEL_PATH}" \
    --top-k "${PINGMESH_TOP_K}"
