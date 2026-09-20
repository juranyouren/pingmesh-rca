#!/usr/bin/env bash
# Zero-argument server entrypoint; dataset/GT/output defaults live in common.sh.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
cd "${PINGMESH_PROJECT_ROOT}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
if [[ "${1:-}" == "run" || "${1:-}" == "evaluate" ]]; then
    COMMAND="$1"
    shift
else
    COMMAND=run
fi
exec "${PYTHON:-python}" -m Baseline.RQ1 "${COMMAND}" "$@"
