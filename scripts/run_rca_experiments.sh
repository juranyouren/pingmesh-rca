#!/usr/bin/env bash
# Unified RCA experiment runner.
#
# The only supported flow is deterministic ranking followed by offline gate
# selection, safety verification, and optional local-LLM review.

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
Usage: ./scripts/run_rca_experiments.sh [result-prefix]

Experiments are selected with PINGMESH_EXPERIMENTS:
  pipe            deterministic topology + temporal ranking
  gate_auto       search, apply, and assert a safe gate policy
  pipe_llm        run the local LLM for every case
  gate_llm        run the local LLM only when selected by the gate
  cache_llm       run every case with cached node summaries
  gate_cache_llm  combine the selected gate and cached summaries

Default: pipe gate_auto pipe_llm gate_llm
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    usage
    exit 0
fi

RUN_EXPERIMENTS="${PINGMESH_EXPERIMENTS:-pipe gate_auto pipe_llm gate_llm}"
for experiment in ${RUN_EXPERIMENTS}; do
    case "${experiment}" in
        pipe|gate_auto|pipe_llm|gate_llm|cache_llm|gate_cache_llm) ;;
        *)
            echo "[ERROR] Unsupported experiment: ${experiment}" >&2
            usage >&2
            exit 2
            ;;
    esac
done

has_experiment() {
    local target="$1"
    for experiment in ${RUN_EXPERIMENTS}; do
        if [ "${experiment}" = "${target}" ]; then
            return 0
        fi
    done
    return 1
}

PREFIX="${1:-rca_experiments}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_TAG="${PREFIX}_${TIMESTAMP}"
WORKDIR="${PINGMESH_RESULTS}/${RUN_TAG}"
SKILLS="${PINGMESH_SKILLS:-1 2}"
TOPK="${PINGMESH_TOP_K:-5}"
BATCH="${PINGMESH_BATCH_SIZE:-8}"
NPU="${PINGMESH_NPU_CARDS:-0}"
WEIGHT_FILE="${PINGMESH_WEIGHTS_MANUAL}"
SUMMARY_CACHE_DIR="${PINGMESH_SUMMARY_CACHE_DIR:-}"
GATE_POLICY_CONFIG="${PINGMESH_GATE_POLICY_CONFIG:-}"
DEBUG_ARGS=()

if [ "${PINGMESH_PRINT_FIRST_PROMPT:-0}" = "1" ] || [ "${PINGMESH_PRINT_FIRST_PROMPT:-0}" = "true" ]; then
    DEBUG_ARGS+=(--print-first-prompt)
fi

if (has_experiment cache_llm || has_experiment gate_cache_llm) && [ -z "${SUMMARY_CACHE_DIR}" ]; then
    echo "[ERROR] Cached-summary experiments require PINGMESH_SUMMARY_CACHE_DIR." >&2
    exit 2
fi

if (has_experiment gate_llm || has_experiment gate_cache_llm) \
    && ! has_experiment gate_auto \
    && [ -z "${GATE_POLICY_CONFIG}" ]; then
    echo "[ERROR] Gated LLM experiments require gate_auto or PINGMESH_GATE_POLICY_CONFIG." >&2
    exit 2
fi

mkdir -p "${WORKDIR}"

score_result() {
    local result_json="$1"
    python Sys/Score/Score_N.py "${result_json}"
}

echo "============================================"
echo "  RCA experiments"
echo "  data:        ${PINGMESH_DATA}"
echo "  results:     ${WORKDIR}"
echo "  experiments: ${RUN_EXPERIMENTS}"
echo "  skills:      ${SKILLS}"
echo "  top_k:       ${TOPK}"
echo "  npu:         ${NPU}"
echo "============================================"

PIPE_DIR="${WORKDIR}/pipe"
PIPE_RES="${PIPE_DIR}/res.json"
if has_experiment pipe || has_experiment gate_auto; then
    echo
    echo "=== [pipe] deterministic topology + temporal ranking ==="
    python Sys/RootCauseAnalyze/skill_pipeline.py \
        --data-root "${PINGMESH_DATA}" \
        --skills ${SKILLS} \
        --top-k "${TOPK}" \
        --weight-file "${WEIGHT_FILE}" \
        --output-dir "${RUN_TAG}/pipe"
    score_result "${PIPE_RES}"
fi

