#!/usr/bin/env bash
# Grouped-OOF experiment for K candidate-conditioned hard-DAG PC-STGR passes.

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
Usage: bash scripts/run_candidate_graph_verifier_ablation.sh [options]

Options:
  --variant supervised|self_supervised  PC-STGR variant (default: self_supervised)
  --workdir PATH                         Output directory
  --base-stage1-dir PATH                 Reuse an existing base PC-STGR OOF directory
  --edge-stage1-dir PATH                 Reuse an existing probability-edge OOF directory
  --skip-preprocess                      Skip topology-context verification
  -h, --help                             Show this help

The reused probability-edge directory must contain res.json, final_model.pt,
final_train_res.json, and folds/fold_N.pt + fold_N_train_res.json. Example:

  bash scripts/run_candidate_graph_verifier_ablation.sh \
    --variant self_supervised \
    --base-stage1-dir OLD_ABLATION/pc_stgr_base \
    --edge-stage1-dir OLD_ABLATION/pc_stgr_edge_prob

Experiments:
  1. pc_stgr_base
  2. pc_stgr_edge_prob
  3. candidate_verifier_frozen    hard-DAG K-pass, pretrained backbone frozen
  4. candidate_verifier_finetuned hard-DAG K-pass, full verifier fine-tuned
EOF
}

STAGE1_VARIANT="self_supervised"
WORKDIR=""
BASE_STAGE1_DIR=""
EDGE_STAGE1_DIR=""
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
        --base-stage1-dir)
            BASE_STAGE1_DIR="${2:?--base-stage1-dir requires a path}"
            shift 2
            ;;
        --edge-stage1-dir)
            EDGE_STAGE1_DIR="${2:?--edge-stage1-dir requires a path}"
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
        PRETRAIN_ARGS=()
        ;;
    self_supervised)
        NEURAL_PIPELINE="Sys/RootCauseAnalyze/stage1/neural_ssl_pipeline.py"
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
        echo "[ERROR] --variant must be supervised or self_supervised." >&2
        exit 2
        ;;
esac

python -c "import torch; print('PyTorch:', torch.__version__)" || {
    echo "[ERROR] This experiment requires the server PyTorch environment." >&2
    exit 2
}

if [[ -z "${WORKDIR}" ]]; then
    WORKDIR="$(pingmesh_create_run_dir candidate_graph_verifier "${STAGE1_VARIANT}")"
else
    mkdir -p "${WORKDIR}"
    WORKDIR="$(cd -- "${WORKDIR}" && pwd)"
fi

if [[ "${SKIP_PREPROCESS}" == "0" ]]; then
    python Sys/Preprocess/backfill_topology_context.py \
        --cases-root "${PINGMESH_DATA}" \
        --raw-root "${PINGMESH_RAW_DATA}" \
        --report "${WORKDIR}/topology_context_backfill_report.json" \
        --write \
        --require-complete
fi

run_stage1() {
    local output_dir="$1"
    shift
    mkdir -p "${output_dir}"
    python "${NEURAL_PIPELINE}" crossval \
        --data-root "${PINGMESH_DATA}" \
        --output-dir "${output_dir}" \
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
        --propagation-probability-method "${PINGMESH_STAGE1_PROPAGATION_PROBABILITY_METHOD}" \
        --propagation-max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
        --seed "${PINGMESH_NEURAL_SEED}" \
        "${PRETRAIN_ARGS[@]}" \
        "$@"
    python Sys/Score/Score_N.py "${output_dir}/res.json"
}

resolve_reused_stage1() {
    local path="$1"
    local require_models="$2"
    path="$(cd -- "${path}" && pwd)"
    [[ -f "${path}/res.json" ]] || {
        echo "[ERROR] Missing ${path}/res.json" >&2
        exit 2
    }
    if [[ "${require_models}" == "1" ]]; then
        [[ -f "${path}/final_model.pt" && -f "${path}/final_train_res.json" ]] || {
            echo "[ERROR] Probability-edge Stage-1 directory lacks final model artifacts: ${path}" >&2
            exit 2
        }
    fi
    if [[ ! -f "${path}/sum.json" ]]; then
        python Sys/Score/Score_N.py "${path}/res.json" >&2
    fi
    printf '%s\n' "${path}"
}

if [[ -z "${BASE_STAGE1_DIR}" ]]; then
    BASE_STAGE1_DIR="${WORKDIR}/pc_stgr_base"
    echo "=== [1/4] Train base PC-STGR ==="
    run_stage1 "${BASE_STAGE1_DIR}"
else
    BASE_STAGE1_DIR="$(resolve_reused_stage1 "${BASE_STAGE1_DIR}" 0)"
    echo "=== [1/4] Reuse base PC-STGR: ${BASE_STAGE1_DIR} ==="
fi

if [[ -z "${EDGE_STAGE1_DIR}" ]]; then
    EDGE_STAGE1_DIR="${WORKDIR}/pc_stgr_edge_prob"
    echo "=== [2/4] Train probability-edge PC-STGR ==="
    run_stage1 "${EDGE_STAGE1_DIR}" --include-propagation-edge-probabilities
else
    EDGE_STAGE1_DIR="$(resolve_reused_stage1 "${EDGE_STAGE1_DIR}" 1)"
    echo "=== [2/4] Reuse probability-edge PC-STGR: ${EDGE_STAGE1_DIR} ==="
fi

