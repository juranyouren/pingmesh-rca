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
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

PREFIX="${1:-paper_02_gate_routing}"
export PINGMESH_EXPERIMENTS="${PINGMESH_EXPERIMENTS:-pipe gate_auto}"

echo "============================================"
echo "  Paper Exp 02: Trust-Tree Routing"
echo "  experiments: ${PINGMESH_EXPERIMENTS}"
echo "============================================"

./scripts/run_rca_experiments.sh "${PREFIX}"
