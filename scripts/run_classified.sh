#!/usr/bin/env bash
# ============================================================
# LLM 告警分类 + 分类增强 Pipeline
# 新方案: 对告警做 causal/symptom/noise 三分类 → PageRank+Temporal 加权
#
# 步骤:
#   1. (离线一次性) LLM 分类全数据集告警名 → alarm_taxonomy.json
#   2. 带 taxonomy 的纯算法消融
#   3. 带 taxonomy 的 LLM 推理 + 评分
#
# 用法:
#   ./scripts/run_classified.sh                    # 全流程
#   ./scripts/run_classified.sh classify           # 仅第1步
#   PINGMESH_DATA=/new/path ./scripts/run_classified.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

PHASE="${1:-all}"

# ── 步骤 1: LLM 告警分类 (离线) ──
if [ "${PHASE}" = "classify" ] || [ "${PHASE}" = "all" ]; then
    echo ""
    echo "============================================"
    echo "  步骤 1: LLM 告警三分类"
    echo "  数据: ${PINGMESH_DATA}"
    echo "  输出: ${PINGMESH_TAXONOMY}"
    echo "============================================"

    # 如果已有 taxonomy 则增量更新
    BASE_ARG=""
    if [ -f "${PINGMESH_TAXONOMY}" ]; then
        BASE_ARG="--base ${PINGMESH_TAXONOMY}"
        echo "  (增量更新已有 taxonomy)"
    fi

    python Sys/RootCauseAnalyze/alarm_classifier.py \
        --data "${PINGMESH_DATA}" \
        --output "${PINGMESH_TAXONOMY}" \
        --npu-cards "${PINGMESH_NPU_CARDS}" \
        ${BASE_ARG}

    echo "  分类完成: ${PINGMESH_TAXONOMY}"
fi

# ── 步骤 2: 分类增强的纯算法消融 ──
if [ "${PHASE}" = "ablation" ] || [ "${PHASE}" = "all" ]; then
    echo ""
    echo "============================================"
    echo "  步骤 2: 分类增强纯算法消融"
    echo "============================================"

    if [ ! -f "${PINGMESH_TAXONOMY}" ]; then
        echo "ERROR: taxonomy 不存在, 请先运行步骤 1"
        exit 1
    fi

    OUTDIR="classified_ablation_$(date +%Y%m%d_%H%M%S)"

    # 三组: [1] topo, [2] temporal, [1,2] topo+temporal (均带分类)
    for skills in "1" "2" "1 2"; do
        skname=$(echo ${skills} | tr ' ' '_')
        tag="${OUTDIR}/skills_${skname}"
        echo "--- ${skname} ---"
        python Sys/RootCauseAnalyze/skill_pipeline.py \
            -d "${PINGMESH_DATA}" \
            -s ${skills} -k 5 \
            -t "${PINGMESH_TAXONOMY}" \
            -w "${PINGMESH_WEIGHTS_MANUAL}" \
            -o "${tag}" 2>&1 | tail -3
    done

    # 评分汇总
    echo ""; echo "--- 评分 ---"
    for skills in "1" "2" "1 2"; do
        skname=$(echo ${skills} | tr ' ' '_')
        res_json="${PINGMESH_RESULTS}/${OUTDIR}/skills_${skname}/res.json"
        if [ -f "${res_json}" ]; then
            echo "  [${skname}]:"
            python -c "
from Sys.Score.Score_N import Scorer
s = Scorer('${res_json}')
m = s.calculate_metrics()['skill_evaluation']['ranking_metrics']
print(f'    Top-1={m[\"Top-1 Acc (%)\"]}  Top-3={m[\"Top-3 Acc (%)\"]}  Top-5={m[\"Top-5 Acc (%)\"]}')
" 2>&1
        fi
    done
fi

# ── 步骤 3: LLM 推理 (带分类) ──
if [ "${PHASE}" = "inference" ] || [ "${PHASE}" = "all" ]; then
    echo ""
    echo "============================================"
    echo "  步骤 3: LLM 推理 (分类增强)"
    echo "============================================"

    if [ ! -f "${PINGMESH_TAXONOMY}" ]; then
        echo "ERROR: taxonomy 不存在, 请先运行步骤 1"
        exit 1
    fi

    OUTDIR="classified_inference_$(date +%s)"

    python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
        -d "${PINGMESH_DATA}" \
        -s ${PINGMESH_SKILLS} \
        -n "${PINGMESH_NPU_CARDS}" \
        -k "${PINGMESH_TOP_K}" \
        -t "${PINGMESH_TAXONOMY}" \
        -o "${OUTDIR}"

    echo ""
    echo "--- 评分 ---"
    python -c "
from Sys.Score.Score_N import Scorer
s = Scorer('${PINGMESH_RESULTS}/${OUTDIR}/res.json')
s.calculate_metrics()
"
    echo "完成。结果: ${PINGMESH_RESULTS}/${OUTDIR}/"
fi

echo ""
echo "============================================"
echo "基线 (无分类): topo+temporal = 56.64% Top-1"
echo "对比分类增强后的数字, 看增益。"
echo "============================================"
