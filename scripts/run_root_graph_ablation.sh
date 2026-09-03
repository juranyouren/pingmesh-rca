#!/usr/bin/env bash
# Grouped-OOF ablation for propagation probabilities and the statistical MLP reranker.

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
Usage: bash scripts/run_root_graph_ablation.sh [options]

Options:
  --variant supervised|self_supervised  PC-STGR variant (default: supervised)
  --workdir PATH                         Reuse/create an explicit output directory
  --skip-preprocess                      Skip raw topology-context verification
  -h, --help                             Show this help

Variants evaluated with identical grouped folds and seeds:
  1. pc_stgr_base             Original PC-STGR
  2. pc_stgr_edge_prob        + root-independent three-state edge probabilities
  3. pc_stgr_base_score_mlp   Stage-1-score-only residual MLP control
  4. pc_stgr_base_graph_mlp   Original PC-STGR + propagation-statistics MLP
  5. pc_stgr_edge_prob_graph_mlp
                              Both propagation additions
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
    echo "[ERROR] This ablation requires the server PyTorch environment." >&2
    exit 2
}

if [[ -z "${WORKDIR}" ]]; then
    WORKDIR="$(pingmesh_create_run_dir root_graph_ablation "${STAGE1_VARIANT}")"
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

run_stage1_variant() {
    local name="$1"
    shift
    local output_dir="${WORKDIR}/${name}"
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

run_reranker_variant() {
    local base_name="$1"
    local output_name="$2"
    local feature_set="$3"
    local output_dir="${WORKDIR}/${output_name}"
    mkdir -p "${output_dir}"
    python Sys/RootCauseAnalyze/stage1/propagation_reranker_pipeline.py crossval \
        --data-root "${PINGMESH_DATA}" \
        --root-results "${WORKDIR}/${base_name}/res.json" \
        --output-dir "${output_dir}" \
        --folds "${PINGMESH_NEURAL_FOLDS}" \
        --top-k "${PINGMESH_NEURAL_STAGE2_TOP_K}" \
        --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
        --max-path-depth "${PINGMESH_PROPAGATION_MAX_PATH_DEPTH}" \
        --edge-probability-method deterministic_evidence_v1 \
        --device "${PINGMESH_NEURAL_DEVICE}" \
        --hidden-dim "${PINGMESH_ROOT_RERANKER_HIDDEN_DIM}" \
        --dropout "${PINGMESH_ROOT_RERANKER_DROPOUT}" \
        --correction-scale "${PINGMESH_ROOT_RERANKER_CORRECTION_SCALE}" \
        --feature-set "${feature_set}" \
        --epochs "${PINGMESH_ROOT_RERANKER_EPOCHS}" \
        --patience "${PINGMESH_ROOT_RERANKER_PATIENCE}" \
        --learning-rate "${PINGMESH_ROOT_RERANKER_LEARNING_RATE}" \
        --weight-decay "${PINGMESH_ROOT_RERANKER_WEIGHT_DECAY}" \
        --seed "${PINGMESH_NEURAL_SEED}"
    python Sys/Score/Score_N.py "${output_dir}/res.json"
}

echo "=== [1/5] Original PC-STGR ==="
run_stage1_variant pc_stgr_base

echo "=== [2/5] PC-STGR + root-independent edge probabilities ==="
run_stage1_variant pc_stgr_edge_prob --include-propagation-edge-probabilities

echo "=== [3/5] Stage-1-score-only MLP control ==="
run_reranker_variant pc_stgr_base pc_stgr_base_score_mlp stage1_only

echo "=== [4/5] Original PC-STGR + propagation-statistics MLP ==="
run_reranker_variant pc_stgr_base pc_stgr_base_graph_mlp all

echo "=== [5/5] Edge-probability PC-STGR + propagation-statistics MLP ==="
run_reranker_variant pc_stgr_edge_prob pc_stgr_edge_prob_graph_mlp all

export PINGMESH_ABLATION_WORKDIR="${WORKDIR}"
export PINGMESH_ABLATION_VARIANT="${STAGE1_VARIANT}"
python - <<'PY'
import csv
import json
import os
from pathlib import Path

workdir = Path(os.environ["PINGMESH_ABLATION_WORKDIR"])
stage1_variant = os.environ["PINGMESH_ABLATION_VARIANT"]
names = (
    "pc_stgr_base",
    "pc_stgr_edge_prob",
    "pc_stgr_base_score_mlp",
    "pc_stgr_base_graph_mlp",
    "pc_stgr_edge_prob_graph_mlp",
)
rows = []
for name in names:
    score = json.loads((workdir / name / "sum.json").read_text(encoding="utf-8"))
    metrics = score["ranking_evaluation"]["ranking_metrics"]
    row = {
        "experiment": name,
        "stage1_variant": stage1_variant,
        "edge_probabilities": int("edge_prob" in name),
        "statistical_mlp": int(name.endswith("_mlp")),
        "mlp_feature_set": "",
        "cases": metrics.get("Total Evaluated Cases", 0),
        "top1": metrics.get("Top-1 Acc (%)", 0),
        "top3": metrics.get("Top-3 Acc (%)", 0),
        "top5": metrics.get("Top-5 Acc (%)", 0),
        "mrr": metrics.get("MRR", 0),
        "candidate_recall": "",
        "corrections": "",
        "corruptions": "",
        "net_corrections": "",
    }
    reranker_summary = workdir / name / "training_summary.json"
    if name.endswith("_mlp") and reranker_summary.exists():
        reranker = json.loads(reranker_summary.read_text(encoding="utf-8"))
        audit = reranker["oof_metrics"]
        row["mlp_feature_set"] = reranker["model_config"].get("feature_set", "all")
        for key in ("candidate_recall", "corrections", "corruptions", "net_corrections"):
            row[key] = audit.get(key, "")
    rows.append(row)

payload = {
    "workdir": str(workdir),
    "stage1_variant": stage1_variant,
    "evaluation": "incident_grouped_out_of_fold",
    "results": rows,
}
by_name = {row["experiment"]: row for row in rows}
payload["effects"] = {
    "edge_probability_stage1": {
        metric: round(
            float(by_name["pc_stgr_edge_prob"][metric])
            - float(by_name["pc_stgr_base"][metric]),
            6,
        )
        for metric in ("top1", "mrr")
    },
    "propagation_graph_features_over_score_only_mlp": {
        metric: round(
            float(by_name["pc_stgr_base_graph_mlp"][metric])
            - float(by_name["pc_stgr_base_score_mlp"][metric]),
            6,
        )
        for metric in ("top1", "mrr")
    },
    "combined_over_base": {
        metric: round(
            float(by_name["pc_stgr_edge_prob_graph_mlp"][metric])
            - float(by_name["pc_stgr_base"][metric]),
            6,
        )
        for metric in ("top1", "mrr")
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

echo "Root graph ablation completed: ${WORKDIR}"
