#!/usr/bin/env bash
# ============================================================
# 根因定位基线方法对比实验 — TraceRCA / NetEventCause / BiAn
# 配置来自 scripts/common.sh
#
# 用法:
#   ./scripts/run_rca_baselines.sh
#   PINGMESH_DATA=/path/to/data ./scripts/run_rca_baselines.sh
# ============================================================
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

usage() {
    cat <<'EOF'
Usage: bash scripts/run_rca_baselines.sh [--workdir PATH]

Without --workdir, a collision-safe run ID is generated automatically.
EOF
}

WORKDIR=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --workdir)
            WORKDIR="${2:?--workdir requires a path}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "[ERROR] Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done
if [[ -z "${WORKDIR}" ]]; then
    WORKDIR="$(pingmesh_create_run_dir rca baselines)"
else
    mkdir -p "${WORKDIR}"
fi

echo "============================================"
echo "  基线对比实验"
echo "  数据: ${PINGMESH_DATA}"
echo "  结果: ${WORKDIR}"
echo "============================================"

# ── TraceRCA (纯统计, 不依赖 NPU) ──
echo ""
echo "--- TraceRCA ---"
tracerca_log="$(python Baseline/TraceRCA/TraceRCAnalyzer.py "${PINGMESH_DATA}")"
printf '%s\n' "${tracerca_log}" | tail -5
tracerca_dir="$(printf '%s\n' "${tracerca_log}" | awk '/^Saved to /{sub(/^Saved to /,""); print}' | tail -1)"
tracerca_res="${tracerca_dir}/res.json"
tracerca_out="${WORKDIR}/tracerca"
if [ -f "${tracerca_res}" ]; then
    cp -r "$(dirname "${tracerca_res}")" "${tracerca_out}" 2>/dev/null || true
    python -c "
from Sys.Score.Score_N import Scorer
s = Scorer('${tracerca_res}')
m = s.calculate_metrics()['ranking_evaluation']['ranking_metrics']
print(f'  TraceRCA: Top-1={m[\"Top-1 Acc (%)\"]}  Top-3={m[\"Top-3 Acc (%)\"]}  Top-5={m[\"Top-5 Acc (%)\"]}')
" 2>&1
else
    echo "  [WARN] TraceRCA res.json 未找到，请检查输出"
fi

# ── NetEventCause (无拓扑时序, 不依赖 NPU) ──
echo ""
echo "--- NetEventCause ---"
nec_log="$(python Baseline/NetEventCause/NECAnalyzer.py "${PINGMESH_DATA}")"
printf '%s\n' "${nec_log}" | tail -5
nec_dir="$(printf '%s\n' "${nec_log}" | awk '/^Saved to /{sub(/^Saved to /,""); print}' | tail -1)"
nec_res="${nec_dir}/res.json"
nec_out="${WORKDIR}/neteventcause"
if [ -f "${nec_res}" ]; then
    cp -r "$(dirname "${nec_res}")" "${nec_out}" 2>/dev/null || true
    python -c "
from Sys.Score.Score_N import Scorer
s = Scorer('${nec_res}')
m = s.calculate_metrics()['ranking_evaluation']['ranking_metrics']
print(f'  NetEventCause: Top-1={m[\"Top-1 Acc (%)\"]}  Top-3={m[\"Top-3 Acc (%)\"]}  Top-5={m[\"Top-5 Acc (%)\"]}')
" 2>&1
else
    echo "  [WARN] NetEventCause res.json 未找到，请检查输出"
fi

# ── BiAn Pipeline1 (32B local LLM, requires NPU) ──
echo ""
echo "--- BiAn Pipeline1 ---"
bian_out="${WORKDIR}/bian_pipe1"
python Baseline/BiAn/bian_pipe1.py "${PINGMESH_DATA}" \
    --output-dir "${bian_out}" \
    --model "${PINGMESH_MODEL_PATH}" \
    --npu "${PINGMESH_NPU_CARDS}" \
    --temperature "${PINGMESH_TEMPERATURE}" \
    --max-tokens "${PINGMESH_MAX_TOKENS}" \
    --max-model-len "${PINGMESH_MAX_MODEL_LEN}"
python Sys/Score/Score_N.py "${bian_out}/res.json"

echo ""
echo "============================================"
echo "  基线对比完成"
echo "  结果: ${WORKDIR}/"
echo "============================================"
