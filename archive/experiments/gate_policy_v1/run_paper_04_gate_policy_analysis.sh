#!/usr/bin/env bash
# Paper Exp 04: gate policy and selection analysis.
#
# Research question:
#   Which gate policy is most reliable, and when should topo/temporal/LLM be
#   selected for invoke_llm cases?
#
# Usage:
#   ./scripts/run_paper_04_gate_policy_analysis.sh <gate_pipe_llm_run_dir>
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

RUN_DIR="${1:?Usage: $0 <gate_pipe_llm_run_dir>}"
RES_JSON="${RUN_DIR}/res.json"

if [ ! -f "${RES_JSON}" ]; then
    echo "ERROR: res.json not found at ${RES_JSON}" >&2
    exit 1
fi

echo "============================================"
echo "  Paper Exp 04: Gate Policy Analysis"
echo "  input: ${RES_JSON}"
echo "============================================"

python Sys/Score/evaluate_gate_ablation.py \
    --res "${RES_JSON}" \
    --out-dir "${RUN_DIR}/gate_ablation" \
    --policies baseline,strict_combined,conservative

python Sys/Score/evaluate_gate_selection.py \
    --res "${RES_JSON}" \
    --out-dir "${RUN_DIR}/gate_selection"
