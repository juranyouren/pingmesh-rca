#!/usr/bin/env bash
# ============================================================
# 集中配置 — 所有脚本 source 此文件，config.py 从这里读取
# 环境变量优先，未设置则使用默认值。
#
# 切换数据集:    export PINGMESH_DATA=/new/path
# 切换模型:      export PINGMESH_MODEL_PATH=/new/model
# 切换 NPU:      export PINGMESH_NPU_CARDS=0,1,2,3
# 切换 Skill:    export PINGMESH_SKILLS="1"
# ============================================================

# ── 项目根目录 ──
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-/home/sbp/lixinyang/pingmesh}"

# ── 数据路径 ──
export PINGMESH_DATA="${PINGMESH_DATA:-${PINGMESH_PROJECT_ROOT}/data/node/nodes_labeled}"
export PINGMESH_RESULTS="${PINGMESH_RESULTS:-${PINGMESH_PROJECT_ROOT}/data/res}"

# ── 权重文件 ──
export PINGMESH_WEIGHTS_MANUAL="${PINGMESH_WEIGHTS_MANUAL:-${PINGMESH_PROJECT_ROOT}/data/weights/classified_alarms/all_alarms.json}"
export PINGMESH_WEIGHTS_LLM="${PINGMESH_WEIGHTS_LLM:-${PINGMESH_PROJECT_ROOT}/data/weights/alarm_weights.json}"

# ── 模型 ──
export PINGMESH_MODEL_PATH="${PINGMESH_MODEL_PATH:-/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B}"

# ── NPU / 推理参数 ──
export PINGMESH_NPU_CARDS="${PINGMESH_NPU_CARDS:-0,1}"
export PINGMESH_SKILLS="${PINGMESH_SKILLS:-1 2}"
export PINGMESH_TOP_K="${PINGMESH_TOP_K:-5}"
export PINGMESH_BATCH_SIZE="${PINGMESH_BATCH_SIZE:-8}"
export PINGMESH_TEMPERATURE="${PINGMESH_TEMPERATURE:-0.6}"
export PINGMESH_MAX_TOKENS="${PINGMESH_MAX_TOKENS:-4096}"
export PINGMESH_MAX_MODEL_LEN="${PINGMESH_MAX_MODEL_LEN:-16384}"
