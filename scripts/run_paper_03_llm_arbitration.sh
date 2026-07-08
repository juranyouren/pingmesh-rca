#!/usr/bin/env bash
# Paper Exp 03: gated LLM arbitration.
#
# Research question:
#   Does gate-controlled LLM arbitration improve or preserve accuracy while
#   reducing unnecessary LLM calls compared with full LLM reranking?
#
# Outputs:
#   ${PINGMESH_RESULTS}/paper_03_llm_arbitration_<timestamp>/
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

PREFIX="${1:-paper_03_llm_arbitration}"
export PINGMESH_EXPERIMENTS="${PINGMESH_EXPERIMENTS:-pipe gate_eval gate_pipe pipe_llm gate_pipe_llm}"

echo "============================================"
echo "  Paper Exp 03: LLM Arbitration"
echo "  experiments: ${PINGMESH_EXPERIMENTS}"
echo "  npu:         ${PINGMESH_NPU_CARDS}"
echo "============================================"

./scripts/run_gate_pipe_experiments.sh "${PREFIX}"
