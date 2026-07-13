#!/usr/bin/env bash
# Paper Exp 05b: cached-summary LLM arbitration.
#
# Research question:
#   Does cached candidate summarization reduce prompt cost while preserving
#   ranking quality?
#
# Optional overrides: PINGMESH_SUMMARY_CACHE_DIR, PINGMESH_SUMMARY_MODEL_PATH.
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

PREFIX="${1:-paper_06_cached_summary_llm}"
export PINGMESH_EXPERIMENTS="${PINGMESH_EXPERIMENTS:-pipe gate_eval pipe_cache_llm gate_pipe_cache_llm}"

echo "============================================"
echo "  Paper Exp 05b: Cached Summary LLM"
echo "  experiments:   ${PINGMESH_EXPERIMENTS}"
echo "  summary_cache: ${PINGMESH_SUMMARY_CACHE_DIR}"
echo "============================================"

./scripts/run_gate_pipe_experiments.sh "${PREFIX}"
