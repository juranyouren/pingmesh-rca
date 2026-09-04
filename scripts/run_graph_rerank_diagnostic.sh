#!/usr/bin/env bash
# Diagnose candidate propagation-graph reranking signal without fitting a model.

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
Usage: bash scripts/run_graph_rerank_diagnostic.sh --stage1-dir PATH [options]

Required:
  --stage1-dir PATH         Stage-1 OOF directory containing res.json

Options:
  --output-dir PATH         Diagnostic output directory (default: new run directory)
  --top-k N                 Candidate roots to diagnose (default: 5)
  --edge-method METHOD      deterministic_evidence_v1 or logit_softmax_v1
  --skip-preprocess         Skip raw topology-context verification
  -h, --help                Show this help

This is an exploratory label-based diagnostic, not a trained reranker and not
held-out paper performance. Root labels are used only after all candidate
propagation graphs and label-free reasonableness scores have been constructed.
EOF
}

STAGE1_DIR=""
OUTPUT_DIR=""
TOP_K="${PINGMESH_NEURAL_STAGE2_TOP_K}"
EDGE_METHOD="deterministic_evidence_v1"
SKIP_PREPROCESS=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --stage1-dir)
            STAGE1_DIR="${2:?--stage1-dir requires a value}"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="${2:?--output-dir requires a value}"
            shift 2
            ;;
        --top-k)
            TOP_K="${2:?--top-k requires a value}"
            shift 2
            ;;
        --edge-method)
            EDGE_METHOD="${2:?--edge-method requires a value}"
            shift 2
            ;;
        --skip-preprocess)
            SKIP_PREPROCESS=1
            shift
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

if [[ -z "${STAGE1_DIR}" ]]; then
    echo "[ERROR] --stage1-dir is required." >&2
    usage >&2
    exit 2
fi
STAGE1_DIR="$(cd -- "${STAGE1_DIR}" && pwd)"
if [[ ! -f "${STAGE1_DIR}/res.json" ]]; then
    echo "[ERROR] Missing Stage-1 result: ${STAGE1_DIR}/res.json" >&2
    exit 2
fi

case "${EDGE_METHOD}" in
    deterministic_evidence_v1|logit_softmax_v1) ;;
    *)
        echo "[ERROR] Unsupported --edge-method: ${EDGE_METHOD}" >&2
        exit 2
        ;;
esac

if [[ -z "${OUTPUT_DIR}" ]]; then
    OUTPUT_DIR="$(pingmesh_create_run_dir graph_rerank_diagnostic "$(basename "${STAGE1_DIR}")")"
else
    mkdir -p "${OUTPUT_DIR}"
    OUTPUT_DIR="$(cd -- "${OUTPUT_DIR}" && pwd)"
fi

if [[ "${SKIP_PREPROCESS}" == "0" ]]; then
    python Sys/Preprocess/backfill_topology_context.py \
        --cases-root "${PINGMESH_DATA}" \
        --raw-root "${PINGMESH_RAW_DATA}" \
        --report "${OUTPUT_DIR}/topology_context_backfill_report.json" \
        --write \
        --require-complete
fi

python Sys/Score/diagnose_graph_reranking.py \
    --data-root "${PINGMESH_DATA}" \
    --root-results "${STAGE1_DIR}/res.json" \
    --output-dir "${OUTPUT_DIR}" \
    --top-k "${TOP_K}" \
    --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
    --max-path-depth "${PINGMESH_PROPAGATION_MAX_PATH_DEPTH}" \
    --edge-probability-method "${EDGE_METHOD}"

echo "Graph-rerank signal diagnostic completed: ${OUTPUT_DIR}"
