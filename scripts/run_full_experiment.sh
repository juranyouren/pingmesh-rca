#!/usr/bin/env bash
# End-to-end experiment: preprocessing -> root OOF -> DD model -> graph -> metrics.

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
Usage: bash scripts/run_full_experiment.sh [options]

Options:
  --root-variant supervised|self_supervised
                                   Root model variant (default: supervised)
  --resume RUN_DIR                 Continue an existing full run
  --stages LIST                    Comma-separated stages to consider
                                   (default: preprocess,root,dd,graph,evaluate)
  --with-edge-ablations            Also run P0/P1 propagation baselines
  --with-raw-node-metrics          Also evaluate without node aggregation
  --with-baselines                 Also run TraceRCA/NetEventCause/BiAn
  --dry-run                        Print the resolved workflow without executing it
  -h, --help                       Show this help

Run IDs are automatic:
  full_<variant>_<YYYYMMDD_HHMMSS>_<git-short-sha>[_NN]
EOF
}

ROOT_VARIANT="${PINGMESH_NEURAL_VARIANT}"
ROOT_VARIANT_EXPLICIT=0
RESUME_DIR=""
STAGES="preprocess,root,dd,graph,evaluate"
WITH_EDGE_ABLATIONS=0
WITH_RAW_NODE_METRICS=0
WITH_BASELINES=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --root-variant)
            ROOT_VARIANT="${2:?--root-variant requires a value}"
            ROOT_VARIANT_EXPLICIT=1
            shift 2
            ;;
        --resume)
            RESUME_DIR="${2:?--resume requires a run directory}"
            shift 2
            ;;
        --stages)
            STAGES="${2:?--stages requires a comma-separated list}"
            shift 2
            ;;
        --with-edge-ablations)
            WITH_EDGE_ABLATIONS=1
            shift
            ;;
        --with-raw-node-metrics)
            WITH_RAW_NODE_METRICS=1
            shift
            ;;
        --with-baselines)
            WITH_BASELINES=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
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

if [[ -n "${RESUME_DIR}" && "${ROOT_VARIANT_EXPLICIT}" == "0" ]]; then
    case "$(basename "${RESUME_DIR}")" in
        full_self_supervised_*) ROOT_VARIANT="self_supervised" ;;
        full_supervised_*) ROOT_VARIANT="supervised" ;;
    esac
fi

case "${ROOT_VARIANT}" in
    supervised)
        OOF_NAME="pc_stgr_oof"
        ;;
    self_supervised)
        OOF_NAME="pc_stgr_ssl_oof"
        ;;
    *)
        echo "[ERROR] --root-variant must be supervised or self_supervised." >&2
        exit 2
        ;;
esac

for stage in ${STAGES//,/ }; do
    case "${stage}" in
        preprocess|root|dd|graph|evaluate) ;;
        *)
            echo "[ERROR] Unknown stage in --stages: ${stage}" >&2
            exit 2
            ;;
    esac
done

if [[ -n "${RESUME_DIR}" ]]; then
    if [[ ! -d "${RESUME_DIR}" ]]; then
        echo "[ERROR] Resume directory does not exist: ${RESUME_DIR}" >&2
        exit 2
    fi
    WORKDIR="$(cd -- "${RESUME_DIR}" && pwd)"
elif [[ "${DRY_RUN}" == "1" ]]; then
    WORKDIR="$(pingmesh_preview_run_dir full "${ROOT_VARIANT}")"
else
    WORKDIR="$(pingmesh_create_run_dir full "${ROOT_VARIANT}")"
fi

if [[ "${DRY_RUN}" == "0" ]]; then
    mkdir -p "${WORKDIR}/logs" "${WORKDIR}/stages"
fi
ROOT_DIR="${WORKDIR}/root"
ROOT_RESULTS="${ROOT_DIR}/${OOF_NAME}/res.json"
DD_MODEL_DIR="${WORKDIR}/dd_edge_model"
DD_MANIFEST="${DD_MODEL_DIR}/oof_manifest.json"
PROPAGATION_DIR="${WORKDIR}/propagation"
P4_DIR="${PROPAGATION_DIR}/p4"
EVALUATION_DIR="${WORKDIR}/evaluation"

