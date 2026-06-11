#!/usr/bin/env bash
# ============================================================
# pingmesh RCA 推理脚本示例
# 使用前修改 PROJECT_ROOT 为实际路径
# ============================================================
set -euo pipefail

PROJECT_ROOT="/home/sbp/lixinyang/pingmesh"
DATA="${PROJECT_ROOT}/data/nodes_labeled"
RES="${PROJECT_ROOT}/data/res"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "${PROJECT_ROOT}"

echo "============================================"
echo "  pingmesh RCA 推理示例"
echo "  数据: ${DATA}"
echo "  结果: ${RES}"
echo "============================================"

# ============================================================
# 1. SkilledAnalyzer — Skill 触发推理（最常用）
# ============================================================

run_skilled() {
    local tag="$1"; shift
    echo ""
    echo "--- SkilledAnalyzer: ${tag} ---"
    python Sys/RootCauseAnalyze/SkilledAnalyzer.py "$@"
}

# 全量跑，全部 Skill，默认 NPU=0,1
# run_skilled "full" -d "${DATA}" -o "${RES}/skilled_full"

# 指定数据目录 + 自定义输出目录
# run_skilled "custom" -d "${DATA}" -o "${RES}/skilled_test_001"

# 仅拓扑 Skill（消融：无 co_occur 无 temporal）
# run_skilled "topo_only" -s 1 -o "${RES}/skilled_topo_only"

# 4 卡并行（2 实例），全量 Skill
# run_skilled "4card" -n 0,1,2,3 -s 1 2 3 -b 16

# 只重跑错案（回归测试）
# run_skilled "failures" \
#   --failures-from "${RES}/skilled_prev/draft_ranking_failures.json"

# ============================================================
# 2. SkillNRefineAnalyzer — Skill + Refine 双阶段（最强方案）
# ============================================================

run_refine() {
    local tag="$1"; shift
    echo ""
    echo "--- SkillNRefineAnalyzer: ${tag} ---"
    python Sys/RootCauseAnalyze/SkillNRefineAnalyzer.py "$@"
}

# 8 卡全开，全量 Skill
# run_refine "8card" -d "${DATA}" -n 0,1,2,3,4,5,6,7 -s 1 2 3

# 仅拓扑 + 时序（消融：无 co_occur）
# run_refine "topo_temporal" -s 1 3 -n 0,1,2,3

# ============================================================
# 3. graph_only — 纯图算法消融（不依赖 LLM / NPU）
# ============================================================

run_graph() {
    local tag="$1"; shift
    echo ""
    echo "--- graph_only: ${tag} ---"
    python graph_only.py "$@"
}

# 无向 PageRank
# run_graph "undirected" -d "${DATA}"

# 有向 PageRank
# run_graph "directed" -d "${DATA}" --directed -o "${RES}/graph_directed"

# ============================================================
# 4. 评分
# ============================================================

run_score() {
    local res_json="$1"
    echo ""
    echo "--- Score: ${res_json} ---"
    python -c "
from Sys.Score.Score_N import Scorer, LlmTextParser
s = Scorer('${res_json}')
s.calculate_metrics()
"
}

# run_score "${RES}/skilled_full/res.json"

# ============================================================
# 5. 消融实验矩阵：不同 Skill 组合一次性跑完
# ============================================================

run_ablation_skills() {
    echo ""
    echo "=== 消融实验: Skill 组合矩阵 ==="
    for skills in "1" "1 2" "1 3" "1 2 3"; do
        local tag="skills_$(echo ${skills} | tr ' ' '_')"
        echo "--- 组合: ${tag} ---"
        python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
            -d "${DATA}" -s ${skills} -o "${RES}/ablation_${tag}"
    done
    echo "=== 消融实验完成 ==="
}

# ============================================================
# 6. Naive LLM vs Graph-only vs Full 三组对比
# ============================================================

