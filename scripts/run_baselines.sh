#!/usr/bin/env bash
# ============================================================
# 基线方法对比实验 — TraceRCA / NetEventCause / BiAn
# 配置来自 scripts/common.sh
#
# 用法:
#   ./scripts/run_baselines.sh
#   PINGMESH_DATA=/path/to/data ./scripts/run_baselines.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
WORKDIR="${PINGMESH_RESULTS}/baselines_${TIMESTAMP}"
mkdir -p "${WORKDIR}"

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
m = s.calculate_metrics()['skill_evaluation']['ranking_metrics']
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
m = s.calculate_metrics()['skill_evaluation']['ranking_metrics']
print(f'  NetEventCause: Top-1={m[\"Top-1 Acc (%)\"]}  Top-3={m[\"Top-3 Acc (%)\"]}  Top-5={m[\"Top-5 Acc (%)\"]}')
" 2>&1
else
    echo "  [WARN] NetEventCause res.json 未找到，请检查输出"
fi

# ── BiAn (纯 LLM 框架, 需要 NPU) ──
echo ""
echo "--- BiAn ---"
bian_log="$(python Baseline/BiAn/BiAnalyzer.py "${PINGMESH_DATA}" "${PINGMESH_NPU_CARDS}")"
printf '%s\n' "${bian_log}" | tail -5
bian_dir="$(printf '%s\n' "${bian_log}" | awk '/^Saved to /{sub(/^Saved to /,""); print}' | tail -1)"
bian_res="${bian_dir}/res.json"
bian_out="${WORKDIR}/bian"
if [ -f "${bian_res}" ]; then
    cp -r "$(dirname "${bian_res}")" "${bian_out}" 2>/dev/null || true
    python -c "
from Sys.Score.Score_N import Scorer
s = Scorer('${bian_res}')
m = s.calculate_metrics()['skill_evaluation']['ranking_metrics']
print(f'  BiAn: Top-1={m[\"Top-1 Acc (%)\"]}  Top-3={m[\"Top-3 Acc (%)\"]}  Top-5={m[\"Top-5 Acc (%)\"]}')
" 2>&1
else
    echo "  [WARN] BiAn res.json 未找到，请检查输出"
fi

echo ""
echo "============================================"
echo "  基线对比完成"
echo "  结果: ${WORKDIR}/"
echo ""
echo "  消融基线 (当前方案):"
echo "  topo+temporal = 76.10% Top-1 (159 例)"
echo "============================================"