stage_selected() {
    [[ ",${STAGES}," == *",$1,"* ]]
}

stage_completed() {
    [[ -f "${WORKDIR}/stages/$1.done" ]] || return 1
    case "$1" in
        preprocess)
            [[ -f "${WORKDIR}/preprocess/topology_context_backfill_report.json" \
                && -f "${WORKDIR}/preprocess/topology_equivalence_report.json" ]]
            ;;
        root)
            [[ -f "${ROOT_RESULTS}" && -f "${ROOT_DIR}/summary.json" ]]
            ;;
        dd)
            [[ -f "${DD_MANIFEST}" ]]
            ;;
        graph)
            [[ -f "${P4_DIR}/res.json" \
                && -f "${P4_DIR}/selected_propagation_paths.json" ]] || return 1
            if [[ "${WITH_EDGE_ABLATIONS}" == "1" ]]; then
                [[ -f "${PROPAGATION_DIR}/p0/res.json" \
                    && -f "${PROPAGATION_DIR}/p1/res.json" ]] || return 1
            fi
            ;;
        evaluate)
            [[ -f "${WORKDIR}/summary.json" && -f "${EVALUATION_DIR}/p4.json" ]] || return 1
            if [[ "${WITH_EDGE_ABLATIONS}" == "1" ]]; then
                [[ -f "${EVALUATION_DIR}/p0.json" \
                    && -f "${EVALUATION_DIR}/p1.json" ]] || return 1
            fi
            if [[ "${WITH_RAW_NODE_METRICS}" == "1" ]]; then
                [[ -f "${EVALUATION_DIR}/p4_raw.json" ]] || return 1
                if [[ "${WITH_EDGE_ABLATIONS}" == "1" ]]; then
                    [[ -f "${EVALUATION_DIR}/p0_raw.json" \
                        && -f "${EVALUATION_DIR}/p1_raw.json" ]] || return 1
                fi
            fi
            ;;
    esac
}

mark_stage() {
    printf '%s\n' "$(date -Iseconds)" > "${WORKDIR}/stages/$1.done"
}

run_logged() {
    local stage="$1"
    shift
    if [[ "${DRY_RUN}" == "1" ]]; then
        printf '[DRY-RUN][%s] ' "${stage}"
        printf '%q ' "$@"
        printf '\n'
        return 0
    fi
    "$@" 2>&1 | tee -a "${WORKDIR}/logs/${stage}.log"
}

require_file() {
    if [[ "${DRY_RUN}" == "0" && ! -f "$1" ]]; then
        echo "[ERROR] Required file is missing: $1" >&2
        exit 2
    fi
}

require_dir() {
    if [[ "${DRY_RUN}" == "0" && ! -d "$1" ]]; then
        echo "[ERROR] Required directory is missing: $1" >&2
        exit 2
    fi
}

ensure_dir() {
    if [[ "${DRY_RUN}" == "0" ]]; then
        mkdir -p "$@"
    fi
}

if [[ "${DRY_RUN}" == "0" ]]; then
    if stage_selected preprocess || stage_selected root || stage_selected dd || stage_selected graph \
        || [[ "${WITH_BASELINES}" == "1" ]]; then
        require_dir "${PINGMESH_DATA}"
    fi
    if stage_selected preprocess; then
        require_dir "${PINGMESH_RAW_DATA}"
    fi
    if stage_selected dd || stage_selected evaluate; then
        require_dir "${PINGMESH_PROPAGATION_LABELS_ROOT}"
    fi
    if stage_selected root || stage_selected graph; then
        require_file "${PINGMESH_WEIGHTS_MANUAL}"
    fi
    if stage_selected root; then
        python -c "import torch; print('PC-STGR torch:', torch.__version__)" || {
            echo "[ERROR] Root training requires the server PyTorch environment." >&2
            exit 2
        }
    fi
fi