if has_experiment gate_auto; then
    echo
    echo "=== [gate_auto] select the safest useful policy ==="
    GATE_SEARCH_DIR="${WORKDIR}/gate_search"
    GATE_TARGET_K="${PINGMESH_GATE_RECALL_K:-1}"
    GATE_SEARCH_ARGS=(
        --res "${PIPE_RES}"
        --out-dir "${GATE_SEARCH_DIR}"
        --target-k "${GATE_TARGET_K}"
        --folds "${PINGMESH_GATE_FOLDS:-5}"
        --min-error-recall "${PINGMESH_GATE_MIN_ERROR_RECALL:-1.0}"
        --max-unsafe-bypass "${PINGMESH_GATE_MAX_UNSAFE_BYPASS:-0}"
    )
    if [ -n "${PINGMESH_GATE_BADCASES:-}" ]; then
        GATE_SEARCH_ARGS+=(--badcases "${PINGMESH_GATE_BADCASES}")
    fi
    if [ "${PINGMESH_GATE_NAMED_ONLY:-0}" = "1" ] || [ "${PINGMESH_GATE_NAMED_ONLY:-0}" = "true" ]; then
        GATE_SEARCH_ARGS+=(--named-only)
    fi
    python Sys/Score/search_gate_policy.py "${GATE_SEARCH_ARGS[@]}"

    GATE_POLICY_CONFIG="${GATE_SEARCH_DIR}/selected_gate_policy.json"
    export PINGMESH_GATE_POLICY_CONFIG="${GATE_POLICY_CONFIG}"

    echo
    echo "=== [gate_auto] apply and verify the selected policy ==="
    mkdir -p "${WORKDIR}/gate_selected"
    python Sys/Score/apply_trust_gate.py \
        --res "${PIPE_RES}" \
        --out "${WORKDIR}/gate_selected/res.json" \
        --policy-config "${GATE_POLICY_CONFIG}"
    score_result "${WORKDIR}/gate_selected/res.json"
    python Sys/Score/evaluate_gate_recall.py \
        --res "${PIPE_RES}" \
        --out-dir "${WORKDIR}/gate_recall" \
        --target-k "${GATE_TARGET_K}" \
        --policy-config "${GATE_POLICY_CONFIG}" \
        --assert-safe
    python Sys/Score/evaluate_trust_gate.py \
        --res "${PIPE_RES}" \
        --out-dir "${WORKDIR}/gate_eval" \
        --policy-config "${GATE_POLICY_CONFIG}"
fi

run_llm_experiment() {
    local name="$1"
    local gated="$2"
    local cache_dir="$3"
    local args=(
        --data-root "${PINGMESH_DATA}"
        --skills ${SKILLS}
        --npu-cards "${NPU}"
        --batch-size "${BATCH}"
        --top-k "${TOPK}"
        --output-dir "${RUN_TAG}/${name}"
        --summary-cache-dir "${cache_dir}"
    )
    if [ "${gated}" = "1" ]; then
        args+=(--gate)
    fi
    args+=("${DEBUG_ARGS[@]}")
    echo
    echo "=== [${name}] local LLM inference ==="
    python Sys/RootCauseAnalyze/SkilledAnalyzer.py "${args[@]}"
    score_result "${WORKDIR}/${name}/res.json"
}

if has_experiment pipe_llm; then
    run_llm_experiment pipe_llm 0 ""
fi
if has_experiment gate_llm; then
    run_llm_experiment gate_llm 1 ""
fi
if has_experiment cache_llm; then
    run_llm_experiment cache_llm 0 "${SUMMARY_CACHE_DIR}"
fi
if has_experiment gate_cache_llm; then
    run_llm_experiment gate_cache_llm 1 "${SUMMARY_CACHE_DIR}"
fi

export RCA_WORKDIR="${WORKDIR}"
python - <<'PY'
import csv
import json
import os
from pathlib import Path

workdir = Path(os.environ["RCA_WORKDIR"])
experiment_names = (
    "pipe",
    "gate_selected",
    "pipe_llm",
    "gate_llm",
    "cache_llm",
    "gate_cache_llm",
)
rows = []
for name in experiment_names:
    path = workdir / name / "sum.json"
    if not path.exists():
        continue
    summary = json.loads(path.read_text(encoding="utf-8"))
    metric_name = "skill_evaluation" if name in {"pipe", "gate_selected"} else "llm_evaluation"
    metrics = (summary.get(metric_name) or {}).get("ranking_metrics") or {}
    rows.append(
        {
            "experiment": name,
            "metric": metric_name,
            "cases": metrics.get("Total Evaluated Cases", 0),
            "top1": metrics.get("Top-1 Acc (%)", 0),
            "top3": metrics.get("Top-3 Acc (%)", 0),
            "top5": metrics.get("Top-5 Acc (%)", 0),
        }
    )

policy_path = workdir / "gate_search" / "selected_gate_policy.json"
policy = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.exists() else None
payload = {
    "workdir": str(workdir),
    "selected_gate_policy": (policy or {}).get("selected_policy"),
    "gate_policy_fallback": (policy or {}).get("fallback_to_always_llm"),
    "results": rows,
}
(workdir / "summary.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
)
with (workdir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=("experiment", "metric", "cases", "top1", "top3", "top5"))
    writer.writeheader()
    writer.writerows(rows)

print(json.dumps(payload, ensure_ascii=False, indent=2))
PY

echo
echo "RCA experiments completed: ${WORKDIR}"
