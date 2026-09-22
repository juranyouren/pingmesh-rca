#!/usr/bin/env bash
# ============================================================
# 数据预处理贯通脚本: raw topology sidecar 回填 + 结构等价映射。
#
# 这两步是传播图重建的前置依赖:
#   - topology_context.json  (raw task_topo sidecar, 标签无关/方向无关)
#   - topology_equivalence.json (无证据结构孪生商图)
#
# Usage:
#   bash scripts/run_preprocess.sh
#   bash scripts/run_preprocess.sh --dry-run
#   PINGMESH_DATA=/new/path bash scripts/run_preprocess.sh
#
# 输出: ${PINGMESH_RESULTS}/preprocess_<YYYYMMDD_HHMMSS>_<git-short-sha>/
#
# 说明: 本脚本只做 dry-run 检查需要可加 --dry-run；默认写入 sidecar。
#       run_full_experiment.sh 的 preprocess 阶段执行同样的两步。
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

usage() { sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

DRY_RUN=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "[ERROR] Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

for required in "${PINGMESH_DATA}" "${PINGMESH_RAW_DATA}"; do
    if [[ ! -d "${required}" ]]; then
        echo "[ERROR] Required directory is missing: ${required}" >&2
        exit 2
    fi
done

if [[ "${DRY_RUN}" == "1" ]]; then
    WORKDIR="$(pingmesh_preview_run_dir preprocess)"
else
    WORKDIR="$(pingmesh_create_run_dir preprocess)"
fi

echo "workdir: ${WORKDIR}"
if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[DRY-RUN] would write:"
    echo "  ${WORKDIR}/topology_context_backfill_report.json"
    echo "  ${WORKDIR}/topology_equivalence_report.json"
    exit 0
fi

"${PYTHON}" Sys/Preprocess/backfill_topology_context.py \
    --cases-root "${PINGMESH_DATA}" \
    --raw-root "${PINGMESH_RAW_DATA}" \
    --report "${WORKDIR}/topology_context_backfill_report.json" \
    --write \
    --require-complete

"${PYTHON}" Sys/Preprocess/build_structural_equivalence.py \
    --cases-root "${PINGMESH_DATA}" \
    --report "${WORKDIR}/topology_equivalence_report.json" \
    --write \
    --require-raw-topology

echo
echo "Preprocessing completed: ${WORKDIR}"
