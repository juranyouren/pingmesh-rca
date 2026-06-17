#!/usr/bin/env bash
# ============================================================
# Skill 消融实验矩阵 + 评分
# 用法:
#   ./scripts/run_ablation.sh              # 默认 NPU=0,1
#   ./scripts/run_ablation.sh 0,1,2,3      # 指定 NPU
# ============================================================
set -euo pipefail

PROJECT_ROOT="/home/sbp/lixinyang/pingmesh"
DATA="${PROJECT_ROOT}/data/nodes_labeled"
RES="${PROJECT_ROOT}/data/res"

NPU="${1:-0,1}"
TIMESTAMP="ablation_$(date +%s)"

echo "============================================"
echo "  Skill 消融实验矩阵"
echo "  数据:   ${DATA}"
echo "  NPU:    ${NPU}"
echo "  前缀:   ${TIMESTAMP}"
echo "============================================"

cd "${PROJECT_ROOT}"

# ── 消融矩阵 ──
for skills in "1" "1 2" "1 3" "1 2 3"; do
    tag="${TIMESTAMP}_skills_$(echo ${skills} | tr ' ' '_')"
    echo ""
    echo "=== 组合: skills=[${skills}] -> ${tag} ==="
    python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
        -d "${DATA}" \
        -s ${skills} \
        -n "${NPU}" \
        -o "${tag}"
done

# ── 全部评分 ──
echo ""
echo "============================================"
echo "  评分汇总"
echo "============================================"

for skills in "1" "1 2" "1 3" "1 2 3"; do
    tag="${TIMESTAMP}_skills_$(echo ${skills} | tr ' ' '_')"
    res_json="${RES}/${tag}/res.json"
    if [ -f "${res_json}" ]; then
        echo ""
        echo "--- ${tag} ---"
        python -c "
from Sys.Score.Score_N import Scorer, ResponseParser
s = Scorer('${res_json}')
s.calculate_metrics()
"
    else
        echo "  [跳过] ${res_json} 不存在"
    fi
done

echo ""
echo "完成。结果目录: ${RES}/${TIMESTAMP}_skills_*"
