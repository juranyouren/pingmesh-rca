#!/usr/bin/env bash
# ============================================================
# 完整方案运行: 预处理 -> 锚点条件传播图重建 -> 传播图评价。
#
# 这是"完整方案"的贯通入口 (非 RQ1 的 oracle-root 协议)。
# 锚点由 propagation_pipeline 内部用确定性排序 (拓扑/告警 PageRank + 时序证据)
# 计算；推理过程不读取传播标签，标签只在评价阶段使用。
#
# Usage:
#   bash scripts/run_full_experiment.sh
#   bash scripts/run_full_experiment.sh --dry-run
#   bash scripts/run_full_experiment.sh --stages preprocess,graph
#   bash scripts/run_full_experiment.sh --resume res/full_rules_20260922_101530_ab12cd34
#
#   # 使用 LLM evidence encoder 的输出替代规则编码
#   bash scripts/run_llm_encoder.sh --data "$PINGMESH_DATA" --output "$PINGMESH_RESULTS/llm_encoder_run"
#   bash scripts/run_full_experiment.sh --evidence-dir "$PINGMESH_RESULTS/llm_encoder_run"
#
#   # 环境变量覆盖默认值 (路径/模型/NPU 卡/公共参数来自 scripts/common.sh)
#   PINGMESH_DATA=/new/path bash scripts/run_full_experiment.sh
#
# Options:
#   --stages LIST            逗号分隔的阶段 (默认: preprocess,graph,evaluate)
#   --evidence-dir DIR       LLM encoder 输出根目录；缺省则使用规则编码
#   --resume RUN_DIR         继续已有 run 目录
#   --with-raw-node-metrics  额外评估不做节点聚合的原始设备路径
#   --dry-run                只打印解析后的工作流，不执行
#   -h, --help               显示本帮助
#
# Run IDs: full_<variant>_<YYYYMMDD_HHMMSS>_<git-short-sha>[_NN]
#          variant = rules | llm_encoder
# 输出目录: ${PINGMESH_RESULTS}/<run_id>/{preprocess,propagation,evaluation}
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PROJECT_ROOT}}"
source "${SCRIPT_DIR}/common.sh"
cd "${PROJECT_ROOT}"

export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

usage() { sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

STAGES="preprocess,graph,evaluate"
EVIDENCE_DIR=""
RESUME_DIR=""
WITH_RAW_NODE_METRICS=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --stages)                STAGES="${2:?--stages requires a comma-separated list}"; shift 2 ;;
        --evidence-dir)          EVIDENCE_DIR="${2:?--evidence-dir requires a value}"; shift 2 ;;
        --resume)                RESUME_DIR="${2:?--resume requires a run directory}"; shift 2 ;;
        --with-raw-node-metrics) WITH_RAW_NODE_METRICS=1; shift ;;
        --dry-run)               DRY_RUN=1; shift ;;
        -h|--help)               usage; exit 0 ;;
        *) echo "[ERROR] Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ -n "${EVIDENCE_DIR}" ]]; then
    VARIANT="llm_encoder"
else
    VARIANT="rules"
fi

for stage in ${STAGES//,/ }; do
    case "${stage}" in
        preprocess|graph|evaluate) ;;
        *) echo "[ERROR] Unknown stage in --stages: ${stage}" >&2; exit 2 ;;
    esac
done

if [[ -n "${RESUME_DIR}" ]]; then
    if [[ ! -d "${RESUME_DIR}" ]]; then
        echo "[ERROR] Resume directory does not exist: ${RESUME_DIR}" >&2
        exit 2
    fi
    WORKDIR="$(cd -- "${RESUME_DIR}" && pwd)"
    case "$(basename "${WORKDIR}")" in
        full_llm_encoder_*) VARIANT="llm_encoder" ;;
        full_rules_*)       VARIANT="rules" ;;
    esac
elif [[ "${DRY_RUN}" == "1" ]]; then
    WORKDIR="$(pingmesh_preview_run_dir full "${VARIANT}")"