run_triple_compare() {
    echo ""
    echo "=== 三组对比实验 ==="
    # A) 纯图无向
    python graph_only.py -d "${DATA}" -o "${RES}/triple_graph_undir"
    # B) 纯图有向
    python graph_only.py -d "${DATA}" -o "${RES}/triple_graph_dir" --directed
    # C) 完整方案
    python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
        -d "${DATA}" -s 1 2 3 -o "${RES}/triple_full"
    echo "=== 三组对比完成 ==="
}

# ============================================================
# 按需取消注释执行
# ============================================================

# run_ablation_skills
# run_triple_compare
# run_score "${RES}/ablation_skills_1_2_3/res.json"
```

<｜｜DSML｜｜parameter name="content" string="true">#!/usr/bin/env bash
# ============================================================
# pingmesh RCA 推理脚本示例
# 使用前修改 PROJECT_ROOT 为实际路径
# ============================================================
set -euo pipefail

PROJECT_ROOT="/home/sbp/lixinyang/pingmesh"
DATA="${PROJECT_ROOT}/data/nodes_labeled"
RES="${PROJECT_ROOT}/data/res"

cd "${PROJECT_ROOT}"

# ============================================================
# 1. SkilledAnalyzer — Skill 触发推理（最常用）
# ============================================================

# 全量跑，全部 Skill，默认 NPU=0,1
# python Sys/RootCauseAnalyze/SkilledAnalyzer.py

# 指定数据目录 + 自定义输出目录
# python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
#   -d /home/sbp/lixinyang/pingmesh/data/nodes_labeled \
#   -o /home/sbp/lixinyang/pingmesh/data/res/skilled_test_001

# 仅拓扑 Skill（消融：无 co_occur 无 temporal）
# python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
#   -s 1 -o /home/sbp/lixinyang/pingmesh/data/res/skilled_topo_only

# 4 卡并行（2 实例），全量 Skill
# python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
#   -n 0,1,2,3 -s 1 2 3 -b 16

# 只重跑错案（回归测试）
# python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
#   --failures-from /home/sbp/lixinyang/pingmesh/data/res/skilled_prev/draft_ranking_failures.json


# ============================================================
# 2. SkillNRefineAnalyzer — Skill + Refine 双阶段（最强方案）
# ============================================================

# 8 卡全开，全量 Skill
# python Sys/RootCauseAnalyze/SkillNRefineAnalyzer.py \
#   -d /home/sbp/lixinyang/pingmesh/data/nodes_labeled \
#   -n 0,1,2,3,4,5,6,7 -s 1 2 3

# 仅拓扑 + 时序（消融：无 co_occur）
# python Sys/RootCauseAnalyze/SkillNRefineAnalyzer.py \
#   -s 1 3 -n 0,1,2,3


# ============================================================
# 3. graph_only — 纯图算法消融（不依赖 LLM / NPU）
# ============================================================

# 无向 PageRank
# python graph_only.py

# 有向 PageRank
# python graph_only.py --directed

# 指定数据 + 输出
# python graph_only.py \
#   -d /home/sbp/lixinyang/pingmesh/data/nodes_labeled \
#   -o /home/sbp/lixinyang/pingmesh/data/res/graph_directed \
#   --directed


# ============================================================
# 4. 评分
# ============================================================

# python -c "
# from Sys.Score.Score_N import Scorer, LlmTextParser
# s = Scorer('/home/sbp/lixinyang/pingmesh/data/res/skilled_test_001/res.json')
# s.calculate_metrics()
# "


# ============================================================
# 5. 消融实验矩阵：不同 Skill 组合一次性跑完
# ============================================================

# for skills in "1" "1 2" "1 3" "1 2 3"; do
#   tag=$(echo $skills | tr ' ' '_')
#   python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
#     -d $DATA -s $skills -o $RES/ablation_skills_$tag
# done


# ============================================================
# 6. Naive LLM vs Graph-only vs Full 三组对比
# ============================================================

# python graph_only.py -d $DATA -o $RES/triple_graph_undir
# python graph_only.py -d $DATA -o $RES/triple_graph_dir --directed
# python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
#   -d $DATA -s 1 2 3 -o $RES/triple_full
