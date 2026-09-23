#!/usr/bin/env bash
# ============================================================
# M3 骨架重建消融：在同一份证据上跑三种求解模式并对比。
#
# 三个变体共用 --edge-probability-method logit_evidence_v1，只切换全局骨架的
# 求解方式，从而把"求解器差异"和"证据模型差异"分开：
#
#   beam      现有 M2：root 距离门控 + beam 路径搜索      (= 论文消融表第 1 行)
#   backbone  最大证据树骨架，无 DAG 增补                  (= 第 2 行)
#   full      最大证据树骨架 + 证据门控 DAG 增补           (= 第 3 行)
#
# 重要：默认 null_weight=0.0 处在 lift 空间，等价于 "p > prior"（physical 为
# 0.05），与 beam 路径的 min_edge_support（概率 0.25）不是同一个门槛。直接对比
# 会测到阈值差异而不是算法差异，因此提供 --align-thresholds 把 null_weight
# 反解到指定概率。注意 lift 与概率不在同一空间，且各 edge_type 的 prior 不同，
# 单一标量无法表达统一概率门槛——反解以 physical 的 prior 为准。
#
# Usage:
#   bash scripts/run_m3_variants.sh
#   bash scripts/run_m3_variants.sh --align-thresholds
#   bash scripts/run_m3_variants.sh --variants beam,full
#   bash scripts/run_m3_variants.sh --evaluate
#   bash scripts/run_m3_variants.sh --dry-run
#
#   PINGMESH_DATA=/path/to/nodes_max_labeled bash scripts/run_m3_variants.sh
#   PINGMESH_M3_AUGMENTATION_MIN_PROBABILITY=0.30 bash scripts/run_m3_variants.sh
#
# Options:
#   --data DIR             事件目录 (默认 $PINGMESH_DATA)
#   --variants LIST        逗号分隔 beam|backbone|full (默认全部)
#   --align-thresholds     把 null_weight 反解到 $PINGMESH_M3_ALIGN_PROBABILITY
#   --evaluate             追加 Sys/Score 评测并写入 evaluation/
#   --dry-run              只打印命令，不执行
#   -h, --help             显示本帮助
#
# 输出: ${PINGMESH_RESULTS}/m3_ablation_<YYYYMMDD_HHMMSS>_<git-short-sha>/
#         beam/ backbone/ full/   每个含 res.json 与 selected_propagation_paths.json
#         run_meta.json           本次运行的完整配置与解析后的阈值
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

usage() { sed -n '2,39p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

DATA_ROOT="${PINGMESH_DATA}"
VARIANTS="beam,backbone,full"
ALIGN=0
EVALUATE=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --data) DATA_ROOT="$2"; shift 2 ;;
        --variants) VARIANTS="$2"; shift 2 ;;
        --align-thresholds) ALIGN=1; shift ;;
        --evaluate) EVALUATE=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "[ERROR] unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ ! -d "${DATA_ROOT}" ]]; then
    echo "[ERROR] data root not found: ${DATA_ROOT}" >&2
    echo "        set PINGMESH_DATA or pass --data DIR" >&2
    exit 1
fi

if [[ ! -f "${PINGMESH_M3_EVIDENCE_MODEL}" ]]; then
    echo "[ERROR] evidence model not found: ${PINGMESH_M3_EVIDENCE_MODEL}" >&2
    exit 1
fi

# 反解 null_weight，使实边门槛等于给定概率：logit(p) - prior_logit。
# 骨架求解器在 lift 空间比较权重，而 pipeline 的门槛习惯用概率表达。
aligned_null_weight() {
    "${PYTHON}" - "${PINGMESH_M3_ALIGN_PROBABILITY}" "${PINGMESH_M3_EVIDENCE_MODEL}" <<'PY'
import json, math, sys

probability, model_path = float(sys.argv[1]), sys.argv[2]
priors = json.load(open(model_path, encoding="utf-8"))["prior_by_edge_type"]
prior = float(priors.get("physical", priors["_default"]))


def logit(value):
    clipped = min(max(float(value), 1e-9), 1.0 - 1e-9)
    return math.log(clipped / (1.0 - clipped))


print(round(logit(probability) - logit(prior), 6))
PY
}

