#!/usr/bin/env bash
# ============================================================
# 端到端 LLM 证据实验: 证据编码 -> 锚点先验 -> 传播重建 -> 指标。
#
# 与 run_full_experiment.sh --evidence-dir 的区别: 这里在同一个进程内
# 完成编码与重建，并可用 --compare-rules 让同一批 case 走规则编码做对照。
#
# Usage:
#   bash scripts/run_llm_encoder_full.sh
#   bash scripts/run_llm_encoder_full.sh --compare-rules
#   bash scripts/run_llm_encoder_full.sh --output "${PINGMESH_RESULTS}/my_run"
#   bash scripts/run_llm_encoder_full.sh --help
#
# 需要服务器 NPU 环境；本地无法运行 (无数据、无 NPU 卡)。
# 输出: ${PINGMESH_RESULTS}/llm_encoder_full_<YYYYMMDD_HHMMSS>_<git-short-sha>/
# ============================================================
set -euo pipefail
PINGMESH_ENCODER_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-$(cd -- "${PINGMESH_ENCODER_SCRIPT_DIR}/.." && pwd)}"
source "${PINGMESH_ENCODER_SCRIPT_DIR}/common.sh"
cd "${PINGMESH_PROJECT_ROOT}"
export PYTHONIOENCODING=utf-8

# Pass --output explicitly for a stable location; otherwise create a timestamped
# run directory through the shared helper so every entrypoint names runs alike.
PINGMESH_ENCODER_HAS_OUTPUT=0
for arg in "$@"; do
    case "${arg}" in --output|--output=*) PINGMESH_ENCODER_HAS_OUTPUT=1 ;; esac
done
if [[ "${PINGMESH_ENCODER_HAS_OUTPUT}" == "0" ]]; then
    set -- --output "$(pingmesh_create_run_dir llm_encoder_full)" "$@"
fi

exec "${PYTHON}" -u -m Sys.Score.llm_encoder_experiment "$@"