run_verifier() {
    local name="$1"
    shift
    local output_dir="${WORKDIR}/${name}"
    mkdir -p "${output_dir}"
    python Sys/RootCauseAnalyze/stage1/candidate_graph_verifier_pipeline.py crossval \
        --data-root "${PINGMESH_DATA}" \
        --root-results "${EDGE_STAGE1_DIR}/res.json" \
        --stage1-model-dir "${EDGE_STAGE1_DIR}" \
        --output-dir "${output_dir}" \
        --weight-file "${PINGMESH_WEIGHTS_MANUAL}" \
        --folds "${PINGMESH_NEURAL_FOLDS}" \
        --top-k "${PINGMESH_NEURAL_STAGE2_TOP_K}" \
        --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
        --max-path-depth "${PINGMESH_PROPAGATION_MAX_PATH_DEPTH}" \
        --edge-probability-method deterministic_evidence_v1 \
        --device "${PINGMESH_NEURAL_DEVICE}" \
        --max-correction-scale "${PINGMESH_ROOT_VERIFIER_MAX_CORRECTION_SCALE}" \
        --epochs "${PINGMESH_ROOT_VERIFIER_EPOCHS}" \
        --patience "${PINGMESH_ROOT_VERIFIER_PATIENCE}" \
        --learning-rate "${PINGMESH_ROOT_VERIFIER_LEARNING_RATE}" \
        --weight-decay "${PINGMESH_ROOT_VERIFIER_WEIGHT_DECAY}" \
        --gradient-accumulation "${PINGMESH_ROOT_VERIFIER_GRADIENT_ACCUMULATION}" \
        --auxiliary-margin-loss-weight "${PINGMESH_ROOT_VERIFIER_AUXILIARY_MARGIN_WEIGHT}" \
        --seed "${PINGMESH_NEURAL_SEED}" \
        "$@"
    python Sys/Score/Score_N.py "${output_dir}/res.json"
}

echo "=== [3/4] Candidate verifier with frozen pretrained backbone ==="
run_verifier candidate_verifier_frozen --freeze-backbone

echo "=== [4/4] Fine-tuned candidate-conditioned graph verifier ==="
run_verifier candidate_verifier_finetuned

export PINGMESH_CGV_WORKDIR="${WORKDIR}"
export PINGMESH_CGV_BASE_DIR="${BASE_STAGE1_DIR}"
export PINGMESH_CGV_EDGE_DIR="${EDGE_STAGE1_DIR}"
export PINGMESH_CGV_VARIANT="${STAGE1_VARIANT}"
python - <<'PY'
import csv
import json
import os
from pathlib import Path

workdir = Path(os.environ["PINGMESH_CGV_WORKDIR"])
base_dir = Path(os.environ["PINGMESH_CGV_BASE_DIR"])
edge_dir = Path(os.environ["PINGMESH_CGV_EDGE_DIR"])
variant = os.environ["PINGMESH_CGV_VARIANT"]
experiments = (
    ("pc_stgr_base", base_dir),
    ("pc_stgr_edge_prob", edge_dir),
    ("candidate_verifier_frozen", workdir / "candidate_verifier_frozen"),
    ("candidate_verifier_finetuned", workdir / "candidate_verifier_finetuned"),
)
rows = []
for name, directory in experiments:
    score = json.loads((directory / "sum.json").read_text(encoding="utf-8"))
    metrics = score["ranking_evaluation"]["ranking_metrics"]
    row = {
        "experiment": name,
        "stage1_variant": variant,
        "cases": metrics.get("Total Evaluated Cases", 0),
        "top1": metrics.get("Top-1 Acc (%)", 0),
        "top3": metrics.get("Top-3 Acc (%)", 0),
        "top5": metrics.get("Top-5 Acc (%)", 0),
        "mrr": metrics.get("MRR", 0),
        "candidate_recall": "",
        "corrections": "",
        "corruptions": "",
        "net_corrections": "",
        "verification_scale": "",
    }
    summary_path = directory / "training_summary.json"
    if name.startswith("candidate_verifier") and summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        audit = summary["oof_metrics"]
        for key in (
            "candidate_recall",
            "corrections",
            "corruptions",
            "net_corrections",
        ):
            row[key] = audit.get(key, "")
        scales = [
            fold.get("metrics", {}).get("verification_scale")
            for fold in summary.get("folds", [])
        ]
        scales = [float(value) for value in scales if value is not None]
        row["verification_scale"] = (
            round(sum(scales) / len(scales), 8) if scales else ""
        )
    rows.append(row)

by_name = {row["experiment"]: row for row in rows}
payload = {
    "workdir": str(workdir),
    "stage1_variant": variant,
    "evaluation": "incident_grouped_out_of_fold",
    "results": rows,
    "effects": {
        "edge_probability_candidate_generator_vs_base": {
            metric: round(
                float(by_name["pc_stgr_edge_prob"][metric])
                - float(by_name["pc_stgr_base"][metric]),
                6,
            )
            for metric in ("top1", "top3", "top5", "mrr")
        },
        "frozen_candidate_verifier_vs_edge_stage1": {
            metric: round(
                float(by_name["candidate_verifier_frozen"][metric])
                - float(by_name["pc_stgr_edge_prob"][metric]),
                6,
            )
            for metric in ("top1", "mrr")
        },
        "finetuned_candidate_verifier_vs_edge_stage1": {
            metric: round(
                float(by_name["candidate_verifier_finetuned"][metric])
                - float(by_name["pc_stgr_edge_prob"][metric]),
                6,
            )
            for metric in ("top1", "mrr")
        },
    },
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

echo "Candidate graph verifier ablation completed: ${WORKDIR}"