else
    WORKDIR="$(pingmesh_create_run_dir full "${VARIANT}")"
fi

PREPROCESS_DIR="${WORKDIR}/preprocess"
PROPAGATION_DIR="${WORKDIR}/propagation"
P0_DIR="${PROPAGATION_DIR}/p0"
EVALUATION_DIR="${WORKDIR}/evaluation"

if [[ "${DRY_RUN}" == "0" ]]; then
    mkdir -p "${WORKDIR}/logs" "${WORKDIR}/stages"
fi

stage_selected() { [[ ",${STAGES}," == *",$1,"* ]]; }

stage_completed() {
    [[ -f "${WORKDIR}/stages/$1.done" ]] || return 1
    case "$1" in
        preprocess)
            [[ -f "${PREPROCESS_DIR}/topology_context_backfill_report.json" \
                && -f "${PREPROCESS_DIR}/topology_equivalence_report.json" ]]
            ;;
        graph)
            [[ -f "${P0_DIR}/res.json" && -f "${P0_DIR}/selected_propagation_paths.json" ]]
            ;;
        evaluate)
            [[ -f "${EVALUATION_DIR}/p0.json" && -f "${WORKDIR}/summary.json" ]] || return 1
            [[ "${EVALUATION_DIR}/p0.json" -nt "${P0_DIR}/res.json" \
                && "${WORKDIR}/summary.json" -nt "${EVALUATION_DIR}/p0.json" ]] || return 1
            if [[ "${WITH_RAW_NODE_METRICS}" == "1" ]]; then
                [[ -f "${EVALUATION_DIR}/p0_raw.json" ]] || return 1
            fi
            ;;
    esac
}

mark_stage() { printf '%s\n' "$(date -Iseconds)" > "${WORKDIR}/stages/$1.done"; }

run_logged() {
    local stage="$1"; shift
    if [[ "${DRY_RUN}" == "1" ]]; then
        printf '[DRY-RUN][%s] ' "${stage}"; printf '%q ' "$@"; printf '\n'
        return 0
    fi
    "$@" 2>&1 | tee -a "${WORKDIR}/logs/${stage}.log"
}

require_file() {
    if [[ "${DRY_RUN}" == "0" && ! -f "$1" ]]; then
        echo "[ERROR] Required file is missing: $1" >&2; exit 2
    fi
}

require_dir() {
    if [[ "${DRY_RUN}" == "0" && ! -d "$1" ]]; then
        echo "[ERROR] Required directory is missing: $1" >&2; exit 2
    fi
}

ensure_dir() { [[ "${DRY_RUN}" == "1" ]] || mkdir -p "$@"; }

if [[ "${DRY_RUN}" == "0" ]]; then
    if stage_selected preprocess || stage_selected graph; then
        require_dir "${PINGMESH_DATA}"
    fi
    if stage_selected preprocess; then
        require_dir "${PINGMESH_RAW_DATA}"
    fi
    if stage_selected graph; then
        require_file "${PINGMESH_WEIGHTS_MANUAL}"
    fi
    if stage_selected evaluate; then
        require_dir "${PINGMESH_PROPAGATION_LABELS_ROOT}"
    fi
    if [[ -n "${EVIDENCE_DIR}" ]]; then
        require_dir "${EVIDENCE_DIR}"
    fi
fi

echo "============================================"
echo "  Full propagation reconstruction experiment"
echo "  run:          $(basename "${WORKDIR}")"
echo "  workdir:      ${WORKDIR}"
echo "  evidence:     ${VARIANT}${EVIDENCE_DIR:+ (${EVIDENCE_DIR})}"
echo "  stages:       ${STAGES}"
echo "  top-k:        ${PINGMESH_TOP_K}"
echo "  raw metrics:  ${WITH_RAW_NODE_METRICS}"
echo "  dry run:      ${DRY_RUN}"
echo "============================================"

