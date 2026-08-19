#!/usr/bin/env bash
# PC-STGR paper experiment 05: deterministic Stage 1 versus a selectable
# supervised or self-supervised-pretrained PC-STGR, followed by Stage 2 reranking.
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

STAGE1_VARIANT="${2:-${PINGMESH_NEURAL_VARIANT}}"
case "${STAGE1_VARIANT}" in
    supervised)
        NEURAL_PIPELINE="Sys/RootCauseAnalyze/stage1/neural_pipeline.py"
        OOF_NAME="pc_stgr_oof"
        STAGE2_NAME="pc_stgr_stage2"
        PRETRAIN_ARGS=()
        ;;
    self_supervised)
        NEURAL_PIPELINE="Sys/RootCauseAnalyze/stage1/neural_ssl_pipeline.py"
        OOF_NAME="pc_stgr_ssl_oof"
        STAGE2_NAME="pc_stgr_ssl_stage2"
        PRETRAIN_ARGS=(
            --pretrain-epochs "${PINGMESH_NEURAL_PRETRAIN_EPOCHS}"
            --pretrain-learning-rate "${PINGMESH_NEURAL_PRETRAIN_LEARNING_RATE}"
            --pretrain-weight-decay "${PINGMESH_NEURAL_PRETRAIN_WEIGHT_DECAY}"
            --pretrain-gradient-accumulation "${PINGMESH_NEURAL_PRETRAIN_GRADIENT_ACCUMULATION}"
            --pretrain-gradient-clip "${PINGMESH_NEURAL_PRETRAIN_GRADIENT_CLIP}"
            --pretrain-token-mask-rate "${PINGMESH_NEURAL_PRETRAIN_TOKEN_MASK_RATE}"
            --pretrain-feature-mask-rate "${PINGMESH_NEURAL_PRETRAIN_FEATURE_MASK_RATE}"
            --pretrain-edge-drop-rate "${PINGMESH_NEURAL_PRETRAIN_EDGE_DROP_RATE}"
            --pretrain-token-loss-weight "${PINGMESH_NEURAL_PRETRAIN_TOKEN_LOSS_WEIGHT}"
            --pretrain-feature-loss-weight "${PINGMESH_NEURAL_PRETRAIN_FEATURE_LOSS_WEIGHT}"
            --pretrain-edge-loss-weight "${PINGMESH_NEURAL_PRETRAIN_EDGE_LOSS_WEIGHT}"
        )
        ;;
    *)
        echo "[ERROR] Stage 1 variant must be supervised or self_supervised: ${STAGE1_VARIANT}" >&2
        exit 2
        ;;
esac

python -c "import torch; print('PC-STGR torch:', torch.__version__)" || {
    echo "[ERROR] PC-STGR requires the server PyTorch environment." >&2
    exit 2
}

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_TAG="${1:-paper_05_pc_stgr}_${TIMESTAMP}"
WORKDIR="${PINGMESH_RESULTS}/${RUN_TAG}"
mkdir -p "${WORKDIR}"

echo "============================================"
echo "  Paper Exp 05: PC-STGR"
echo "  data:       ${PINGMESH_DATA}"
echo "  raw data:   ${PINGMESH_RAW_DATA}"
echo "  results:    ${WORKDIR}"
echo "  folds:      ${PINGMESH_NEURAL_FOLDS}"
echo "  device:     ${PINGMESH_NEURAL_DEVICE}"
echo "  variant:    ${STAGE1_VARIANT}"
echo "============================================"

echo
echo "=== [topology] backfill and verify raw task_topo contexts ==="
python Sys/Preprocess/backfill_topology_context.py \
    --cases-root "${PINGMESH_DATA}" \
    --raw-root "${PINGMESH_RAW_DATA}" \
    --report "${WORKDIR}/topology_context_backfill_report.json" \
    --write \
    --require-complete

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
echo "=== [${OOF_NAME}] grouped out-of-fold PC-STGR Stage 1 (${STAGE1_VARIANT}) ==="
python "${NEURAL_PIPELINE}" crossval \
    --data-root "${PINGMESH_DATA}" \
    --output-dir "${WORKDIR}/${OOF_NAME}" \
    --weight-file "${PINGMESH_WEIGHTS_MANUAL}" \
    --folds "${PINGMESH_NEURAL_FOLDS}" \
    --top-k "${PINGMESH_TOP_K}" \
    --device "${PINGMESH_NEURAL_DEVICE}" \
    --epochs "${PINGMESH_NEURAL_EPOCHS}" \
    --patience "${PINGMESH_NEURAL_PATIENCE}" \
    --hidden-dim "${PINGMESH_NEURAL_HIDDEN_DIM}" \
    --heads "${PINGMESH_NEURAL_HEADS}" \
    --layers "${PINGMESH_NEURAL_LAYERS}" \
    --event-embedding-dim "${PINGMESH_NEURAL_EVENT_EMBEDDING_DIM}" \
    --max-events-per-device "${PINGMESH_NEURAL_MAX_EVENTS_PER_DEVICE}" \
    --max-events-total "${PINGMESH_NEURAL_MAX_EVENTS_TOTAL}" \
    --max-event-vocab "${PINGMESH_NEURAL_MAX_EVENT_VOCAB}" \
    --seed "${PINGMESH_NEURAL_SEED}" \
    "${PRETRAIN_ARGS[@]}"
