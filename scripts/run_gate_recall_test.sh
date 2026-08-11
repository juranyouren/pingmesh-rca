#!/usr/bin/env bash
# Test whether the active gate catches every deterministic miss without an
# unsafe bypass. Usage:
#   ./scripts/run_gate_recall_test.sh <skillpipe-res.json> [output-dir] [target-k]
set -euo pipefail
cd "$(dirname "$0")/.."

RES_JSON="${1:?Usage: $0 <skillpipe-res.json> [output-dir] [target-k]}"
OUT_DIR="${2:-$(dirname "${RES_JSON}")/gate_recall}"
TARGET_K="${3:-1}"

python Sys/Score/evaluate_gate_recall.py \
    --res "${RES_JSON}" \
    --out-dir "${OUT_DIR}" \
    --target-k "${TARGET_K}" \
    --assert-safe
