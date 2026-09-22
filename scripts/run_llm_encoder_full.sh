#!/usr/bin/env bash
# Canonical evidence -> root prior -> propagation inference -> metrics.
set -euo pipefail
PINGMESH_ENCODER_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${PINGMESH_ENCODER_SCRIPT_DIR}/common.sh"
cd "${PINGMESH_PROJECT_ROOT}"
export PYTHONIOENCODING=utf-8
# Pass --output explicitly for a stable location; otherwise use a fresh run directory.
PINGMESH_ENCODER_HAS_OUTPUT=0
for arg in "$@"; do
    case "${arg}" in --output|--output=*) PINGMESH_ENCODER_HAS_OUTPUT=1 ;; esac
done
if [[ "${PINGMESH_ENCODER_HAS_OUTPUT}" == "0" ]]; then
    set -- --output "${PINGMESH_RESULTS}/llm_encoder_$(date +%Y%m%d_%H%M%S)_$$" "$@"
fi
python -u -m Sys.Score.llm_encoder_experiment "$@"
