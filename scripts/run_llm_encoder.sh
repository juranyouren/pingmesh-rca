#!/usr/bin/env bash
# ============================================================
# LLM evidence encoder: 把异构告警/日志文本编码为规范化证据谓词。
#
# 它是证据编码器，不是边预测器: 只输出 evidence predicate / entity /
# time-quality，传播边由传播重建阶段决定。
#
# Usage:
#   bash scripts/run_llm_encoder.sh --data "${PINGMESH_DATA}" --output "${PINGMESH_RESULTS}/llm_encoder_run"
#   bash scripts/run_llm_encoder.sh --help
#
#   # 切换模型 (默认 32B，见 scripts/common.sh)
#   PINGMESH_MODEL_PATH=/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-7B \
#       bash scripts/run_llm_encoder.sh --data ... --output ...
#
# 需要服务器 NPU 环境 (vLLM + CANN)；本地无法运行。
# 输出目录随后可传给: bash scripts/run_full_experiment.sh --evidence-dir <output>
# ============================================================
set -euo pipefail
PINGMESH_ENCODER_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-$(cd -- "${PINGMESH_ENCODER_SCRIPT_DIR}/.." && pwd)}"
source "${PINGMESH_ENCODER_SCRIPT_DIR}/common.sh"
cd "${PINGMESH_PROJECT_ROOT}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
exec "${PYTHON}" -m Sys.Preprocess.llm_encoder "$@"
