#!/usr/bin/env bash
# Runnable heterogeneous fault-propagation V0.
#
# This pipeline is label-free and does not require an external root-result file.
# It optionally backfills raw task_topo sidecars, constructs Device/Event/Symptom
# graphs, estimates local root/DD/EE potentials, and jointly selects a
# single-device root and a topology-valid propagation DAG.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

usage() {
    cat <<'EOF'
Usage: bash scripts/run_heterogeneous_v0.sh [--workdir PATH]

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
    WORKDIR="$(pingmesh_create_run_dir heterogeneous v0)"
else
    mkdir -p "${WORKDIR}"
fi

echo "============================================"
echo "  Heterogeneous Propagation V0"
echo "  data:             ${PINGMESH_DATA}"
echo "  raw data:         ${PINGMESH_RAW_DATA}"
echo "  results:          ${WORKDIR}"
echo "  candidate nodes:  ${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}"
echo "  root candidates:  ${PINGMESH_HETERO_MAX_ROOT_CANDIDATES}"
echo "  events/device:    ${PINGMESH_HETERO_MAX_EVENTS_PER_DEVICE}"
echo "  event pairs:      ${PINGMESH_HETERO_MAX_EVENT_PAIRS}"
echo "  DD probabilities: ${PINGMESH_HETERO_EDGE_PROBABILITY_METHOD}"
echo "============================================"

if [[ "${PINGMESH_HETERO_BACKFILL_TOPOLOGY}" == "1" ]]; then
    echo
    echo "=== [topology] backfill and verify raw task_topo contexts ==="
    python Sys/Preprocess/backfill_topology_context.py \
        --cases-root "${PINGMESH_DATA}" \
        --raw-root "${PINGMESH_RAW_DATA}" \
        --report "${WORKDIR}/topology_context_backfill_report.json" \
        --write \
        --require-complete
fi

echo
echo "=== [V0] reconstruct heterogeneous root and propagation graphs ==="
python Sys/RootCauseAnalyze/heterogeneous_propagation_pipeline.py \
    --data-root "${PINGMESH_DATA}" \
    --output-dir "${WORKDIR}" \
    --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
    --max-root-candidates "${PINGMESH_HETERO_MAX_ROOT_CANDIDATES}" \
    --max-events-per-device "${PINGMESH_HETERO_MAX_EVENTS_PER_DEVICE}" \
    --max-event-pairs "${PINGMESH_HETERO_MAX_EVENT_PAIRS}" \
    --edge-probability-method "${PINGMESH_HETERO_EDGE_PROBABILITY_METHOD}"

echo
echo "V0 complete."
echo "  summaries: ${WORKDIR}/res.json"
echo "  full graphs: ${WORKDIR}/heterogeneous_graphs.json"