if [[ "${DRY_RUN}" == "0" ]]; then
    export PINGMESH_FULL_WORKDIR="${WORKDIR}"
    export PINGMESH_FULL_VARIANT="${VARIANT}"
    export PINGMESH_FULL_EVIDENCE_DIR="${EVIDENCE_DIR}"
    export PINGMESH_FULL_STAGES="${STAGES}"
    export PINGMESH_FULL_WITH_RAW_NODE_METRICS="${WITH_RAW_NODE_METRICS}"
    python - <<'PY'
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

workdir = Path(os.environ["PINGMESH_FULL_WORKDIR"])
config_path = workdir / "run_config.json"
variant = os.environ["PINGMESH_FULL_VARIANT"]
if config_path.exists():
    existing = json.loads(config_path.read_text(encoding="utf-8"))
    if existing.get("evidence_variant") != variant:
        raise SystemExit(
            f"resume variant mismatch: run uses {existing.get('evidence_variant')!r}, "
            f"requested {variant!r}"
        )
else:
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=os.environ["PINGMESH_PROJECT_ROOT"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        git_sha = "nogit"
    config_path.write_text(json.dumps({
        "schema_version": "pingmesh-full-experiment-run-v1",
        "run_id": workdir.name,
        "created_at": datetime.now().astimezone().isoformat(),
        "git_sha": git_sha,
        "evidence_variant": variant,
        "evidence_dir": os.environ["PINGMESH_FULL_EVIDENCE_DIR"] or None,
        "stages": os.environ["PINGMESH_FULL_STAGES"].split(","),
        "method": "anchor_conditioned_propagation_reconstruction",
        "edge_probability_method": "deterministic_evidence_v1",
        "with_raw_node_metrics": os.environ["PINGMESH_FULL_WITH_RAW_NODE_METRICS"] == "1",
        "model_path": os.environ.get("PINGMESH_MODEL_PATH"),
        "npu_cards": os.environ.get("PINGMESH_NPU_CARDS"),
        "top_k": os.environ.get("PINGMESH_TOP_K"),
        "stage1_weight": os.environ.get("PINGMESH_STAGE1_WEIGHT"),
        "max_candidate_nodes": os.environ.get("PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES"),
        "max_path_depth": os.environ.get("PINGMESH_PROPAGATION_MAX_PATH_DEPTH"),
        "paths": {
            "data": os.environ["PINGMESH_DATA"],
            "raw_data": os.environ["PINGMESH_RAW_DATA"],
            "propagation_labels": os.environ["PINGMESH_PROPAGATION_LABELS_ROOT"],
            "manual_weights": os.environ["PINGMESH_WEIGHTS_MANUAL"],
            "workdir": str(workdir),
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")
results_root = Path(os.environ["PINGMESH_RESULTS"])
results_root.mkdir(parents=True, exist_ok=True)
(results_root / "latest_full_run.json").write_text(
    json.dumps({"run_id": workdir.name, "workdir": str(workdir)}, ensure_ascii=False, indent=2),
    encoding="utf-8")
PY
fi

if stage_selected preprocess; then
    if stage_completed preprocess; then
        echo "[SKIP] preprocess already completed"
    else
        ensure_dir "${PREPROCESS_DIR}"
        run_logged preprocess python Sys/Preprocess/backfill_topology_context.py \
            --cases-root "${PINGMESH_DATA}" \
            --raw-root "${PINGMESH_RAW_DATA}" \
            --report "${PREPROCESS_DIR}/topology_context_backfill_report.json" \
            --write \
            --require-complete
        run_logged preprocess python Sys/Preprocess/build_structural_equivalence.py \
            --cases-root "${PINGMESH_DATA}" \
            --report "${PREPROCESS_DIR}/topology_equivalence_report.json" \
            --write \
            --require-raw-topology
        [[ "${DRY_RUN}" == "1" ]] || mark_stage preprocess
    fi
fi

if stage_selected graph; then
    if stage_completed graph; then
        echo "[SKIP] graph already completed"
    else
        ensure_dir "${P0_DIR}"
        EVIDENCE_ARGS=()
        if [[ -n "${EVIDENCE_DIR}" ]]; then
            EVIDENCE_ARGS=(--evidence-dir "${EVIDENCE_DIR}")
        fi
        run_logged graph python Sys/RootCauseAnalyze/propagation_pipeline.py \
            --data-root "${PINGMESH_DATA}" \
            --output-dir "${P0_DIR}" \
            --top-k "${PINGMESH_TOP_K}" \
            --weight-file "${PINGMESH_WEIGHTS_MANUAL}" \
            --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}" \
            --max-path-depth "${PINGMESH_PROPAGATION_MAX_PATH_DEPTH}" \
            --stage1-weight "${PINGMESH_STAGE1_WEIGHT}" \
            --edge-probability-method deterministic_evidence_v1 \
            "${EVIDENCE_ARGS[@]+"${EVIDENCE_ARGS[@]}"}"
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
        require_file "${P0_DIR}/res.json"
        require_file "${P0_DIR}/selected_propagation_paths.json"
        evaluate_one p0

        if [[ "${DRY_RUN}" == "0" ]]; then
            export PINGMESH_FULL_EVALUATION_DIR="${EVALUATION_DIR}"
            export PINGMESH_FULL_WITH_RAW_NODE_METRICS
            python - <<'PY'
import csv
import json
import os
from pathlib import Path

workdir = Path(os.environ["PINGMESH_FULL_WORKDIR"])
evaluation_dir = Path(os.environ["PINGMESH_FULL_EVALUATION_DIR"])
raw_metrics = os.environ["PINGMESH_FULL_WITH_RAW_NODE_METRICS"] == "1"
run_config = json.loads((workdir / "run_config.json").read_text(encoding="utf-8"))


def load(name):
    path = evaluation_dir / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def flat(prefix, payload, out):
    for key, value in (payload or {}).items():
        if isinstance(value, dict):
            flat(f"{prefix}{key}.", value, out)
        elif isinstance(value, (int, float, str)) or value is None:
            out[f"{prefix}{key}"] = value


# The node-aggregated view is the primary metric; the raw view is the
# `--with-raw-node-metrics` counterpart with structural-twin projection off.
views = {"p0": load("p0")}
if raw_metrics:
    views["p0_raw"] = load("p0_raw")

summary = {
    "schema_version": "pingmesh-full-experiment-summary-v1",
    "run_id": workdir.name,
    "workdir": str(workdir),
    "run_config": run_config,
    "views": {},
}
for name, payload in views.items():
    if payload is None:
        continue
    summary["views"][name] = {
        "validity": payload.get("validity"),
        "labeled_case_count": payload.get("labeled_case_count"),
        "label_metrics": payload.get("label_metrics"),
        "tolerant_accuracy": payload.get("tolerant_accuracy"),
        "case_count": len(payload.get("cases", [])),
    }

(workdir / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

rows = {}
for name, view in summary["views"].items():
    flat(f"{name}.", view, rows)
with (workdir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(["metric", "value"])
    for key in sorted(rows):
        writer.writerow([key, rows[key]])

lines = [f"# Full run {workdir.name}", "",
         f"- evidence variant: `{run_config.get('evidence_variant')}`",
         f"- git: `{run_config.get('git_sha')}`",
         f"- top-k: `{run_config.get('top_k')}`", "",
         "| metric | value |", "| --- | --- |"]
for key in sorted(rows):
    lines.append(f"| {key} | {rows[key]} |")
(workdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"summary written: {workdir / 'summary.md'}")
PY
        fi
        [[ "${DRY_RUN}" == "1" ]] || mark_stage evaluate
    fi
fi

echo
if [[ "${DRY_RUN}" == "1" ]]; then
    echo "Dry run completed; no training or evaluation command was executed."
else
    echo "Full experiment completed: ${WORKDIR}"
    echo "Summary: ${WORKDIR}/summary.json"
    echo "Table:   ${WORKDIR}/summary.md"
fi
