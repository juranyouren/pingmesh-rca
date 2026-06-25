#!/usr/bin/env bash
# ============================================================
# LLM 告警分类增强 Pipeline (per-case 模式)
#
# 步骤:
#   1. LLM 逐 case 分类告警 → 写入每个 case 目录的 alarm_taxonomy.json
#   2. 带分类的纯算法消融 (自动检测 per-case taxonomy)
#   3. 带分类的 LLM 推理 + 评分
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

# ── 步骤 1: LLM 逐 case 分类 (需要 NPU) ──
if [ "${PHASE}" = "classify" ] || [ "${PHASE}" = "all" ]; then
    echo ""
    echo "============================================"
    echo "  步骤 1: LLM 逐 case 告警三分类"
    echo "  数据: ${PINGMESH_DATA}"
    echo "============================================"

    python Sys/RootCauseAnalyze/alarm_classifier.py \
        --data "${PINGMESH_DATA}" \
        --mode per_case \
        --npu-cards "${PINGMESH_NPU_CARDS}" \
        --write

    echo "  分类完成 (每个 case 目录下的 alarm_taxonomy.json)"
fi

# ── 步骤 2: 分类增强纯算法消融 (不依赖 NPU) ──
if [ "${PHASE}" = "ablation" ] || [ "${PHASE}" = "all" ]; then
    echo ""
    echo "============================================"
    echo "  步骤 2: 分类增强纯算法消融"
    echo "  (自动检测 per-case alarm_taxonomy.json)"
    echo "============================================"

    OUTDIR="classified_ablation_$(date +%Y%m%d_%H%M%S)"

    for skills in "1" "2" "1 2"; do
        skname=$(echo ${skills} | tr ' ' '_')
        tag="${OUTDIR}/skills_${skname}"
        echo "--- ${skname} ---"
        # 不传 -t 参数, skill_pipeline 会自动检测 case 目录下的
        # alarm_taxonomy.json 并加载
        python Sys/RootCauseAnalyze/skill_pipeline.py \
            -d "${PINGMESH_DATA}" \
            -s ${skills} -k 5 \
            -w "${PINGMESH_WEIGHTS_MANUAL}" \
            -o "${tag}" 2>&1 | tail -3
    done

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

# ── 步骤 3: LLM 推理 (自动检测 per-case taxonomy) ──
if [ "${PHASE}" = "inference" ] || [ "${PHASE}" = "all" ]; then
    echo ""
    echo "============================================"
    echo "  步骤 3: LLM 推理 (自动检测 per-case taxonomy)"
    echo "============================================"

    OUTDIR="classified_inference_$(date +%s)"

    python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
        -d "${PINGMESH_DATA}" \
        -s ${PINGMESH_SKILLS} \
        -n "${PINGMESH_NPU_CARDS}" \
        -k "${PINGMESH_TOP_K}" \
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
echo "============================================"
