#!/usr/bin/env bash
# Paper Exp 04: cached node-summary ablation.

set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

REUSE_CACHE=0
if [ "${1:-}" = "--reuse-cache" ]; then
    REUSE_CACHE=1
    shift
fi
PREFIX="${1:-paper_04_summary_ablation}"

if [ -z "${PINGMESH_SUMMARY_CACHE_DIR}" ] || [ "${PINGMESH_SUMMARY_CACHE_DIR}" = "/" ]; then
    echo "[ERROR] Refusing unsafe summary cache path: ${PINGMESH_SUMMARY_CACHE_DIR:-<empty>}" >&2
    exit 2
fi
if [[ "${PINGMESH_SUMMARY_NPU_CARDS}" == *,* ]]; then
    echo "[ERROR] Summary precomputation requires exactly one NPU card." >&2
    exit 2
fi

if [ "${REUSE_CACHE}" = "0" ]; then
    overwrite_args=()
    if [ "${PINGMESH_SUMMARY_OVERWRITE:-0}" = "1" ] || [ "${PINGMESH_SUMMARY_OVERWRITE:-0}" = "true" ]; then
        overwrite_args+=(--overwrite)
    fi
    echo "=== [summary_cache] precompute candidate summaries ==="
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
elif [ ! -d "${PINGMESH_SUMMARY_CACHE_DIR}" ]; then
    echo "[ERROR] --reuse-cache requested but cache does not exist: ${PINGMESH_SUMMARY_CACHE_DIR}" >&2
    exit 2
fi

export PINGMESH_EXPERIMENTS="${PINGMESH_EXPERIMENTS:-pipe gate_auto cache_llm gate_cache_llm}"
./scripts/run_rca_experiments.sh "${PREFIX}"
