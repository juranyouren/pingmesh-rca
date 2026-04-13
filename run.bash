#!/bin/bash
set -e 

BASE_DIR="/home/sbp/lixinyang/pingmesh"
DATA_NODES="${BASE_DIR}/data/nodes"

RUN_ID=$(date +%s)
WORKSPACE="${BASE_DIR}/data/res/run_${RUN_ID}"
mkdir -p "${WORKSPACE}"

echo "=================================================="
echo "启动 Agentic 闭环诊断流程，RUN_ID: ${RUN_ID}"
echo "工作目录: ${WORKSPACE}"
echo "=================================================="

# ==========================================
# 阶段 1：初次推理 (Round 1)
# ==========================================
ROUND1_DIR="${WORKSPACE}/round1"
echo "[Phase 1] 开始初次推理..."
python /home/sbp/lixinyang/pingmesh/Sys/RootCauseAnalyze/SkilledAnalyzer_bash.py \
    --root_path "${DATA_NODES}" \
    --save_dir "${ROUND1_DIR}" 

# ==========================================
# 阶段 2：执行打分与失败案例提取 (Score)
# ==========================================
echo "[Phase 2] 开始针对初次推理结果进行打分..."
python /home/sbp/lixinyang/pingmesh/Sys/Score/Score_bash.py \
    --res_path "${ROUND1_DIR}/res.json"

FAILURES_FILE="${ROUND1_DIR}/ranking_failures.json"

# 阻断逻辑：检查是否生成了失败案例文件，并且文件不为空/数组长度大于0
if [ ! -f "$FAILURES_FILE" ] || [ $(jq length "$FAILURES_FILE") -eq 0 ]; then
    echo "🎉 恭喜！当前模型的打分完美，没有产生任何 Failed Cases。流程结束。"
    exit 0
fi

echo "发现失败案例，进入反思迭代阶段..."

# ==========================================
# 阶段 3：执行反思与新技能生成 (Review)
# ==========================================
echo "[Phase 3] 开始对失败案例进行多维度反思与 Skill 提取..."
# 确保你的 review.py 内部也将结果保存到了传参指定的目录
python /home/sbp/lixinyang/pingmesh/Sys/CaseReviewer/CaseReviewer_bash.py \
    --failure_cases_path "${FAILURES_FILE}" 

# ==========================================
# 阶段 4：合并新老技能库 (Merge)
# ==========================================

FAILURES_FILE="${ROUND1_DIR}/skills.json"
python /home/sbp/lixinyang/pingmesh/SkillBank/SkillExecutor_bash.py \
    --skills_path "${SKILL_FILE}" 

