#!/usr/bin/env bash
# ============================================================
# 单次推理 + 评分
# 用法:
#   ./scripts/run_inference.sh                        # topo+temp, k=5
#   ./scripts/run_inference.sh my_test                # 指定输出目录名
#   ./scripts/run_inference.sh my_test "1 2" 0,1 8 5  # 全部参数
# ============================================================
set -euo pipefail

PROJECT_ROOT="/home/sbp/lixinyang/pingmesh"
DATA="${PROJECT_ROOT}/data/nodes_labeled"

OUTDIR="${1:-}"
SKILLS="${2:-1 2}"
NPU="${3:-0,1}"
BATCH="${4:-8}"
TOPK="${5:-5}"

cd "${PROJECT_ROOT}"

echo "============================================"
echo "  单次推理"
echo "  Skill:   ${SKILLS} (1=topo, 2=temporal)"
echo "  Top-K:   ${TOPK}"
echo "  NPU:     ${NPU}"
echo "  Batch:   ${BATCH}"
echo "============================================"

if [ -z "${OUTDIR}" ]; then OUTDIR="inference_$(date +%s)"; fi

python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
    -d "${DATA}" \
    -s ${SKILLS} \
    -n "${NPU}" \
    -b "${BATCH}" \
    -k "${TOPK}" \
    -o "${OUTDIR}"

echo ""
echo "--- 评分 ---"
python -c "
from Sys.Score.Score_N import Scorer, ResponseParser
s = Scorer('${PROJECT_ROOT}/data/res/${OUTDIR}/res.json')
s.calculate_metrics()
"
echo "完成。结果: ${PROJECT_ROOT}/data/res/${OUTDIR}/"
