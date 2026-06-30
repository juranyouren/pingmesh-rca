#!/usr/bin/env bash
# ============================================================
# Run the small-model NODES summary experiment.
#
# Modes:
#   gate=0 : pipe_summary_llm
#            pipe evidence -> 1.5B NODES summary -> main LLM reranking
#   gate=1 : gate_pipe_summary_llm
#            pipe evidence -> trust-tree gate -> bypass/operator or
#            1.5B NODES summary -> main LLM arbitration
#
# Usage:
#   ./scripts/run_summary_llm.sh
#   ./scripts/run_summary_llm.sh my_outdir
#   ./scripts/run_summary_llm.sh my_outdir 1
#
# Required:
#   export PINGMESH_SUMMARY_MODEL_PATH=/path/to/1.5B-model
#
# Optional:
#   export PINGMESH_SUMMARY_NPU_CARDS=0
#   export PINGMESH_SUMMARY_GATE=1
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

OUTDIR="${1:-}"
SUMMARY_GATE="${2:-${PINGMESH_SUMMARY_GATE:-0}}"
SKILLS="${PINGMESH_SKILLS:-1 2}"
TOPK="${PINGMESH_TOP_K:-5}"
BATCH="${PINGMESH_BATCH_SIZE:-8}"
NPU="${PINGMESH_NPU_CARDS:-0,1,2,3,4,5,6,7}"
SUMMARY_MODEL_PATH="${PINGMESH_SUMMARY_MODEL_PATH:-}"
SUMMARY_NPU_CARDS="${PINGMESH_SUMMARY_NPU_CARDS:-}"
SUMMARY_MAX_TOKENS="${PINGMESH_SUMMARY_MAX_TOKENS:-1024}"

if [ -z "${SUMMARY_MODEL_PATH}" ]; then
    echo "[ERROR] PINGMESH_SUMMARY_MODEL_PATH is required for summary experiments." >&2
    exit 1
fi

if [ -z "${OUTDIR}" ]; then
    if [ "${SUMMARY_GATE}" = "1" ] || [ "${SUMMARY_GATE}" = "true" ] || [ "${SUMMARY_GATE}" = "TRUE" ]; then
        OUTDIR="gate_pipe_summary_llm_$(date +%Y%m%d_%H%M%S)"
    else
        OUTDIR="pipe_summary_llm_$(date +%Y%m%d_%H%M%S)"
    fi
fi

CONF_ARGS=()
if [ "${SUMMARY_GATE}" = "1" ] || [ "${SUMMARY_GATE}" = "true" ] || [ "${SUMMARY_GATE}" = "TRUE" ]; then
    CONF_ARGS+=(--confidence-gate)
fi

SUMMARY_ARGS=(--summarize-nodes --summary-model-path "${SUMMARY_MODEL_PATH}" --summary-max-tokens "${SUMMARY_MAX_TOKENS}")
if [ -n "${SUMMARY_NPU_CARDS}" ]; then
    SUMMARY_ARGS+=(--summary-npu-cards "${SUMMARY_NPU_CARDS}")
fi

echo "============================================"
echo "  Summary NODES + LLM experiment"
echo "  data:          ${PINGMESH_DATA}"
echo "  output:        ${PINGMESH_RESULTS}/${OUTDIR}"
echo "  gate:          ${SUMMARY_GATE}"
echo "  skills:        ${SKILLS}"
echo "  top_k:         ${TOPK}"
echo "  main_npu:      ${NPU}"
echo "  summary_model: ${SUMMARY_MODEL_PATH}"
echo "  summary_npu:   ${SUMMARY_NPU_CARDS:-<worker-first-card>}"
echo "============================================"

python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
    -d "${PINGMESH_DATA}" \
    -s ${SKILLS} \
    -n "${NPU}" \
    -b "${BATCH}" \
    -k "${TOPK}" \
    -o "${OUTDIR}" \
    "${SUMMARY_ARGS[@]}" \
    "${CONF_ARGS[@]}"

echo ""
echo "--- scoring ---"
python -c "
from Sys.Score.Score_N import Scorer
s = Scorer('${PINGMESH_RESULTS}/${OUTDIR}/res.json')
s.calculate_metrics()
"

echo "Done. Result: ${PINGMESH_RESULTS}/${OUTDIR}/"
