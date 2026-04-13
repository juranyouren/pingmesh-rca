#!/bin/bash
set -e 

BASE_DIR="/home/sbp/lixinyang/pingmesh"
DATA_NODES="${BASE_DIR}/data/nodes"
# ORIGINAL_SKILL_PATH="${BASE_DIR}/SkillBank/skills" # 既然是共享库，这行不用在 bash 里显式传参了

RUN_ID=$(date +%s)
WORKSPACE="${BASE_DIR}/data/res/run_${RUN_ID}"
mkdir -p "${WORKSPACE}"

# 定义最大迭代轮数，防止陷入无限死循环
MAX_ROUNDS=10
CURRENT_ROUND=1
# ==========================================
# 日志配置：将所有输出同时打印到屏幕并追加到 log 文件
# ==========================================
LOG_FILE="${WORKSPACE}/pipeline_${RUN_ID}.log"
echo "正在初始化日志系统，日志将保存至: ${LOG_FILE}"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=================================================="
echo "启动 Agentic 闭环诊断流程，RUN_ID: ${RUN_ID}"
echo "工作目录: ${WORKSPACE}"
echo "最大允许迭代轮数: ${MAX_ROUNDS}"
echo "=================================================="

while [ $CURRENT_ROUND -le $MAX_ROUNDS ]; do
    ROUND_DIR="${WORKSPACE}/round${CURRENT_ROUND}"
    mkdir -p "${ROUND_DIR}"
    
    echo ""
    echo ">>>>>>>>>> 开始第 ${CURRENT_ROUND} 轮迭代 <<<<<<<<<<"
    
    # ==========================================
    # 阶段 1：推理 (Inference)
    # ==========================================
    echo "[Phase 1] 开始基于当前技能库进行推理..."
    python /home/sbp/lixinyang/pingmesh/Sys/RootCauseAnalyze/SkilledAnalyzer_bash.py \
        --root_path "${DATA_NODES}" \
        --save_dir "${ROUND_DIR}" 

    # ==========================================
    # 阶段 2：执行打分与失败案例提取 (Score)
    # ==========================================
    echo "[Phase 2] 开始针对本轮推理结果进行打分..."
    python /home/sbp/lixinyang/pingmesh/Sys/Score/Score_bash.py \
        --res_path "${ROUND_DIR}/res.json"

    FAILURES_FILE="${ROUND_DIR}/ranking_failures.json"

    # ==========================================
    # 阻断逻辑：检查是否通过了测试
    # ==========================================
    if [ ! -f "$FAILURES_FILE" ] || [ $(jq length "$FAILURES_FILE") -eq 0 ]; then
        echo "🎉 恭喜！第 ${CURRENT_ROUND} 轮的打分完美，没有产生任何 Failed Cases。"
        echo "🚀 闭环流程圆满结束！最终结果见: ${ROUND_DIR}"
        exit 0
    fi

    echo "发现失败案例，进入反思迭代阶段..."

    # ==========================================
    # 阶段 3：执行反思与新技能生成 (Review)
    # ==========================================
    echo "[Phase 3] 开始对失败案例进行多维度反思与 Skill 提取..."
    python /home/sbp/lixinyang/pingmesh/Sys/CaseReviewer/CaseReviewer_bash.py \
        --failure_cases_path "${FAILURES_FILE}" 

    # ==========================================
    # 阶段 4：注册新技能 (Execute/Merge)
    # ==========================================
    echo "[Phase 4] 将新生成的技能注册到全局 SkillBank 中..."
    # 修复了你原来的变量命名错误！
    # 假设 CaseReviewer 跑完后，把新技能存放在了 failures_file 同级目录下的 skills.json
    NEW_SKILLS_FILE="${ROUND_DIR}/skills.json" 
    
    if [ -f "$NEW_SKILLS_FILE" ]; then
        python /home/sbp/lixinyang/pingmesh/SkillBank/SkillExecutor_bash.py \
            --skills_path "${NEW_SKILLS_FILE}"
        echo "✅ 新技能已成功注入全局技能库！"
    else
        echo "⚠️ 警告：反思阶段未能生成 ${NEW_SKILLS_FILE}，可能是提取失败或没有新逻辑。"
        # 如果没有新技能，继续跑下一轮毫无意义，因为结果会一样，直接 break
        echo "🛑 提前终止迭代。"
        break
    fi

    echo "第 ${CURRENT_ROUND} 轮迭代完成，准备进入下一轮..."
    # 轮数 +1
    CURRENT_ROUND=$((CURRENT_ROUND + 1))
done

if [ $CURRENT_ROUND -gt $MAX_ROUNDS ]; then
    echo "=================================================="
    echo "⚠️ 已达到最大迭代轮数 ($MAX_ROUNDS)，流程自动终止。"
    echo "请检查最后的 failed cases，可能存在 LLM 无法通过增加技能来解决的边界问题。"
    echo "=================================================="
fi