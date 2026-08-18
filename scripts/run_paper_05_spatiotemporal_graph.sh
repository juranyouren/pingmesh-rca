#!/usr/bin/env bash
# Paper experiment 05: deterministic Stage 1 versus the unified neural
# spatio-temporal event graph ranker, followed by Stage 2 reranking.
#
# Neural scores are always computed from grouped out-of-fold predictions.
# The final_model.pt checkpoint is trained only after OOF predictions are
# complete and is never used to score those same cases.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

python -c "import torch; print('Neural Stage 1 torch:', torch.__version__)" || {
    echo "[ERROR] Neural Stage 1 requires the server PyTorch environment." >&2
    exit 2
}

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_TAG="${1:-paper_05_spatiotemporal_graph}_${TIMESTAMP}"
WORKDIR="${PINGMESH_RESULTS}/${RUN_TAG}"
mkdir -p "${WORKDIR}"

echo "============================================"
echo "  Paper Exp 05: unified spatio-temporal graph"
echo "  data:       ${PINGMESH_DATA}"
echo "  results:    ${WORKDIR}"
echo "  folds:      ${PINGMESH_NEURAL_FOLDS}"
echo "  device:     ${PINGMESH_NEURAL_DEVICE}"
echo "============================================"

echo
echo "=== [deterministic] current topology + temporal fusion ==="
python Sys/RootCauseAnalyze/stage1/pipeline.py \
    --data-root "${PINGMESH_DATA}" \
    --rankers topology temporal \
    --top-k "${PINGMESH_TOP_K}" \
    --weight-file "${PINGMESH_WEIGHTS_MANUAL}" \
    --output-dir "${RUN_TAG}/deterministic"
python Sys/Score/Score_N.py "${WORKDIR}/deterministic/res.json"

echo
echo "=== [neural_oof] grouped out-of-fold neural Stage 1 ==="
python Sys/RootCauseAnalyze/stage1/neural_pipeline.py crossval \
    --data-root "${PINGMESH_DATA}" \
    --output-dir "${WORKDIR}/neural_oof" \
    --weight-file "${PINGMESH_WEIGHTS_MANUAL}" \
    --folds "${PINGMESH_NEURAL_FOLDS}" \
    --top-k "${PINGMESH_TOP_K}" \
    --device "${PINGMESH_NEURAL_DEVICE}" \
    --epochs "${PINGMESH_NEURAL_EPOCHS}" \
    --patience "${PINGMESH_NEURAL_PATIENCE}" \
    --hidden-dim "${PINGMESH_NEURAL_HIDDEN_DIM}" \
    --heads "${PINGMESH_NEURAL_HEADS}" \
    --layers "${PINGMESH_NEURAL_LAYERS}" \
    --max-events-per-device "${PINGMESH_NEURAL_MAX_EVENTS_PER_DEVICE}" \
    --max-events-total "${PINGMESH_NEURAL_MAX_EVENTS_TOTAL}" \
    --max-event-vocab "${PINGMESH_NEURAL_MAX_EVENT_VOCAB}" \
    --seed "${PINGMESH_NEURAL_SEED}"
python Sys/Score/Score_N.py "${WORKDIR}/neural_oof/res.json"

echo
echo "=== [neural_stage2] OOF neural roots -> propagation-constrained reranking ==="
python Sys/RootCauseAnalyze/propagation_pipeline.py \
    --data-root "${PINGMESH_DATA}" \
    --root-results "${WORKDIR}/neural_oof/res.json" \
    --output-dir "${WORKDIR}/neural_stage2" \
    --top-k "${PINGMESH_NEURAL_STAGE2_TOP_K}" \
    --weight-file "${PINGMESH_WEIGHTS_MANUAL}" \
    --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
    --max-path-depth "${PINGMESH_PROPAGATION_MAX_PATH_DEPTH}" \
    --stage1-weight "${PINGMESH_STAGE1_WEIGHT}"
python Sys/Score/Score_N.py "${WORKDIR}/neural_stage2/res.json"
python Sys/Score/evaluate_propagation.py \
    --predictions "${WORKDIR}/neural_stage2/res.json" \
    --out "${WORKDIR}/neural_stage2/validity.json"

export PINGMESH_NEURAL_EXPERIMENT_WORKDIR="${WORKDIR}"
python - <<'PY'
import csv
import json
import os
from pathlib import Path

workdir = Path(os.environ["PINGMESH_NEURAL_EXPERIMENT_WORKDIR"])
rows = []
for name in ("deterministic", "neural_oof", "neural_stage2"):
    path = workdir / name / "sum.json"
    if not path.exists():
        continue
    summary = json.loads(path.read_text(encoding="utf-8"))
    metrics = (summary.get("ranking_evaluation") or {}).get("ranking_metrics") or {}
    rows.append(
        {
            "experiment": name,
            "evaluation": "out_of_fold" if name.startswith("neural") else "deterministic",
            "cases": metrics.get("Total Evaluated Cases", 0),
            "top1": metrics.get("Top-1 Acc (%)", 0),
            "top3": metrics.get("Top-3 Acc (%)", 0),
            "top5": metrics.get("Top-5 Acc (%)", 0),
        }
    )

validity_path = workdir / "neural_stage2" / "validity.json"
validity = json.loads(validity_path.read_text(encoding="utf-8")) if validity_path.exists() else None
payload = {
    "workdir": str(workdir),
    "results": rows,
    "stage2_validity": (validity or {}).get("validity"),
    "final_checkpoint": str(workdir / "neural_oof" / "final_model.pt"),
}
(workdir / "summary.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
)
with (workdir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=("experiment", "evaluation", "cases", "top1", "top3", "top5"),
    )
    writer.writeheader()
    writer.writerows(rows)
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY

echo
echo "Paper Exp 05 completed: ${WORKDIR}"
