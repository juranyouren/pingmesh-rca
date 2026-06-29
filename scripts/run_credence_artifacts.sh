#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

RUN_ID="${CREDENCE_RUN_ID:-credence_$(date +%Y%m%d_%H%M%S)}"
ALWAYS_LLM_OUT="${CREDENCE_ALWAYS_LLM_OUT:-${RUN_ID}_always_llm}"
GATED_OUT="${CREDENCE_GATED_OUT:-${RUN_ID}_gated}"
CREDENCE_OUT="${CREDENCE_OUT:-${PINGMESH_RESULTS}/credence/${RUN_ID}}"
SKILLS="${1:-${PINGMESH_SKILLS}}"
NPU="${2:-${PINGMESH_NPU_CARDS}}"
BATCH="${3:-${PINGMESH_BATCH_SIZE}}"
TOPK="${4:-${PINGMESH_TOP_K}}"
RISK_BUDGET="${CREDENCE_RISK_BUDGET:-0.10}"
DELTA="${CREDENCE_DELTA:-0.05}"

mkdir -p "${CREDENCE_OUT}/manifest"

echo "============================================"
echo "  CREDENCE artifact pipeline"
echo "  data:      ${PINGMESH_DATA}"
echo "  results:   ${PINGMESH_RESULTS}"
echo "  run id:    ${RUN_ID}"
echo "  out:       ${CREDENCE_OUT}"
echo "  skills:    ${SKILLS}"
echo "============================================"

git rev-parse HEAD > "${CREDENCE_OUT}/manifest/git_commit.txt" 2>/dev/null || true
find "${PINGMESH_DATA}" -type f | sort | sha256sum > "${CREDENCE_OUT}/manifest/data_file_list.sha256" || true
if [ -f "${PINGMESH_WEIGHTS_MANUAL}" ]; then
    sha256sum "${PINGMESH_WEIGHTS_MANUAL}" > "${CREDENCE_OUT}/manifest/weights.sha256"
else
    : > "${CREDENCE_OUT}/manifest/weights.sha256"
fi
python - <<'PY' > "${CREDENCE_OUT}/manifest/env.txt"
import platform, sys
print("python", sys.version.replace("\n", " "))
print("platform", platform.platform())
PY

echo ""
echo "[1/6] Run always-LLM inference for rescue/harm measurement"
PINGMESH_CONFIDENCE_GATE=0 ./scripts/run_inference.sh "${ALWAYS_LLM_OUT}" "${SKILLS}" "${NPU}" "${BATCH}" "${TOPK}"

ALWAYS_LLM_RES_JSON="${PINGMESH_RESULTS}/${ALWAYS_LLM_OUT}/res.json"
if [ ! -s "${ALWAYS_LLM_RES_JSON}" ]; then
    echo "missing always-LLM res.json: ${ALWAYS_LLM_RES_JSON}" >&2
    exit 2
fi

echo ""
echo "[2/6] Run confidence-gated inference for gate features and routed decisions"
PINGMESH_CONFIDENCE_GATE=1 ./scripts/run_inference.sh "${GATED_OUT}" "${SKILLS}" "${NPU}" "${BATCH}" "${TOPK}"

GATED_RES_JSON="${PINGMESH_RESULTS}/${GATED_OUT}/res.json"
if [ ! -s "${GATED_RES_JSON}" ]; then
    echo "missing gated res.json: ${GATED_RES_JSON}" >&2
    exit 2
fi

echo ""
echo "[3/6] Export confidence cases"
python Sys/Score/export_confidence_cases.py \
    --res "${GATED_RES_JSON}" \
    --llm-res "${ALWAYS_LLM_RES_JSON}" \
    --out "${CREDENCE_OUT}/confidence_cases.jsonl" \
    --summary "${CREDENCE_OUT}/confidence_extraction_summary.json" \
    --manifest "${CREDENCE_OUT}/confidence_manifest.json" \
    --data-version "${RUN_ID}"

echo ""
echo "[4/6] Calibrate confidence"
python Sys/Score/calibrate_confidence.py \
    --cases "${CREDENCE_OUT}/confidence_cases.jsonl" \
    --out-dir "${CREDENCE_OUT}" \
    --risk-budget "${RISK_BUDGET}" \
    --delta "${DELTA}"

echo ""
echo "[5/6] Evaluate LLM value"
python Sys/Score/evaluate_llm_value.py \
    --cases "${CREDENCE_OUT}/confidence_cases.jsonl" \
    --calibration "${CREDENCE_OUT}/confidence_calibration.json" \
    --out "${CREDENCE_OUT}/llm_value.csv"

echo ""
echo "[6/6] Evaluate diagnosability"
python Sys/Score/evaluate_diagnosability.py \
    --cases "${CREDENCE_OUT}/confidence_cases.jsonl" \
    --out "${CREDENCE_OUT}/diagnosability_frontier.csv"

echo ""
echo "CREDENCE artifacts written to: ${CREDENCE_OUT}"
