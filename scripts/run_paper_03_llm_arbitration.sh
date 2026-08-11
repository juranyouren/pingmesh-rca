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
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

PREFIX="${1:-paper_03_llm_arbitration}"
export PINGMESH_EXPERIMENTS="${PINGMESH_EXPERIMENTS:-pipe gate_auto pipe_llm gate_llm}"

echo "============================================"
echo "  Paper Exp 03: LLM Arbitration"
echo "  experiments: ${PINGMESH_EXPERIMENTS}"
echo "  npu:         ${PINGMESH_NPU_CARDS}"
echo "============================================"

./scripts/run_rca_experiments.sh "${PREFIX}"
