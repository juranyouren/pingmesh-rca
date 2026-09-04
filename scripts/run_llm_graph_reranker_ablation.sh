#!/usr/bin/env bash
# Compare local-Qwen evidence/graph/prior listwise root reranking variants.

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
Usage: bash scripts/run_llm_graph_reranker_ablation.sh --stage1-dir PATH [options]

Required:
  --stage1-dir PATH          OOF Stage-1 directory containing res.json

Options:
  --output-dir PATH          Output directory (default: collision-safe run dir)
  --top-k N                  Candidate count (default: 5)
  --model PATH               Local Qwen32B model path
  --npu CARDS                Comma-separated Ascend NPU cards
  --batch-size N             vLLM prompt batch size
  --max-input-tokens N       Prompt budget before structural pruning
  --consistency-passes N     Candidate-order passes for proposed changes
  --save-prompts             Save full prompts for local audit
  --skip-preprocess          Skip raw topology-context verification
  --mock                     Run label-free mock inference without loading vLLM
  -h, --help                 Show this help

The inference stage never reads root labels. After every LLM variant has been
written, the separate evaluator joins labels and writes summary.json/csv.
EOF
}

STAGE1_DIR=""
OUTPUT_DIR=""
TOP_K="${PINGMESH_NEURAL_STAGE2_TOP_K}"
MODEL_PATH="${PINGMESH_MODEL_PATH}"
NPU_CARDS="${PINGMESH_NPU_CARDS}"
BATCH_SIZE="${PINGMESH_BATCH_SIZE}"
MAX_INPUT_TOKENS="${PINGMESH_LLM_RERANK_MAX_INPUT_TOKENS}"
CONSISTENCY_PASSES="${PINGMESH_LLM_RERANK_CONSISTENCY_PASSES}"
SKIP_PREPROCESS=0
SAVE_PROMPTS=0
MOCK=0

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
        --model)
            MODEL_PATH="${2:?--model requires a value}"
            shift 2
            ;;
        --npu)
            NPU_CARDS="${2:?--npu requires a value}"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="${2:?--batch-size requires a value}"
            shift 2
            ;;
        --max-input-tokens)
            MAX_INPUT_TOKENS="${2:?--max-input-tokens requires a value}"
            shift 2
            ;;
        --consistency-passes)
            CONSISTENCY_PASSES="${2:?--consistency-passes requires a value}"
            shift 2
            ;;
        --save-prompts)
            SAVE_PROMPTS=1
            shift
            ;;
        --skip-preprocess)
            SKIP_PREPROCESS=1
            shift
            ;;
        --mock)
            MOCK=1
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

if [[ -z "${OUTPUT_DIR}" ]]; then
    OUTPUT_DIR="$(pingmesh_create_run_dir llm_graph_reranker "$(basename "${STAGE1_DIR}")")"
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

extra_args=()
if [[ "${SAVE_PROMPTS}" == "1" ]]; then
    extra_args+=(--save-prompts)
fi
if [[ "${MOCK}" == "1" ]]; then
    extra_args+=(--mock)
fi

python Sys/RootCauseAnalyze/stage1/llm_graph_reranker_pipeline.py \
    --data-root "${PINGMESH_DATA}" \
    --root-results "${STAGE1_DIR}/res.json" \
    --output-dir "${OUTPUT_DIR}" \
    --model "${MODEL_PATH}" \
    --npu "${NPU_CARDS}" \
    --top-k "${TOP_K}" \
    --batch-size "${BATCH_SIZE}" \
    --temperature "${PINGMESH_LLM_RERANK_TEMPERATURE}" \
    --max-tokens "${PINGMESH_LLM_RERANK_MAX_TOKENS}" \
    --max-model-len "${PINGMESH_MAX_MODEL_LEN}" \
    --max-input-tokens "${MAX_INPUT_TOKENS}" \
    --max-evidence-records "${PINGMESH_LLM_RERANK_MAX_EVIDENCE}" \
    --consistency-passes "${CONSISTENCY_PASSES}" \
    --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
    --max-path-depth "${PINGMESH_PROPAGATION_MAX_PATH_DEPTH}" \
    --edge-probability-method deterministic_evidence_v1 \
    "${extra_args[@]}"

methods=(
    llm_evidence_only
    llm_evidence_graph
    llm_prior_evidence_graph
    llm_prior_evidence_graph_consensus
)
for method in "${methods[@]}"; do
    python Sys/Score/Score_N.py "${OUTPUT_DIR}/${method}/res.json"
done

python Sys/Score/summarize_llm_graph_reranker.py \
    --baseline-res "${STAGE1_DIR}/res.json" \
    --experiment-dir "${OUTPUT_DIR}" \
    --methods "${methods[@]}"

echo "Local-Qwen graph-reranker ablation completed: ${OUTPUT_DIR}"
