#!/usr/bin/env bash
set -euo pipefail
PINGMESH_ENCODER_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${PINGMESH_ENCODER_SCRIPT_DIR}/common.sh"
cd "${PINGMESH_PROJECT_ROOT}"
export PINGMESH_MODEL_PATH="${PINGMESH_MODEL_PATH:-/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B}"
python -m Sys.Preprocess.llm_encoder "$@"
