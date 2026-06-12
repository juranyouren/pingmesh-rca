#!/usr/bin/env bash
# ============================================================
# Skill Pipeline 消融实验 — 测试不同 Skill 组合的 Top-K 召回率
# 纯算法，不依赖 LLM / NPU
#
# 用法:
#   ./scripts/run_skill_ablation.sh              # 全部组合
#   ./scripts/run_skill_ablation.sh my_prefix    # 自定义前缀
# ============================================================
set -euo pipefail

PROJECT_ROOT="/home/sbp/lixinyang/pingmesh"
DATA="${PROJECT_ROOT}/data/nodes_labeled"
RES="${PROJECT_ROOT}/data/res"

PREFIX="${1:-skill_ablation}"
TIMESTAMP="${PREFIX}_$(date +%s)"

cd "${PROJECT_ROOT}"

echo "============================================"
echo "  Skill Pipeline 消融实验 (纯算法)"
echo "  数据: ${DATA}"
echo "  前缀: ${TIMESTAMP}"
echo "============================================"

# ── 消融矩阵: 有向 vs 无向 × 不同 skill 组合 ──
# 共 8 组: 无向/有向 × [1], [1,2], [1,3], [1,2,3]

declare -A SKILL_NAMES
SKILL_NAMES=(["1"]="topo" ["1 2"]="topo_co" ["1 3"]="topo_temporal" ["1 2 3"]="all")

for directed in "" "--directed"; do
    if [ -z "${directed}" ]; then
        dname="undir"
    else
        dname="dir"
    fi

    for skills in "1" "1 2" "1 3" "1 2 3"; do
        skname="${SKILL_NAMES[${skills}]}"
        tag="${TIMESTAMP}/${dname}_skills_${skname}"

        echo ""
        echo "=== ${dname} + ${skname} -> ${tag} ==="
        python Sys/RootCauseAnalyze/skill_pipeline.py \
            -d "${DATA}" \
            -s ${skills} ${directed} \
            -o "${tag}" \
            -k 5
    done
done

# ── 全部评分 ──
echo ""
echo "============================================"
echo "  评分汇总"
echo "============================================"

for directed in "undir" "dir"; do
    for skname in "topo" "topo_co" "topo_temporal" "all"; do
        res_json="${RES}/${TIMESTAMP}/${directed}_skills_${skname}/res.json"
        if [ -f "${res_json}" ]; then
            echo ""
            echo "--- ${directed}/${skname} ---"
            python -c "
from Sys.Score.Score_N import Scorer, LlmTextParser
s = Scorer('${res_json}')
s.calculate_metrics()
"
        fi
    done
done

echo ""
echo "完成。结果目录: ${RES}/${TIMESTAMP}/"
