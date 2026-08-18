#!/usr/bin/env bash
# Compare P0 deterministic normalization, P1 fixed Logit/Softmax, and the P4
# case-grouped OOF supervised Softmax classifier with the same Stage 1 input.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

ROOT_RESULTS="${1:-}"
if [[ -z "${ROOT_RESULTS}" || ! -f "${ROOT_RESULTS}" ]]; then
    echo "Usage: bash scripts/run_stage2_edge_probability_ablation.sh <stage1-res.json> [run-tag]" >&2
    exit 2
fi
if [[ ! -d "${PINGMESH_PROPAGATION_LABELS_ROOT}" ]]; then
    echo "Missing propagation labels: ${PINGMESH_PROPAGATION_LABELS_ROOT}" >&2
    echo "Set PINGMESH_PROPAGATION_LABELS_ROOT before running P4." >&2
    exit 2
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_TAG="${2:-stage2_edge_probability}_${TIMESTAMP}"
WORKDIR="${PINGMESH_RESULTS}/${RUN_TAG}"
mkdir -p "${WORKDIR}"

run_stage2() {
    local name="$1"
    shift
    python Sys/RootCauseAnalyze/propagation_pipeline.py \
        --data-root "${PINGMESH_DATA}" \
        --root-results "${ROOT_RESULTS}" \
        --output-dir "${WORKDIR}/${name}" \
        --top-k "${PINGMESH_NEURAL_STAGE2_TOP_K}" \
        --weight-file "${PINGMESH_WEIGHTS_MANUAL}" \
        --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
        --max-path-depth "${PINGMESH_PROPAGATION_MAX_PATH_DEPTH}" \
        --stage1-weight "${PINGMESH_STAGE1_WEIGHT}" \
        "$@"
    python Sys/Score/Score_N.py "${WORKDIR}/${name}/res.json"
    python Sys/Score/evaluate_propagation.py \
        --predictions "${WORKDIR}/${name}/res.json" \
        --out "${WORKDIR}/${name}/validity.json"
}

echo "=== P0: deterministic evidence normalization ==="
run_stage2 p0 \
    --edge-probability-method deterministic_evidence_v1

echo "=== P1: fixed three-state Logit/Softmax ==="
run_stage2 p1 \
    --edge-probability-method logit_softmax_v1

echo "=== P4: train case-grouped OOF supervised classifier ==="
python Sys/Score/train_stage2_edge_classifier.py crossval \
    --data-root "${PINGMESH_DATA}" \
    --labels-root "${PINGMESH_PROPAGATION_LABELS_ROOT}" \
    --output-dir "${WORKDIR}/p4_model" \
    --folds "${PINGMESH_EDGE_CLASSIFIER_FOLDS}" \
    --epochs "${PINGMESH_EDGE_CLASSIFIER_EPOCHS}" \
    --patience "${PINGMESH_EDGE_CLASSIFIER_PATIENCE}" \
    --learning-rate "${PINGMESH_EDGE_CLASSIFIER_LEARNING_RATE}" \
    --l2 "${PINGMESH_EDGE_CLASSIFIER_L2}" \
    --seed "${PINGMESH_NEURAL_SEED}" \
    --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
    --max-path-depth "${PINGMESH_PROPAGATION_MAX_PATH_DEPTH}"

echo "=== P4: OOF supervised three-state Softmax ==="
run_stage2 p4 \
    --edge-probability-method supervised_softmax_v1 \
    --edge-probability-oof-manifest "${WORKDIR}/p4_model/oof_manifest.json"

export PINGMESH_EDGE_ABLATION_WORKDIR="${WORKDIR}"
python - <<'PY'
import json
import os
from pathlib import Path

workdir = Path(os.environ["PINGMESH_EDGE_ABLATION_WORKDIR"])
rows = []
for name in ("p0", "p1", "p4"):
    summary_path = workdir / name / "sum.json"
    validity_path = workdir / name / "validity.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    validity = json.loads(validity_path.read_text(encoding="utf-8"))["validity"]
    metrics = summary["ranking_evaluation"]["ranking_metrics"]
    rows.append(
        {
            "experiment": name,
            "cases": metrics.get("Total Evaluated Cases", 0),
            "top1": metrics.get("Top-1 Acc (%)", 0),
            "top3": metrics.get("Top-3 Acc (%)", 0),
            "top5": metrics.get("Top-5 Acc (%)", 0),
            "mean_coverage": validity.get("mean_observed_impact_coverage", 0),
            "mean_grounding": validity.get("mean_evidence_grounding", 0),
            "mean_edge_count": validity.get("mean_edge_count", 0),
            "rewrite_rate": validity.get("root_ranking_rewrite_rate", 0),
            "fallback_rate": validity.get("stage1_fallback_rate", 0),
        }
    )
(workdir / "summary.json").write_text(
    json.dumps({"workdir": str(workdir), "results": rows}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(json.dumps(rows, ensure_ascii=False, indent=2))
PY

echo "Stage 2 edge probability ablation completed: ${WORKDIR}"