python Sys/Score/Score_N.py "${WORKDIR}/${OOF_NAME}/res.json"

echo
echo "=== [${STAGE2_NAME}] OOF PC-STGR roots -> propagation-constrained reranking ==="
python Sys/RootCauseAnalyze/propagation_pipeline.py \
    --data-root "${PINGMESH_DATA}" \
    --root-results "${WORKDIR}/${OOF_NAME}/res.json" \
    --output-dir "${WORKDIR}/${STAGE2_NAME}" \
    --top-k "${PINGMESH_NEURAL_STAGE2_TOP_K}" \
    --weight-file "${PINGMESH_WEIGHTS_MANUAL}" \
    --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
    --max-path-depth "${PINGMESH_PROPAGATION_MAX_PATH_DEPTH}" \
    --stage1-weight "${PINGMESH_STAGE1_WEIGHT}"
python Sys/Score/Score_N.py "${WORKDIR}/${STAGE2_NAME}/res.json"
python Sys/Score/evaluate_propagation.py \
    --predictions "${WORKDIR}/${STAGE2_NAME}/res.json" \
    --selected-paths "${WORKDIR}/${STAGE2_NAME}/selected_propagation_paths.json" \
    --out "${WORKDIR}/${STAGE2_NAME}/validity.json"

export PINGMESH_NEURAL_EXPERIMENT_WORKDIR="${WORKDIR}"
export PINGMESH_NEURAL_EXPERIMENT_VARIANT="${STAGE1_VARIANT}"
export PINGMESH_NEURAL_EXPERIMENT_OOF_NAME="${OOF_NAME}"
export PINGMESH_NEURAL_EXPERIMENT_STAGE2_NAME="${STAGE2_NAME}"
python - <<'PY'
import csv
import json
import os
from pathlib import Path

workdir = Path(os.environ["PINGMESH_NEURAL_EXPERIMENT_WORKDIR"])
variant = os.environ["PINGMESH_NEURAL_EXPERIMENT_VARIANT"]
oof_name = os.environ["PINGMESH_NEURAL_EXPERIMENT_OOF_NAME"]
stage2_name = os.environ["PINGMESH_NEURAL_EXPERIMENT_STAGE2_NAME"]
rows = []
for name in ("deterministic", oof_name, stage2_name):
    path = workdir / name / "sum.json"
    if not path.exists():
        continue
    summary = json.loads(path.read_text(encoding="utf-8"))
    metrics = (summary.get("ranking_evaluation") or {}).get("ranking_metrics") or {}
    rows.append(
        {
            "experiment": name,
            "stage1_variant": variant if name != "deterministic" else "deterministic",
            "evaluation": "out_of_fold" if name != "deterministic" else "deterministic",
            "cases": metrics.get("Total Evaluated Cases", 0),
            "top1": metrics.get("Top-1 Acc (%)", 0),
            "top3": metrics.get("Top-3 Acc (%)", 0),
            "top5": metrics.get("Top-5 Acc (%)", 0),
        }
    )

validity_path = workdir / stage2_name / "validity.json"
validity = json.loads(validity_path.read_text(encoding="utf-8")) if validity_path.exists() else None
payload = {
    "workdir": str(workdir),
    "stage1_variant": variant,
    "results": rows,
    "stage2_validity": (validity or {}).get("validity"),
    "final_checkpoint": str(workdir / oof_name / "final_model.pt"),
}
(workdir / "summary.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
)
with (workdir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=("experiment", "stage1_variant", "evaluation", "cases", "top1", "top3", "top5"),
    )
    writer.writeheader()
    writer.writerows(rows)
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY

echo
echo "Paper Exp 05 completed: ${WORKDIR}"
