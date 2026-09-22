#!/usr/bin/env bash
# ============================================================
# RQ1: 设备传播图恢复实验 (当前唯一在用的 baseline experiment runner)。
#
# Usage:
#   bash scripts/run_rq1.sh                     # 等价于 python -m Baseline.RQ1 run
#   bash scripts/run_rq1.sh evaluate
#   bash scripts/run_rq1.sh --check-inputs      # 只读检查，不读 GT/不写实验目录
#   bash scripts/run_rq1.sh --dry-run           # 严格预检 (需要 GT)
#
#   # PCMCI 采集覆盖口径 (record-count 是计数假设，不是覆盖证明)
#   PINGMESH_RQ1_PCMCI_COVERAGE=record-count bash scripts/run_rq1.sh
#   # 标签口径 (strict 把 possible 边留给人工确认)
#   PINGMESH_RQ1_LABEL_POLICY=strict bash scripts/run_rq1.sh
#
# 数据集/GT/输出/方法参数默认值全部来自 scripts/common.sh，无需手工传参。
# 输出: ${PINGMESH_RESULTS}/rq1_<condition>_<YYYYMMDD_HHMMSS>_<git-short-sha>/
# ============================================================
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
cd "${PINGMESH_PROJECT_ROOT}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
if [[ "${1:-}" == "run" || "${1:-}" == "evaluate" ]]; then
    COMMAND="$1"
    shift
else
    COMMAND=run
fi
exec "${PYTHON}" -m Baseline.RQ1 "${COMMAND}" "$@"