NULL_WEIGHT="${PINGMESH_M3_NULL_WEIGHT}"
if [[ "${ALIGN}" == "1" ]]; then
    if [[ "${DRY_RUN}" == "1" ]]; then
        NULL_WEIGHT="<aligned-to-${PINGMESH_M3_ALIGN_PROBABILITY}>"
    else
        NULL_WEIGHT="$(aligned_null_weight)"
    fi
fi

# 沿用 common.sh 的运行目录命名契约。dry-run 只预览路径，不落盘。
if [[ "${DRY_RUN}" == "1" ]]; then
    RUN_DIR="$(pingmesh_preview_run_dir m3_ablation)"
else
    RUN_DIR="$(pingmesh_create_run_dir m3_ablation)"
fi

# 权重文件只存在于服务器；缺失时不传，让 pipeline 用它自己的默认值。
WEIGHT_ARGS=()
if [[ -f "${PINGMESH_WEIGHTS_MANUAL}" ]]; then
    WEIGHT_ARGS=(--weight-file "${PINGMESH_WEIGHTS_MANUAL}")
fi

run_variant() {
    local name="$1"
    shift
    local out_dir="${RUN_DIR}/${name}"
    local cmd=(
        "${PYTHON}" Sys/RootCauseAnalyze/propagation_pipeline.py
        --data-root "${DATA_ROOT}"
        --output-dir "${out_dir}"
        --top-k "${PINGMESH_TOP_K}"
        --max-candidate-nodes "${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES}"
        --max-path-depth "${PINGMESH_PROPAGATION_MAX_PATH_DEPTH}"
        --stage1-weight "${PINGMESH_STAGE1_WEIGHT}"
        --edge-probability-method "${PINGMESH_M3_EVIDENCE_METHOD}"
        --edge-evidence-model "${PINGMESH_M3_EVIDENCE_MODEL}"
        "${WEIGHT_ARGS[@]+"${WEIGHT_ARGS[@]}"}"
        "$@"
    )
    if [[ "${DRY_RUN}" == "1" ]]; then
        echo "[DRY-RUN][${name}] ${cmd[*]}"
        return 0
    fi
    mkdir -p "${out_dir}"
    echo "[RUN][${name}] backbone=$*"
    "${cmd[@]}"
}

echo "============================================"
echo "  M3 backbone ablation"
echo "  run:          $(basename "${RUN_DIR}")"
echo "  data:         ${DATA_ROOT}"
echo "  evidence:     ${PINGMESH_M3_EVIDENCE_METHOD}"
echo "  null_weight:  ${NULL_WEIGHT}$([[ "${ALIGN}" == "1" ]] && echo "  (aligned, --align-thresholds)")"
echo "  aug. min p:   ${PINGMESH_M3_AUGMENTATION_MIN_PROBABILITY}"
echo "  variants:     ${VARIANTS}"
echo "  dry run:      ${DRY_RUN}"
echo "============================================"

for variant in ${VARIANTS//,/ }; do
    case "${variant}" in
        beam)
            run_variant beam --backbone-method beam_search_v1
            ;;
        backbone)
            run_variant backbone \
                --backbone-method "${PINGMESH_M3_BACKBONE_METHOD}" \
                --backbone-null-weight "${NULL_WEIGHT}" \
                --augmentation-min-probability "${PINGMESH_M3_AUGMENTATION_MIN_PROBABILITY}" \
                --no-dag-augmentation
            ;;
        full)
            run_variant full \
                --backbone-method "${PINGMESH_M3_BACKBONE_METHOD}" \
                --backbone-null-weight "${NULL_WEIGHT}" \
                --augmentation-min-probability "${PINGMESH_M3_AUGMENTATION_MIN_PROBABILITY}"
            ;;
        *)
            echo "[ERROR] unknown variant: ${variant} (expected beam|backbone|full)" >&2
            exit 2
            ;;
    esac
done

if [[ "${DRY_RUN}" == "1" ]]; then
    echo
    echo "Dry run completed; no propagation or evaluation command was executed."
    exit 0
fi

