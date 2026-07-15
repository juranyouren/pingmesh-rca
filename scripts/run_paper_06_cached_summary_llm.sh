#!/usr/bin/env bash
# Paper Exp 05b: cached-summary LLM arbitration.
#
# Research question:
#   Does cached candidate summarization reduce prompt cost while preserving
#   ranking quality?
#
# Optional overrides: PINGMESH_SUMMARY_CACHE_DIR, PINGMESH_SUMMARY_MODEL_PATH.
#
# Common commands:
#   # Run after run_paper_05 has populated the same cache directory:
#   source scripts/common.sh
#   export PINGMESH_SUMMARY_CACHE_DIR="$PINGMESH_RESULTS/node_summary_cache_hybrid_v3"
#   ./scripts/run_paper_06_cached_summary_llm.sh
#
#   # Use a recognizable result prefix and print the first final LLM prompt:
#   PINGMESH_PRINT_FIRST_PROMPT=1 \
#     ./scripts/run_paper_06_cached_summary_llm.sh paper_06_hybrid_v3
#
#   # Evaluate the gated cached-LLM error cases after the run:
#   RUN="$PINGMESH_RESULTS/<paper_06_hybrid_v3_timestamp>"
#   python Sys/Score/evaluate_gate_selection.py \
#     --res "$RUN/gate_pipe_cache_llm/res.json" \
#     --out-dir "$RUN/gate_selection_cache"
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