echo "============================================"
echo "  Full root + propagation experiment"
echo "  run:          $(basename "${WORKDIR}")"
echo "  workdir:      ${WORKDIR}"
echo "  root variant: ${ROOT_VARIANT}"
echo "  stages:       ${STAGES}"
echo "  DD ablations: ${WITH_EDGE_ABLATIONS}"
echo "  raw metrics:  ${WITH_RAW_NODE_METRICS}"
echo "  baselines:    ${WITH_BASELINES}"
echo "  dry run:      ${DRY_RUN}"
echo "============================================"

if [[ "${DRY_RUN}" == "0" ]]; then
    export PINGMESH_FULL_WORKDIR="${WORKDIR}"
    export PINGMESH_FULL_ROOT_VARIANT="${ROOT_VARIANT}"
    export PINGMESH_FULL_STAGES="${STAGES}"
    export PINGMESH_FULL_WITH_EDGE_ABLATIONS="${WITH_EDGE_ABLATIONS}"
    export PINGMESH_FULL_WITH_RAW_NODE_METRICS="${WITH_RAW_NODE_METRICS}"
    export PINGMESH_FULL_WITH_BASELINES="${WITH_BASELINES}"
    python - <<'PY'
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

workdir = Path(os.environ["PINGMESH_FULL_WORKDIR"])
results_root = Path(os.environ["PINGMESH_RESULTS"])
config_path = workdir / "run_config.json"
try:
    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=os.environ["PINGMESH_PROJECT_ROOT"], text=True
    ).strip()
except Exception:
    git_sha = "nogit"
if config_path.exists():
    existing = json.loads(config_path.read_text(encoding="utf-8"))
    requested_variant = os.environ["PINGMESH_FULL_ROOT_VARIANT"]
    if existing.get("root_variant") != requested_variant:
        raise SystemExit(
            f"resume variant mismatch: run uses {existing.get('root_variant')!r}, "
            f"requested {requested_variant!r}"
        )