if [[ "${EVALUATE}" == "1" ]]; then
    EVAL_DIR="${RUN_DIR}/evaluation"
    mkdir -p "${EVAL_DIR}"
    for variant in ${VARIANTS//,/ }; do
        prediction_dir="${RUN_DIR}/${variant}"
        [[ -f "${prediction_dir}/res.json" ]] || continue
        "${PYTHON}" Sys/Score/Score_N.py "${prediction_dir}/res.json"
        "${PYTHON}" Sys/Score/evaluate_propagation.py \
            --predictions "${prediction_dir}/res.json" \
            --selected-paths "${prediction_dir}/selected_propagation_paths.json" \
            --out "${EVAL_DIR}/${variant}.json" \
            --labels-root "${PINGMESH_PROPAGATION_LABELS_ROOT}"
    done
fi

# 运行溯源：模型、阈值、commit 全部落盘，便于复现。
"${PYTHON}" - "${RUN_DIR}" "${DATA_ROOT}" "${NULL_WEIGHT}" "${ALIGN}" "${VARIANTS}" <<'PY'
import json, os, subprocess, sys

run_dir, data_root, null_weight, aligned, variants = sys.argv[1:6]


def git(*args):
    try:
        return subprocess.check_output(
            ["git", *args], cwd=run_dir, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


try:
    resolved_null_weight = float(null_weight)
except ValueError:
    resolved_null_weight = null_weight

meta = {
    "experiment": "m3_ablation",
    "data_root": data_root,
    "variants": [name for name in variants.split(",") if name],
    "backbone_method": os.environ.get("PINGMESH_M3_BACKBONE_METHOD"),
    "evidence_method": os.environ.get("PINGMESH_M3_EVIDENCE_METHOD"),
    "evidence_model": os.environ.get("PINGMESH_M3_EVIDENCE_MODEL"),
    "null_weight": resolved_null_weight,
    "thresholds_aligned": aligned == "1",
    "alignment_probability": float(os.environ.get("PINGMESH_M3_ALIGN_PROBABILITY", "0.25")),
    "augmentation_min_probability": float(
        os.environ.get("PINGMESH_M3_AUGMENTATION_MIN_PROBABILITY", "0.60")
    ),
    "top_k": int(os.environ.get("PINGMESH_TOP_K", "10")),
    "git_commit": git("rev-parse", "HEAD"),
    "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
}
with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as handle:
    json.dump(meta, handle, indent=2, ensure_ascii=False, sort_keys=True)
PY

"${PYTHON}" - "${RUN_DIR}" "${VARIANTS}" <<'PY'
import json, os, sys

run_dir, variants = sys.argv[1], sys.argv[2]
header = ("variant", "incident", "edges", "backbone", "augmented", "unreached", "coverage", "diagnosability")
rows = []
for name in [item for item in variants.split(",") if item]:
    path = os.path.join(run_dir, name, "res.json")
    if not os.path.exists(path):
        continue
    for case in json.load(open(path, encoding="utf-8")):
        prop = case.get("propagation") or {}
        diag = prop.get("diagnostics") or {}
        label = prop.get("diagnosability")
        if isinstance(label, dict):
            label = label.get("diagnosability")
        unreached = diag.get("unreached_nodes")
        rows.append((
            name,
            os.path.basename(str(case.get("dir", "")).replace("\\", "/").rstrip("/")),
            diag.get("selected_edge_count", "-"),
            diag.get("backbone_edge_count", "-"),
            diag.get("augmented_edge_count", "-"),
            len(unreached) if isinstance(unreached, list) else "-",
            prop.get("target_coverage", "-"),
            label,
        ))

if not rows:
    print("[WARN] no res.json found; nothing to summarise")
    sys.exit(0)

widths = [
    max(len(str(row[index])) for row in [header, *rows])
    for index in range(len(header))
]
print()
print("  ".join(str(header[i]).ljust(widths[i]) for i in range(len(header))))
print("-" * (sum(widths) + 2 * (len(header) - 1)))
for row in rows:
    print("  ".join(str(row[i]).ljust(widths[i]) for i in range(len(header))))
print()
PY

echo "Run directory: ${RUN_DIR}"
