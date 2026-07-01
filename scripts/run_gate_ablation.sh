#!/usr/bin/env bash
# ============================================================
# Gate Policy Ablation
# Runs multiple routing strategies against gate_pipe_llm results.
#
# Usage:
#   ./scripts/run_gate_ablation.sh <gate_pipe_llm_run_dir>
#
# Example:
#   ./scripts/run_gate_ablation.sh /path/to/data/res/gate_pipe_experiments_20260701_120000/gate_pipe_llm
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

RUN_DIR="${1:?Usage: $0 <gate_pipe_llm_run_dir>}"
RES_JSON="${RUN_DIR}/res.json"
OUT_DIR="${RUN_DIR}/gate_ablation"

if [ ! -f "$RES_JSON" ]; then
    echo "ERROR: res.json not found at $RES_JSON"
    exit 1
fi

echo "============================================"
echo "  Gate Policy Ablation"
echo "  Input:  $RES_JSON"
echo "  Output: $OUT_DIR"
echo "============================================"

python Sys/Score/evaluate_gate_ablation.py \
    --res "$RES_JSON" \
    --out-dir "$OUT_DIR" \
    --policies baseline,strict_combined,conservative

echo ""
echo "Done → $OUT_DIR"
