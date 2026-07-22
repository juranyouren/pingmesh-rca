#!/usr/bin/env bash
# 用法（证据表预生成完成后，在项目根目录执行）：
#
#   source scripts/common.sh
#   export PINGMESH_LLM_NPU_GROUPS='0,1;2,3'  # 每组加载一个大模型副本
#   export PINGMESH_ABLATION_MODES='m1 m13 m23 m123'
#   bash scripts/run_ablation_study.sh
#
# 只检查 Gate、重推 case 和 prompt，不启动大模型：
#   bash scripts/run_ablation_study.sh --plan-only
#
# 小规模端到端试跑：
#   RUN_TAG=smoke bash scripts/run_ablation_study.sh --limit-cases 2

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"

source "${PROJECT_ROOT}/scripts/common.sh"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
EVIDENCE_ROOT="${PINGMESH_EVIDENCE_TABLE_DIR:-${PROJECT_ROOT}/data/evidence_Table}"
OUTPUT_ROOT="${PINGMESH_ABLATION_OUTPUT_ROOT:-${PINGMESH_RESULTS}}"
RUN_TAG="${RUN_TAG:-ablation_$(date +%Y%m%d_%H%M%S)}"
read -r -a MODES <<< "${PINGMESH_ABLATION_MODES:-m1 m13 m23 m123}"

if [[ -n "${PINGMESH_LLM_NPU_GROUPS:-}" ]]; then
  LLM_NPU_GROUPS="${PINGMESH_LLM_NPU_GROUPS}"
else
  IFS=',' read -r -a cards <<< "${PINGMESH_NPU_CARDS}"
  groups=()
  for ((i=0; i<${#cards[@]}; i+=2)); do
    if ((i + 1 < ${#cards[@]})); then
      groups+=("${cards[i]},${cards[i+1]}")
    else
      groups+=("${cards[i]}")
    fi
  done
  LLM_NPU_GROUPS="$(IFS=';'; echo "${groups[*]}")"
fi

echo "[ablation] data=${PINGMESH_DATA}"
echo "[ablation] evidence=${EVIDENCE_ROOT}"
echo "[ablation] output=${OUTPUT_ROOT}/${RUN_TAG}"
echo "[ablation] modes=${MODES[*]}"
echo "[ablation] model=${PINGMESH_MODEL_PATH}"
echo "[ablation] npu_groups=${LLM_NPU_GROUPS}"

"${PYTHON_BIN}" scripts/run_ablation_study.py \
  --data-root "${PINGMESH_DATA}" \
  --evidence-root "${EVIDENCE_ROOT}" \
  --output-root "${OUTPUT_ROOT}" \
  --run-tag "${RUN_TAG}" \
  --modes "${MODES[@]}" \
  --top-k "${PINGMESH_TOP_K}" \
  --weight-file "${PINGMESH_WEIGHTS_MANUAL}" \
  --model-path "${PINGMESH_MODEL_PATH}" \
  --npu-groups "${LLM_NPU_GROUPS}" \
  --batch-size "${PINGMESH_BATCH_SIZE}" \
  --max-num-seqs "${PINGMESH_BATCH_SIZE}" \
  --max-model-len "${PINGMESH_MAX_MODEL_LEN}" \
  --max-tokens "${PINGMESH_MAX_TOKENS}" \
  --temperature "${PINGMESH_TEMPERATURE}" \
  "$@"
