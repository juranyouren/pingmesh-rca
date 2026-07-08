#!/usr/bin/env bash
# Paper Exp 02: trust-tree routing without LLM.
#
# Research question:
#   Which cases can deterministic RCA accept automatically, and which require
#   LLM/operator intervention?
#
# Outputs:
#   ${PINGMESH_RESULTS}/paper_02_gate_routing_<timestamp>/
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

PREFIX="${1:-paper_02_gate_routing}"
export PINGMESH_EXPERIMENTS="${PINGMESH_EXPERIMENTS:-pipe gate_eval gate_pipe}"

echo "============================================"
echo "  Paper Exp 02: Trust-Tree Routing"
echo "  experiments: ${PINGMESH_EXPERIMENTS}"
echo "============================================"

./scripts/run_gate_pipe_experiments.sh "${PREFIX}"
