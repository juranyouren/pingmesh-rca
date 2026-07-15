#!/usr/bin/env bash
# ============================================================
# 单次推理 + 评分
# 配置来自 scripts/common.sh (环境变量或默认值)
#
# 用法:
#   ./scripts/run_inference.sh                    # 全部默认
#   ./scripts/run_inference.sh my_test            # 指定输出目录名
#   PINGMESH_DATA=/path/to/data ./scripts/run_inference.sh  # 切换数据
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

OUTDIR="${1:-}"
SKILLS="${2:-${PINGMESH_SKILLS}}"
NPU="${3:-${PINGMESH_NPU_CARDS}}"
BATCH="${4:-${PINGMESH_BATCH_SIZE}}"
TOPK="${5:-${PINGMESH_TOP_K}}"
CONF_GATE="${PINGMESH_CONFIDENCE_GATE:-0}"
CONF_HIGH_MARGIN="${PINGMESH_CONFIDENCE_HIGH_MARGIN:-15}"
CONF_AGREEMENT_MARGIN="${PINGMESH_CONFIDENCE_AGREEMENT_MARGIN:-8}"
CONF_ARGS=()
DEBUG_ARGS=()
if [ "${CONF_GATE}" = "1" ] || [ "${CONF_GATE}" = "true" ] || [ "${CONF_GATE}" = "TRUE" ]; then
    CONF_ARGS+=(--confidence-gate)
    CONF_ARGS+=(--confidence-high-margin "${CONF_HIGH_MARGIN}")
    CONF_ARGS+=(--confidence-agreement-margin "${CONF_AGREEMENT_MARGIN}")
fi
if [ "${PINGMESH_PRINT_FIRST_PROMPT:-0}" = "1" ] || [ "${PINGMESH_PRINT_FIRST_PROMPT:-0}" = "true" ] || [ "${PINGMESH_PRINT_FIRST_PROMPT:-0}" = "TRUE" ]; then
    DEBUG_ARGS+=(--print-first-prompt)
fi

echo "============================================"
echo "  单次推理"
echo "  数据:    ${PINGMESH_DATA}"
echo "  Skill:   ${SKILLS} (1=topo, 2=temporal)"
echo "  Top-K:   ${TOPK}"
echo "  NPU:     ${NPU}"
echo "  Gate:    ${CONF_GATE} (high_margin=${CONF_HIGH_MARGIN}, agreement_margin=${CONF_AGREEMENT_MARGIN})"
echo "============================================"

if [ -z "${OUTDIR}" ]; then OUTDIR="inference_$(date +%s)"; fi

python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
    -d "${PINGMESH_DATA}" \
    -s ${SKILLS} \
    -n "${NPU}" \
    -b "${BATCH}" \
    -k "${TOPK}" \
    -o "${OUTDIR}" \
    "${CONF_ARGS[@]}" \
    "${DEBUG_ARGS[@]}"

echo ""
echo "--- 评分 ---"
python -c "
from Sys.Score.Score_N import Scorer
s = Scorer('${PINGMESH_RESULTS}/${OUTDIR}/res.json')
s.calculate_metrics()
"
echo "完成。结果: ${PINGMESH_RESULTS}/${OUTDIR}/"
