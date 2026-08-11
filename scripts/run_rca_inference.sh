#!/usr/bin/env bash
# Run one RCA inference job with optional selected-policy gating.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    cat <<'EOF'
Usage: ./scripts/run_rca_inference.sh [output-name] [skills] [npu] [batch] [top-k]

Optional environment variables:
  PINGMESH_ENABLE_GATE=1          enable configurable_gate_v1
  PINGMESH_GATE_POLICY_CONFIG=... selected policy JSON from gate_auto
  PINGMESH_USE_SUMMARY_CACHE=1    read PINGMESH_SUMMARY_CACHE_DIR
  PINGMESH_PRINT_FIRST_PROMPT=1   print the first final prompt
EOF
    exit 0
fi

OUTDIR="${1:-inference_$(date +%s)}"
SKILLS="${2:-${PINGMESH_SKILLS}}"
NPU="${3:-${PINGMESH_NPU_CARDS}}"
BATCH="${4:-${PINGMESH_BATCH_SIZE}}"
TOPK="${5:-${PINGMESH_TOP_K}}"
ENABLE_GATE="${PINGMESH_ENABLE_GATE:-0}"
USE_CACHE="${PINGMESH_USE_SUMMARY_CACHE:-0}"
EXTRA_ARGS=(--summary-cache-dir "")

if [ "${ENABLE_GATE}" = "1" ] || [ "${ENABLE_GATE}" = "true" ]; then
    if [ -z "${PINGMESH_GATE_POLICY_CONFIG:-}" ]; then
        echo "[ERROR] PINGMESH_ENABLE_GATE requires PINGMESH_GATE_POLICY_CONFIG." >&2
        exit 2
    fi
    EXTRA_ARGS+=(--gate)
fi
if [ "${USE_CACHE}" = "1" ] || [ "${USE_CACHE}" = "true" ]; then
    EXTRA_ARGS=(--summary-cache-dir "${PINGMESH_SUMMARY_CACHE_DIR}")
    if [ "${ENABLE_GATE}" = "1" ] || [ "${ENABLE_GATE}" = "true" ]; then
        EXTRA_ARGS+=(--gate)
    fi
fi
if [ "${PINGMESH_PRINT_FIRST_PROMPT:-0}" = "1" ] || [ "${PINGMESH_PRINT_FIRST_PROMPT:-0}" = "true" ]; then
    EXTRA_ARGS+=(--print-first-prompt)
fi

echo "============================================"
echo "  RCA inference"
echo "  data:    ${PINGMESH_DATA}"
echo "  output:  ${PINGMESH_RESULTS}/${OUTDIR}"
echo "  skills:  ${SKILLS}"
echo "  top_k:   ${TOPK}"
echo "  npu:     ${NPU}"
echo "  gate:    ${ENABLE_GATE}"
echo "  cache:   ${USE_CACHE}"
echo "============================================"

python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
    --data-root "${PINGMESH_DATA}" \
    --skills ${SKILLS} \
    --npu-cards "${NPU}" \
    --batch-size "${BATCH}" \
    --top-k "${TOPK}" \
    --output-dir "${OUTDIR}" \
    "${EXTRA_ARGS[@]}"

python Sys/Score/Score_N.py "${PINGMESH_RESULTS}/${OUTDIR}/res.json"
echo "RCA inference completed: ${PINGMESH_RESULTS}/${OUTDIR}"
