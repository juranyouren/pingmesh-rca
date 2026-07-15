#!/usr/bin/env bash
# Paper Exp 01: deterministic skill ablation.
#
# Research question:
#   How much do topology, temporal evidence, and their fusion contribute?
#
# Outputs:
#   ${PINGMESH_RESULTS}/ablation_<timestamp>/
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

echo "============================================"
echo "  Paper Exp 01: Skill Ablation"
echo "  data:    ${PINGMESH_DATA}"
echo "  results: ${PINGMESH_RESULTS}"
echo "  top_k:   ${PINGMESH_TOP_K}"
echo "============================================"

./scripts/run_full_ablation.sh
