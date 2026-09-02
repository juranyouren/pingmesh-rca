#!/usr/bin/env bash
# Compare P0 deterministic normalization, P1 fixed Logit/Softmax, and the P4
# case-grouped OOF supervised Softmax classifier with the same Stage 1 input.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

usage() {
    cat <<'EOF'
Usage: bash scripts/run_dd_edge_ablation.sh --root-results PATH [options]

Options:
  --root-results PATH   Grouped-OOF root res.json (required)
  --workdir PATH        Write into an existing workflow directory
  --skip-preprocess     Skip topology backfill/equivalence preprocessing
  -h, --help            Show this help

Without --workdir, a collision-safe run ID is generated automatically.
EOF
}

ROOT_RESULTS=""
WORKDIR=""
SKIP_PREPROCESS=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --root-results)
            ROOT_RESULTS="${2:?--root-results requires a path}"
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

if [[ -z "${ROOT_RESULTS}" || ! -f "${ROOT_RESULTS}" ]]; then
    echo "[ERROR] --root-results must point to an existing res.json." >&2
    usage >&2
    exit 2
fi
if [[ ! -d "${PINGMESH_PROPAGATION_LABELS_ROOT}" ]]; then
    echo "Missing propagation labels: ${PINGMESH_PROPAGATION_LABELS_ROOT}" >&2
    echo "Set PINGMESH_PROPAGATION_LABELS_ROOT before running P4." >&2
    exit 2
fi

if [[ -z "${WORKDIR}" ]]; then
    WORKDIR="$(pingmesh_create_run_dir dd_edge ablation)"
else
    mkdir -p "${WORKDIR}"
fi

if [[ "${SKIP_PREPROCESS}" == "0" ]]; then
    echo "=== Backfill and verify raw topology contexts ==="
    python Sys/Preprocess/backfill_topology_context.py \
        --cases-root "${PINGMESH_DATA}" \
        --raw-root "${PINGMESH_RAW_DATA}" \
        --report "${WORKDIR}/topology_context_backfill_report.json" \
        --write \
        --require-complete

    echo "=== Build evidence-free structural-equivalence sidecars ==="
    python Sys/Preprocess/build_structural_equivalence.py \
        --cases-root "${PINGMESH_DATA}" \
        --report "${WORKDIR}/topology_equivalence_report.json" \
        --write \
        --require-raw-topology
fi

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
        --selected-paths "${WORKDIR}/${name}/selected_propagation_paths.json" \
        --out "${WORKDIR}/${name}/validity.json" \
        --labels-root "${PINGMESH_PROPAGATION_LABELS_ROOT}"
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
    evaluation = json.loads(validity_path.read_text(encoding="utf-8"))
    validity = evaluation["validity"]
    label_metrics = evaluation.get("label_metrics", {})
    metrics = summary["ranking_evaluation"]["ranking_metrics"]
    rows.append(
        {
            "experiment": name,
            "cases": metrics.get("Total Evaluated Cases", 0),
            "top1": metrics.get("Top-1 Acc (%)", 0),
            "top3": metrics.get("Top-3 Acc (%)", 0),
            "top5": metrics.get("Top-5 Acc (%)", 0),
            "mrr": metrics.get("MRR", metrics.get("Mean Reciprocal Rank", 0)),
            "dd_edge_f1": label_metrics.get("macro_directed_edge_f1", 0),
            "node_f1": label_metrics.get("macro_node_f1", 0),
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