else:
    payload = {
        "run_id": workdir.name,
        "created_at": datetime.now().astimezone().isoformat(),
        "git_sha": git_sha,
        "root_variant": os.environ["PINGMESH_FULL_ROOT_VARIANT"],
        "stages": os.environ["PINGMESH_FULL_STAGES"].split(","),
        "with_edge_ablations": os.environ["PINGMESH_FULL_WITH_EDGE_ABLATIONS"] == "1",
        "with_raw_node_metrics": os.environ["PINGMESH_FULL_WITH_RAW_NODE_METRICS"] == "1",
        "with_baselines": os.environ["PINGMESH_FULL_WITH_BASELINES"] == "1",
        "paths": {
            "data": os.environ["PINGMESH_DATA"],
            "raw_data": os.environ["PINGMESH_RAW_DATA"],
            "propagation_labels": os.environ["PINGMESH_PROPAGATION_LABELS_ROOT"],
            "manual_weights": os.environ["PINGMESH_WEIGHTS_MANUAL"],
            "workdir": str(workdir),
        },
    }
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
results_root.mkdir(parents=True, exist_ok=True)
(results_root / "latest_full_run.json").write_text(
    json.dumps({"run_id": workdir.name, "workdir": str(workdir)}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
PY
fi

if stage_selected preprocess; then
    if stage_completed preprocess; then
        echo "[SKIP] preprocess already completed"
    else
        ensure_dir "${WORKDIR}/preprocess"
        run_logged preprocess python Sys/Preprocess/backfill_topology_context.py \
            --cases-root "${PINGMESH_DATA}" \
            --raw-root "${PINGMESH_RAW_DATA}" \
            --report "${WORKDIR}/preprocess/topology_context_backfill_report.json" \
            --write \
            --require-complete
        run_logged preprocess python Sys/Preprocess/build_structural_equivalence.py \
            --cases-root "${PINGMESH_DATA}" \
            --report "${WORKDIR}/preprocess/topology_equivalence_report.json" \
            --write \
            --require-raw-topology
        [[ "${DRY_RUN}" == "1" ]] || mark_stage preprocess
    fi
fi

if stage_selected root; then
    if stage_completed root; then
        echo "[SKIP] root already completed"
    else
        run_logged root bash "${SCRIPT_DIR}/run_root_oof.sh" \
            --variant "${ROOT_VARIANT}" \
            --workdir "${ROOT_DIR}" \
            --skip-preprocess
        [[ "${DRY_RUN}" == "1" ]] || mark_stage root
    fi
fi

if stage_selected dd; then
    if stage_completed dd; then
        echo "[SKIP] dd already completed"
    else
        ensure_dir "${DD_MODEL_DIR}"
        run_logged dd python Sys/Score/train_stage2_edge_classifier.py crossval \
            --data-root "${PINGMESH_DATA}" \
            --labels-root "${PINGMESH_PROPAGATION_LABELS_ROOT}" \
            --output-dir "${DD_MODEL_DIR}" \
            --folds "${PINGMESH_EDGE_CLASSIFIER_FOLDS}" \
            --epochs "${PINGMESH_EDGE_CLASSIFIER_EPOCHS}" \
            --patience "${PINGMESH_EDGE_CLASSIFIER_PATIENCE}" \
            --learning-rate "${PINGMESH_EDGE_CLASSIFIER_LEARNING_RATE}" \
            --l2 "${PINGMESH_EDGE_CLASSIFIER_L2}" \
            --seed "${PINGMESH_NEURAL_SEED}" \
            --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
            --max-path-depth "${PINGMESH_PROPAGATION_MAX_PATH_DEPTH}"
        [[ "${DRY_RUN}" == "1" ]] || mark_stage dd
    fi
fi

run_propagation() {
    local name="$1"
    local method="$2"
    shift 2
    ensure_dir "${PROPAGATION_DIR}/${name}"
    run_logged graph python Sys/RootCauseAnalyze/propagation_pipeline.py \
        --data-root "${PINGMESH_DATA}" \
        --root-results "${ROOT_RESULTS}" \
        --output-dir "${PROPAGATION_DIR}/${name}" \
        --top-k "${PINGMESH_NEURAL_STAGE2_TOP_K}" \
        --weight-file "${PINGMESH_WEIGHTS_MANUAL}" \
        --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
        --max-path-depth "${PINGMESH_PROPAGATION_MAX_PATH_DEPTH}" \
        --stage1-weight "${PINGMESH_STAGE1_WEIGHT}" \
        --edge-probability-method "${method}" \
        "$@"
}

if stage_selected graph; then
    if stage_completed graph; then
        echo "[SKIP] graph already completed"
    else
        require_file "${ROOT_RESULTS}"
        require_file "${DD_MANIFEST}"
        run_propagation p4 supervised_softmax_v1 \
            --edge-probability-oof-manifest "${DD_MANIFEST}"
        if [[ "${WITH_EDGE_ABLATIONS}" == "1" ]]; then
            run_propagation p0 deterministic_evidence_v1
            run_propagation p1 logit_softmax_v1
        fi
        [[ "${DRY_RUN}" == "1" ]] || mark_stage graph
    fi
fi

evaluate_one() {
    local name="$1"
    local prediction_dir="${PROPAGATION_DIR}/${name}"
    run_logged evaluate python Sys/Score/Score_N.py "${prediction_dir}/res.json"
    run_logged evaluate python Sys/Score/evaluate_propagation.py \
        --predictions "${prediction_dir}/res.json" \
        --selected-paths "${prediction_dir}/selected_propagation_paths.json" \
        --out "${EVALUATION_DIR}/${name}.json" \
        --labels-root "${PINGMESH_PROPAGATION_LABELS_ROOT}"
    if [[ "${WITH_RAW_NODE_METRICS}" == "1" ]]; then
        run_logged evaluate python Sys/Score/evaluate_propagation.py \
            --predictions "${prediction_dir}/res.json" \
            --selected-paths "${prediction_dir}/selected_propagation_paths.json" \
            --out "${EVALUATION_DIR}/${name}_raw.json" \
            --labels-root "${PINGMESH_PROPAGATION_LABELS_ROOT}" \
            --disable-structural-equivalence
    fi
}

if stage_selected evaluate; then
    if stage_completed evaluate; then
        echo "[SKIP] evaluate already completed"
    else
        ensure_dir "${EVALUATION_DIR}"
        require_file "${P4_DIR}/res.json"
        require_file "${P4_DIR}/selected_propagation_paths.json"
        evaluate_one p4
        if [[ "${WITH_EDGE_ABLATIONS}" == "1" ]]; then
            evaluate_one p0
            evaluate_one p1
        fi

        if [[ "${DRY_RUN}" == "0" ]]; then
            export PINGMESH_FULL_OOF_NAME="${OOF_NAME}"
            python - <<'PY'
import csv
import json
import os
from pathlib import Path

workdir = Path(os.environ["PINGMESH_FULL_WORKDIR"])
oof_name = os.environ["PINGMESH_FULL_OOF_NAME"]
root_summary = json.loads((workdir / "root" / "summary.json").read_text(encoding="utf-8"))
root_row = next(row for row in root_summary["results"] if row["experiment"] == oof_name)
rows = []
for name in ("p4", "p0", "p1"):
    score_path = workdir / "propagation" / name / "sum.json"
    evaluation_path = workdir / "evaluation" / f"{name}.json"
    if not score_path.exists() or not evaluation_path.exists():
        continue
    score = json.loads(score_path.read_text(encoding="utf-8"))
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    ranking = score["ranking_evaluation"]["ranking_metrics"]
    labels = evaluation.get("label_metrics", {})
    rows.append(
        {
            "experiment": name,
            "cases": ranking.get("Total Evaluated Cases", 0),
            "top1": ranking.get("Top-1 Acc (%)", 0),
            "top3": ranking.get("Top-3 Acc (%)", 0),
            "top5": ranking.get("Top-5 Acc (%)", 0),
            "mrr": ranking.get("MRR", ranking.get("Mean Reciprocal Rank", 0)),
            "dd_edge_f1": labels.get("macro_directed_edge_f1", 0),
            "node_f1": labels.get("macro_node_f1", 0),
        }
    )

payload = {
    "run_id": workdir.name,
    "workdir": str(workdir),
    "root_variant": os.environ["PINGMESH_FULL_ROOT_VARIANT"],
    "root_metrics": {
        key: root_row[key] for key in ("cases", "top1", "top3", "top5", "mrr")
    },
    "propagation_metrics": rows,
    "artifacts": {
        "root_predictions": str(workdir / "root" / oof_name / "res.json"),
        "dd_oof_manifest": str(workdir / "dd_edge_model" / "oof_manifest.json"),
        "propagation_predictions": str(workdir / "propagation" / "p4" / "res.json"),
        "propagation_graphs": str(
            workdir / "propagation" / "p4" / "selected_propagation_paths.json"
        ),
        "evaluation": str(workdir / "evaluation" / "p4.json"),
    },
}
(workdir / "summary.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
)
with (workdir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
    fieldnames = ("experiment", "cases", "top1", "top3", "top5", "mrr", "dd_edge_f1", "node_f1")
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
            mark_stage evaluate
        fi
    fi
fi

if [[ "${WITH_BASELINES}" == "1" ]]; then
    if [[ -f "${WORKDIR}/stages/baselines.done" && -d "${WORKDIR}/baselines" ]]; then
        echo "[SKIP] baselines already completed"
    else
        run_logged baselines bash "${SCRIPT_DIR}/run_rca_baselines.sh" \
            --workdir "${WORKDIR}/baselines"
        [[ "${DRY_RUN}" == "1" ]] || mark_stage baselines
    fi
fi

echo
if [[ "${DRY_RUN}" == "1" ]]; then
    echo "Dry run completed; no training or evaluation command was executed."
else
    echo "Full experiment completed: ${WORKDIR}"
    echo "Summary: ${WORKDIR}/summary.json"
fi
