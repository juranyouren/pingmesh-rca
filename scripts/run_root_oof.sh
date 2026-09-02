#!/usr/bin/env bash
# Train deterministic and grouped-OOF PC-STGR root-cause rankers.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

usage() {
    cat <<'EOF'
Usage: bash scripts/run_root_oof.sh [options]

Options:
  --variant supervised|self_supervised  Root model variant (default: supervised)
  --workdir PATH                         Write into an existing workflow directory
  --skip-preprocess                      Skip topology backfill (for full workflow)
  -h, --help                             Show this help

Without --workdir, a collision-safe run ID is generated automatically.
EOF
}

STAGE1_VARIANT="${PINGMESH_NEURAL_VARIANT}"
WORKDIR=""
SKIP_PREPROCESS=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --variant)
            STAGE1_VARIANT="${2:?--variant requires a value}"
            shift 2
            ;;
        --workdir)
            WORKDIR="${2:?--workdir requires a path}"
            shift 2
            ;;
        --skip-preprocess)
            SKIP_PREPROCESS=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "[ERROR] Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

case "${STAGE1_VARIANT}" in
    supervised)
        NEURAL_PIPELINE="Sys/RootCauseAnalyze/stage1/neural_pipeline.py"
        OOF_NAME="pc_stgr_oof"
        PRETRAIN_ARGS=()
        ;;
    self_supervised)
        NEURAL_PIPELINE="Sys/RootCauseAnalyze/stage1/neural_ssl_pipeline.py"
        OOF_NAME="pc_stgr_ssl_oof"
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
        echo "[ERROR] --variant must be supervised or self_supervised: ${STAGE1_VARIANT}" >&2
        exit 2
        ;;
esac

python -c "import torch; print('PC-STGR torch:', torch.__version__)" || {
    echo "[ERROR] PC-STGR requires the server PyTorch environment." >&2
    exit 2
}

if [[ -z "${WORKDIR}" ]]; then
    WORKDIR="$(pingmesh_create_run_dir root "${STAGE1_VARIANT}")"
else
    mkdir -p "${WORKDIR}"
fi

echo "============================================"
echo "  Root-cause OOF experiment"
echo "  data:       ${PINGMESH_DATA}"
echo "  raw data:   ${PINGMESH_RAW_DATA}"
echo "  results:    ${WORKDIR}"
echo "  folds:      ${PINGMESH_NEURAL_FOLDS}"
echo "  device:     ${PINGMESH_NEURAL_DEVICE}"
echo "  variant:    ${STAGE1_VARIANT}"
echo "============================================"

if [[ "${SKIP_PREPROCESS}" == "0" ]]; then
    echo
    echo "=== [topology] backfill and verify raw task_topo contexts ==="
    python Sys/Preprocess/backfill_topology_context.py \
        --cases-root "${PINGMESH_DATA}" \
        --raw-root "${PINGMESH_RAW_DATA}" \
        --report "${WORKDIR}/topology_context_backfill_report.json" \
        --write \
        --require-complete
fi

echo
echo "=== [deterministic] topology + temporal root baseline ==="
python Sys/RootCauseAnalyze/stage1/pipeline.py \
    --data-root "${PINGMESH_DATA}" \
    --rankers topology temporal \
    --top-k "${PINGMESH_TOP_K}" \
    --weight-file "${PINGMESH_WEIGHTS_MANUAL}" \
    --output-dir "${WORKDIR}/deterministic"
python Sys/Score/Score_N.py "${WORKDIR}/deterministic/res.json"

echo
echo "=== [${OOF_NAME}] grouped out-of-fold PC-STGR (${STAGE1_VARIANT}) ==="
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

export PINGMESH_ROOT_WORKDIR="${WORKDIR}"
export PINGMESH_ROOT_VARIANT="${STAGE1_VARIANT}"
export PINGMESH_ROOT_OOF_NAME="${OOF_NAME}"
python - <<'PY'
import csv
import json
import os
from pathlib import Path

workdir = Path(os.environ["PINGMESH_ROOT_WORKDIR"])
variant = os.environ["PINGMESH_ROOT_VARIANT"]
oof_name = os.environ["PINGMESH_ROOT_OOF_NAME"]
rows = []
for name in ("deterministic", oof_name):
    summary = json.loads((workdir / name / "sum.json").read_text(encoding="utf-8"))
    metrics = summary["ranking_evaluation"]["ranking_metrics"]
    rows.append(
        {
            "experiment": name,
            "variant": variant if name == oof_name else "deterministic",
            "evaluation": "out_of_fold" if name == oof_name else "deterministic",
            "cases": metrics.get("Total Evaluated Cases", 0),
            "top1": metrics.get("Top-1 Acc (%)", 0),
            "top3": metrics.get("Top-3 Acc (%)", 0),
            "top5": metrics.get("Top-5 Acc (%)", 0),
            "mrr": metrics.get("MRR", metrics.get("Mean Reciprocal Rank", 0)),
        }
    )

payload = {
    "workdir": str(workdir),
    "stage1_variant": variant,
    "root_results": str(workdir / oof_name / "res.json"),
    "final_checkpoint": str(workdir / oof_name / "final_model.pt"),
    "results": rows,
}
(workdir / "summary.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
)
with (workdir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY

echo
echo "Root-cause OOF experiment completed: ${WORKDIR}"
