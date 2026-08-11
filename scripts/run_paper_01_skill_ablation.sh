#!/usr/bin/env bash
# Paper Exp 01: deterministic topology/temporal/fusion ablation.

set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_TAG="${1:-paper_01_skill_ablation}_${TIMESTAMP}"
WORKDIR="${PINGMESH_RESULTS}/${RUN_TAG}"
mkdir -p "${WORKDIR}"

COMBINATIONS=("1|topo" "2|temporal" "1 2|topo_temporal")
WEIGHTS=("manual|${PINGMESH_WEIGHTS_MANUAL}" "llm|${PINGMESH_WEIGHTS_LLM}")

for combination in "${COMBINATIONS[@]}"; do
    IFS="|" read -r skills method <<< "${combination}"
    for weight in "${WEIGHTS[@]}"; do
        IFS="|" read -r weight_name weight_path <<< "${weight}"
        if [ ! -f "${weight_path}" ]; then
            echo "[WARNING] Skip missing weight file: ${weight_path}" >&2
            continue
        fi
        output_name="${method}__w_${weight_name}"
        echo
        echo "=== [${output_name}] skills=${skills} ==="
        python Sys/RootCauseAnalyze/skill_pipeline.py \
            --data-root "${PINGMESH_DATA}" \
            --skills ${skills} \
            --top-k "${PINGMESH_TOP_K}" \
            --weight-file "${weight_path}" \
            --output-dir "${RUN_TAG}/${output_name}"
        python Sys/Score/Score_N.py "${WORKDIR}/${output_name}/res.json"
    done
done

export RCA_ABLATION_WORKDIR="${WORKDIR}"
python - <<'PY'
import json
import os
from pathlib import Path

workdir = Path(os.environ["RCA_ABLATION_WORKDIR"])
rows = []
for path in sorted(workdir.glob("*/sum.json")):
    payload = json.loads(path.read_text(encoding="utf-8"))
    metrics = (payload.get("skill_evaluation") or {}).get("ranking_metrics") or {}
    rows.append(
        {
            "experiment": path.parent.name,
            "cases": metrics.get("Total Evaluated Cases", 0),
            "top1": metrics.get("Top-1 Acc (%)", 0),
            "top3": metrics.get("Top-3 Acc (%)", 0),
            "top5": metrics.get("Top-5 Acc (%)", 0),
        }
    )
rows.sort(key=lambda row: (-float(row["top1"]), row["experiment"]))
(workdir / "summary.json").write_text(
    json.dumps({"results": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(rows, ensure_ascii=False, indent=2))
PY

echo "Paper Exp 01 completed: ${WORKDIR}"
