#!/usr/bin/env bash
# ============================================================
# 集中配置 — 所有脚本 source 此文件
# 环境变量优先，未设置则使用默认值。
#
# 切换数据集只需: export PINGMESH_DATA=/new/path
# 或在调用时: PINGMESH_DATA=/new/path ./scripts/run_inference.sh
# ============================================================

# ── 项目根目录 ──
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-/home/sbp/lixinyang/pingmesh}"

# ── 数据路径 ──
# raw:  原始数据 (data/raw/pingmesh_xxx)
# node: 预处理后的标注数据 (data/node/node_xxx)
export PINGMESH_DATA="${PINGMESH_DATA:-${PINGMESH_PROJECT_ROOT}/data/node/nodes_labeled}"
export PINGMESH_RESULTS="${PINGMESH_RESULTS:-${PINGMESH_PROJECT_ROOT}/data/res}"

# ── 权重文件 ──
export PINGMESH_WEIGHTS_MANUAL="${PINGMESH_WEIGHTS_MANUAL:-${PINGMESH_PROJECT_ROOT}/data/weights/classified_alarms/all_alarms.json}"
export PINGMESH_WEIGHTS_LLM="${PINGMESH_WEIGHTS_LLM:-${PINGMESH_PROJECT_ROOT}/data/weights/alarm_weights.json}"

# ── NPU & 推理参数 ──
export PINGMESH_NPU_CARDS="${PINGMESH_NPU_CARDS:-0,1}"
export PINGMESH_SKILLS="${PINGMESH_SKILLS:-1 2}"
export PINGMESH_TOP_K="${PINGMESH_TOP_K:-5}"
export PINGMESH_BATCH_SIZE="${PINGMESH_BATCH_SIZE:-8}"
