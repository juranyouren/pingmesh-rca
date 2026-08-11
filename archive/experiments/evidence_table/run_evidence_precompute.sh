#!/usr/bin/env bash
# 用法（在项目根目录执行）：
#
#   source scripts/common.sh
#   export PINGMESH_DATA=/path/to/nodes_labeled
#   export PINGMESH_SUMMARY_MODEL_PATH=/path/to/local-small-model
#   export PINGMESH_SUMMARY_NPU_CARDS=0,1,2,3  # 每张卡启动一个相同模型副本
#   export PINGMESH_SUMMARY_BATCH_SIZE=8
#   bash scripts/run_evidence_precompute.sh
#
# 默认输出：data/evidence_Table
# 强制重建：PINGMESH_EVIDENCE_OVERWRITE=1 bash scripts/run_evidence_precompute.sh
# 小规模试跑：bash scripts/run_evidence_precompute.sh --limit-cases 2
# 自定义输出：export PINGMESH_EVIDENCE_TABLE_DIR=/path/to/evidence_Table

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"

source "${PROJECT_ROOT}/scripts/common.sh"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
EVIDENCE_OUTPUT_ROOT="${PINGMESH_EVIDENCE_TABLE_DIR:-${PROJECT_ROOT}/data/evidence_Table}"
SUMMARY_CARDS="${PINGMESH_SUMMARY_NPU_CARDS:-0}"
SUMMARY_BATCH_SIZE="${PINGMESH_SUMMARY_BATCH_SIZE:-8}"
SUMMARY_MAX_NUM_SEQS="${PINGMESH_SUMMARY_MAX_NUM_SEQS:-8}"
SUMMARY_MAX_MODEL_LEN="${PINGMESH_SUMMARY_MAX_MODEL_LEN:-4096}"
SUMMARY_MAX_TOKENS="${PINGMESH_SUMMARY_MAX_TOKENS:-512}"

overwrite_args=()
if [[ "${PINGMESH_EVIDENCE_OVERWRITE:-0}" == "1" || "${PINGMESH_EVIDENCE_OVERWRITE:-0}" == "true" ]]; then
  overwrite_args+=(--overwrite)
fi

echo "[evidence] data=${PINGMESH_DATA}"
echo "[evidence] output=${EVIDENCE_OUTPUT_ROOT}"
echo "[evidence] model=${PINGMESH_SUMMARY_MODEL_PATH}"
echo "[evidence] cards=${SUMMARY_CARDS} (one replica per card)"
echo "[evidence] batch=${SUMMARY_BATCH_SIZE}; max_num_seqs=${SUMMARY_MAX_NUM_SEQS}"

"${PYTHON_BIN}" scripts/build_evidence_tables.py \
  --data-root "${PINGMESH_DATA}" \
  --output-root "${EVIDENCE_OUTPUT_ROOT}" \
  --model-path "${PINGMESH_SUMMARY_MODEL_PATH}" \
  --npu-cards "${SUMMARY_CARDS}" \
  --weight-file "${PINGMESH_WEIGHTS_MANUAL}" \
  --batch-size "${SUMMARY_BATCH_SIZE}" \
  --max-num-seqs "${SUMMARY_MAX_NUM_SEQS}" \
  --max-model-len "${SUMMARY_MAX_MODEL_LEN}" \
  --max-tokens "${SUMMARY_MAX_TOKENS}" \
  --kv-cache-gb "${PINGMESH_SUMMARY_KV_CACHE_GB}" \
  --num-gpu-blocks-override "${PINGMESH_SUMMARY_NUM_GPU_BLOCKS}" \
  "${overwrite_args[@]}" \
  "$@"
