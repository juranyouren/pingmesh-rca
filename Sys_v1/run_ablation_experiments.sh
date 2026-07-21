#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"

# Reuse the repository's server paths and model defaults. Every important
# experiment parameter below can still be overridden through the environment.
source "${PROJECT_ROOT}/scripts/common.sh"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
RUN_TAG="${RUN_TAG:-sys_v1_$(date +%Y%m%d_%H%M%S)}"
TOP_K="${SYS_V1_TOP_K:-10}"
BATCH_SIZE="${SYS_V1_BATCH_SIZE:-4}"
MAIN_NPU_CARDS="${SYS_V1_MAIN_NPU_CARDS:-4,5}"
M1_NPU_CARD="${SYS_V1_M1_NPU_CARD:-${MAIN_NPU_CARDS%%,*}}"
SUMMARY_NPU_CARD="${SYS_V1_SUMMARY_NPU_CARD:-0}"
SUMMARY_MAX_TOKENS="${SYS_V1_SUMMARY_MAX_TOKENS:-1024}"
NEIGHBOR_ALARM_MODE="${SYS_V1_NEIGHBOR_ALARM_MODE:-highest_weight}"
MAX_NEIGHBOR_DEVICES="${SYS_V1_MAX_NEIGHBOR_DEVICES:-8}"
MAX_NEIGHBOR_ALARMS="${SYS_V1_MAX_NEIGHBOR_ALARMS:-3}"
SUMMARY_CONTEXT_MAX_CHARS="${SYS_V1_SUMMARY_CONTEXT_MAX_CHARS:-3500}"

if (($# == 0)); then
  MODES=(m1 m1_m3 m2_m3 m123)
else
  MODES=("$@")
fi

for mode in "${MODES[@]}"; do
  case "${mode}" in
    m1|m1_m3|m2_m3|m123) ;;
    *)
      echo "Unsupported ablation mode: ${mode}" >&2
      echo "Choose from: m1 m1_m3 m2_m3 m123" >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "${PINGMESH_DATA}" ]]; then
  echo "PINGMESH_DATA does not exist: ${PINGMESH_DATA}" >&2
  exit 2
fi
if [[ ! -f "${PINGMESH_WEIGHTS_MANUAL}" ]]; then
  echo "Alarm weight file does not exist: ${PINGMESH_WEIGHTS_MANUAL}" >&2
  exit 2
fi

needs_main_llm=0
needs_summary_model=0
for mode in "${MODES[@]}"; do
  [[ "${mode}" != "m1" ]] && needs_main_llm=1
  [[ "${mode}" == "m2_m3" || "${mode}" == "m123" ]] && needs_summary_model=1
done

if ((needs_main_llm)) && [[ "${MAIN_NPU_CARDS}" != *,* ]]; then
  echo "M3 LLM experiments require at least two main-model NPU cards." >&2
  echo "Set SYS_V1_MAIN_NPU_CARDS, for example: 4,5" >&2
  exit 2
fi
if ((needs_summary_model)); then
  if [[ -z "${PINGMESH_SUMMARY_MODEL_PATH:-}" ]]; then
    echo "PINGMESH_SUMMARY_MODEL_PATH is required for M2 experiments." >&2
    exit 2
  fi
  case ",${MAIN_NPU_CARDS}," in
    *",${SUMMARY_NPU_CARD},"*)
      echo "Summary NPU ${SUMMARY_NPU_CARD} overlaps main-model cards ${MAIN_NPU_CARDS}." >&2
      exit 2
      ;;
  esac
fi

# Sys/common.sh defines the historical summary cache by default. Sys_v1 uses a
# different evidence and prompt version, so run the new neighbor-aware summary
# model live instead of silently falling back to an incompatible old cache.
unset PINGMESH_SUMMARY_CACHE_DIR

COMMON_ARGS=(
  --data-root "${PINGMESH_DATA}"
  --top-k "${TOP_K}"
  --batch-size "${BATCH_SIZE}"
)

SUMMARY_ARGS=(
  --summarize-nodes
  --summary-model-path "${PINGMESH_SUMMARY_MODEL_PATH:-}"
  --summary-npu-cards "${SUMMARY_NPU_CARD}"
  --summary-max-tokens "${SUMMARY_MAX_TOKENS}"
  --neighbor-alarm-mode "${NEIGHBOR_ALARM_MODE}"
  --max-neighbor-devices "${MAX_NEIGHBOR_DEVICES}"
  --max-neighbor-alarms "${MAX_NEIGHBOR_ALARMS}"
  --summary-context-max-chars "${SUMMARY_CONTEXT_MAX_CHARS}"
)

echo "[Sys_v1] run_tag=${RUN_TAG}"
echo "[Sys_v1] modes=${MODES[*]}"
echo "[Sys_v1] data=${PINGMESH_DATA}"
echo "[Sys_v1] results=${PINGMESH_RESULTS}"
echo "[Sys_v1] main_npus=${MAIN_NPU_CARDS}; summary_npu=${SUMMARY_NPU_CARD}"

for mode in "${MODES[@]}"; do
  output_dir="${RUN_TAG}_${mode}"
  npu_cards="${MAIN_NPU_CARDS}"
  extra_args=()

  if [[ "${mode}" == "m1" ]]; then
    npu_cards="${M1_NPU_CARD}"
  elif [[ "${mode}" == "m2_m3" || "${mode}" == "m123" ]]; then
    extra_args=("${SUMMARY_ARGS[@]}")
  fi

  echo
  echo "[Sys_v1] running ${mode} -> ${PINGMESH_RESULTS}/${output_dir}"
  "${PYTHON_BIN}" Sys_v1/RootCauseAnalyze/SkilledAnalyzer.py \
    "${COMMON_ARGS[@]}" \
    "${extra_args[@]}" \
    --ablation "${mode}" \
    --npu-cards "${npu_cards}" \
    --output-dir "${output_dir}"

  result_json="${PINGMESH_RESULTS}/${output_dir}/res.json"
  if [[ "${SYS_V1_SKIP_SCORE:-0}" != "1" ]]; then
    if [[ ! -f "${result_json}" ]]; then
      echo "Expected result file was not produced: ${result_json}" >&2
      exit 1
    fi
    echo "[Sys_v1] scoring ${mode}"
    "${PYTHON_BIN}" Sys_v1/Score/Score_N.py "${result_json}"
  fi
done

echo
echo "[Sys_v1] all requested experiments completed: ${MODES[*]}"
echo "[Sys_v1] result prefix: ${PINGMESH_RESULTS}/${RUN_TAG}_*"
