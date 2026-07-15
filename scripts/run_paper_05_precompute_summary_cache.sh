#!/usr/bin/env bash
# Paper Exp 05a: precompute candidate-node summaries for cached LLM experiments.
#
# Research question:
#   Can a small local model compress node evidence before main LLM arbitration?
#
# Optional overrides: PINGMESH_SUMMARY_CACHE_DIR, PINGMESH_SUMMARY_MODEL_PATH.
#
# Common commands:
#   # First run with the hybrid-v3 cache and 8-way vLLM continuous batching:
#   git pull origin main
#   source scripts/common.sh
#   export PINGMESH_SUMMARY_CACHE_DIR="$PINGMESH_RESULTS/node_summary_cache_hybrid_v3"
#   export PINGMESH_SUMMARY_MAX_NUM_SEQS=8
#   ./scripts/run_paper_05_precompute_summary_cache.sh
#
#   # OOM fallback / higher-throughput tuning:
#   PINGMESH_SUMMARY_MAX_NUM_SEQS=4 ./scripts/run_paper_05_precompute_summary_cache.sh
#   PINGMESH_SUMMARY_MAX_NUM_SEQS=16 ./scripts/run_paper_05_precompute_summary_cache.sh
#
#   # Force regeneration of cache files that already exist:
#   PINGMESH_SUMMARY_OVERWRITE=1 ./scripts/run_paper_05_precompute_summary_cache.sh
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

if [ "$(dirname "${PINGMESH_SUMMARY_CACHE_DIR}")" = "/" ]; then
    echo "[ERROR] Refusing to write the summary cache directly under /." >&2
    echo "        PINGMESH_RESULTS was probably unset when the cache path was exported." >&2
    echo "        Run: source scripts/common.sh" >&2
    echo '             export PINGMESH_SUMMARY_CACHE_DIR="$PINGMESH_RESULTS/node_summary_cache_hybrid_v3"' >&2
    exit 2
fi

if [[ "${PINGMESH_SUMMARY_NPU_CARDS}" == *,* ]]; then
    echo "[ERROR] Summary precomputation currently uses exactly one NPU." >&2
    echo "        Run: export PINGMESH_SUMMARY_NPU_CARDS=0" >&2
    exit 2
fi

if ! [[ "${PINGMESH_SUMMARY_MAX_NUM_SEQS}" =~ ^[1-9][0-9]*$ ]]; then
    echo "[ERROR] PINGMESH_SUMMARY_MAX_NUM_SEQS must be a positive integer." >&2
    exit 2
fi

max_case_candidates=$((2 * PINGMESH_TOP_K))
if [ "${PINGMESH_SUMMARY_MAX_NUM_SEQS}" -gt "${max_case_candidates}" ]; then
    echo "[WARNING] concurrency=${PINGMESH_SUMMARY_MAX_NUM_SEQS} exceeds the maximum"
    echo "          ${max_case_candidates} candidate devices per case; it will not add throughput."
fi

overwrite_args=()
if [ "${PINGMESH_SUMMARY_OVERWRITE:-0}" = "1" ] || [ "${PINGMESH_SUMMARY_OVERWRITE:-0}" = "true" ]; then
    overwrite_args+=(--overwrite)
fi

echo "============================================"
echo "  Paper Exp 05a: Precompute Summary Cache"
echo "  data:       ${PINGMESH_DATA}"
echo "  cache:      ${PINGMESH_SUMMARY_CACHE_DIR}"
echo "  model:      ${PINGMESH_SUMMARY_MODEL_PATH}"
echo "  npu_cards:  ${PINGMESH_SUMMARY_NPU_CARDS}"
echo "  concurrency:${PINGMESH_SUMMARY_MAX_NUM_SEQS} sequences"
echo "  kv_cache:   ${PINGMESH_SUMMARY_KV_CACHE_GB} GiB per NPU"
echo "  kv_blocks:  ${PINGMESH_SUMMARY_NUM_GPU_BLOCKS} (old vLLM fallback)"
echo "============================================"

python scripts/precompute_node_summaries.py \
    --data-root "${PINGMESH_DATA}" \
    --out-cache "${PINGMESH_SUMMARY_CACHE_DIR}" \
    --npu-cards "${PINGMESH_SUMMARY_NPU_CARDS}" \
    --model-path "${PINGMESH_SUMMARY_MODEL_PATH}" \
    --max-num-seqs "${PINGMESH_SUMMARY_MAX_NUM_SEQS}" \
    --kv-cache-gb "${PINGMESH_SUMMARY_KV_CACHE_GB}" \
    --num-gpu-blocks-override "${PINGMESH_SUMMARY_NUM_GPU_BLOCKS}" \
    --top-k "${PINGMESH_TOP_K}" \
    "${overwrite_args[@]}"
