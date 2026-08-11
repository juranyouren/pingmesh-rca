#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source scripts/common.sh

DATA_ROOT="${1:-${PINGMESH_DATA}}"
OUTPUT_DIR="${2:-}"

ARGS=("${DATA_ROOT}" --model "${PINGMESH_MODEL_PATH}" --npu "${PINGMESH_NPU_CARDS}" \
  --temperature "${PINGMESH_TEMPERATURE}" --max-tokens "${PINGMESH_MAX_TOKENS}" \
  --max-model-len "${PINGMESH_MAX_MODEL_LEN}")

if [[ -n "${OUTPUT_DIR}" ]]; then
  ARGS+=(--output-dir "${OUTPUT_DIR}")
fi

python Baseline/BiAn/bian_pipe1.py "${ARGS[@]}"
