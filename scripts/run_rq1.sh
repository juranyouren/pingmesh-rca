#!/usr/bin/env bash
# Run from any directory. Pass explicit server paths; no implicit label discovery.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."
exec "${PYTHON:-python}" -m Baseline.RQ1 "$@"
