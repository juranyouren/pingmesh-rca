#!/usr/bin/env bash
# ============================================================
# 集中配置 — 所有实验脚本 source 此文件，Sys/config.py 从这里读取。
#
# 这是服务器路径、模型路径、NPU 卡、数据路径与公共实验默认参数的唯一入口。
# 环境变量优先，未设置则使用默认值；请在命令行覆盖，不要改各个 runner。
#
# 用法:
#   source scripts/common.sh
#
#   # 切换数据集
#   export PINGMESH_DATA=/new/path
#   # 切换模型
#   export PINGMESH_MODEL_PATH=/new/model
#   # 切换 NPU 卡
#   export PINGMESH_NPU_CARDS=0,1,2,3,4,5,6,7
#   # 选择解释器
#   export PYTHON=/usr/bin/python3.10
#
# 只有被实际读取的变量才保留在这里；新增默认值前请确认有消费者。
# ============================================================

# ── 项目根目录 ──
PINGMESH_COMMON_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PINGMESH_DEFAULT_PROJECT_ROOT="$(cd -- "${PINGMESH_COMMON_DIR}/.." && pwd)"
export PINGMESH_PROJECT_ROOT="${PINGMESH_PROJECT_ROOT:-${PINGMESH_DEFAULT_PROJECT_ROOT}}"

# ── 解释器 ──
# RQ1 需要 Python 3.10；其余入口用默认 python 即可。
export PYTHON="${PYTHON:-python}"

# ── 数据路径 ──
export PINGMESH_DATA="${PINGMESH_DATA:-${PINGMESH_PROJECT_ROOT}/data/node/nodes_max_labeled}"
export PINGMESH_RAW_DATA="${PINGMESH_RAW_DATA:-${PINGMESH_PROJECT_ROOT}/data/raw/pingmesh_labeled}"
# 正式实验结果统一进入 res/；run 目录由 pingmesh_create_run_dir 自动创建。
export PINGMESH_RESULTS="${PINGMESH_RESULTS:-${PINGMESH_PROJECT_ROOT}/res}"

# ── 权重文件 ──
export PINGMESH_WEIGHTS_MANUAL="${PINGMESH_WEIGHTS_MANUAL:-${PINGMESH_PROJECT_ROOT}/data/weights/classified_alarms/all_alarms.json}"

# ── 模型 ──
# 服务器本地权重；不使用任何外部 LLM API。
export PINGMESH_MODEL_PATH="${PINGMESH_MODEL_PATH:-/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B}"

# ── NPU / 推理参数 ──
export PINGMESH_NPU_CARDS="${PINGMESH_NPU_CARDS:-4,5,6,7}"
export PINGMESH_TOP_K="${PINGMESH_TOP_K:-10}"
# vLLM 批大小：证据编码把所有「有记录」的设备合并进同一次 generate 调用，
# 单个 prompt 的批大小在解码时会被权重读取完全支配，故批处理是主要加速手段。
# 1 等价于逐条串行（旧行为）。
export PINGMESH_BATCH_SIZE="${PINGMESH_BATCH_SIZE:-8}"
export PINGMESH_TEMPERATURE="${PINGMESH_TEMPERATURE:-0.6}"
export PINGMESH_MAX_TOKENS="${PINGMESH_MAX_TOKENS:-4096}"
export PINGMESH_MAX_MODEL_LEN="${PINGMESH_MAX_MODEL_LEN:-16384}"

# ── 传播图重建 (anchor-conditioned reconstruction) ──
export PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES="${PINGMESH_PROPAGATION_MAX_CANDIDATE_NODES:-80}"
export PINGMESH_PROPAGATION_MAX_PATH_DEPTH="${PINGMESH_PROPAGATION_MAX_PATH_DEPTH:-8}"
export PINGMESH_STAGE1_WEIGHT="${PINGMESH_STAGE1_WEIGHT:-0.5}"
export PINGMESH_PROPAGATION_LABELS_ROOT="${PINGMESH_PROPAGATION_LABELS_ROOT:-${PINGMESH_PROJECT_ROOT}/data/propagation_labels}"

# ── M3 骨架重建 (anchor-conditioned backbone) ──
# 骨架求解器最大化方向证据之和，只有 logit_evidence_v1 可加，故 M3 变体固定用它。
export PINGMESH_M3_BACKBONE_METHOD="${PINGMESH_M3_BACKBONE_METHOD:-maximum_evidence_arborescence_v1}"
export PINGMESH_M3_EVIDENCE_METHOD="${PINGMESH_M3_EVIDENCE_METHOD:-logit_evidence_v1}"
export PINGMESH_M3_EVIDENCE_MODEL="${PINGMESH_M3_EVIDENCE_MODEL:-${PINGMESH_PROJECT_ROOT}/configs/propagation/evidence_logit_v1.json}"
# 空选项 (lift 空间)：0.0 = 需要净正证据。lift 与概率不在同一空间，
# 各 edge_type 的 prior 不同，所以这个标量表达不了统一的概率门槛。
export PINGMESH_M3_NULL_WEIGHT="${PINGMESH_M3_NULL_WEIGHT:-0.0}"
export PINGMESH_M3_AUGMENTATION_MIN_PROBABILITY="${PINGMESH_M3_AUGMENTATION_MIN_PROBABILITY:-0.60}"
# --align-thresholds 用这个概率反解 null_weight，使 M3 与 beam search 的门槛可比。
export PINGMESH_M3_ALIGN_PROBABILITY="${PINGMESH_M3_ALIGN_PROBABILITY:-0.25}"

# ── RQ1 (Baseline/RQ1) ──
export PINGMESH_RQ1_CONFIG="${PINGMESH_RQ1_CONFIG:-${PINGMESH_PROJECT_ROOT}/configs/baselines/rq1.json}"
export PINGMESH_RQ1_CONDITION="${PINGMESH_RQ1_CONDITION:-oracle}"
export PINGMESH_RQ1_MANIFEST="${PINGMESH_RQ1_MANIFEST:-}"
export PINGMESH_RQ1_GROUPS="${PINGMESH_RQ1_GROUPS:-}"
export PINGMESH_RQ1_ROOTS="${PINGMESH_RQ1_ROOTS:-}"
export PINGMESH_RQ1_FOLDS="${PINGMESH_RQ1_FOLDS:-5}"
export PINGMESH_RQ1_SEED="${PINGMESH_RQ1_SEED:-20260920}"
# record-count is an explicit exported-event counting assumption, not coverage proof.
export PINGMESH_RQ1_PCMCI_COVERAGE="${PINGMESH_RQ1_PCMCI_COVERAGE:-config}"
# possible-positive scores propagation 'possible' edges as confirmed directed GT,
# matching the historical scorer; set to strict to defer them to human review.
export PINGMESH_RQ1_LABEL_POLICY="${PINGMESH_RQ1_LABEL_POLICY:-possible-positive}"
# The annotation tool never emitted `graph_complete`, so every propagation label it
# produced is a complete ground-truth reference even though the key is absent. Default
# to all-complete; set to as-declared to honour the key strictly and withhold SHD on a
# reference that does not declare itself complete.
export PINGMESH_RQ1_LABEL_COMPLETENESS="${PINGMESH_RQ1_LABEL_COMPLETENESS:-all-complete}"

# ── Experiment run directories ──
# Run IDs are generated centrally so every entrypoint follows the same naming
# contract: <experiment>_<variant>_<YYYYMMDD_HHMMSS>_<git-short-sha>[_NN].
pingmesh_git_short_sha() {
    git -C "${PINGMESH_PROJECT_ROOT}" rev-parse --short HEAD 2>/dev/null || printf '%s\n' "nogit"
}

pingmesh_preview_run_dir() {
    local experiment="$1"
    local variant="${2:-}"
    local timestamp sha stem candidate suffix

    timestamp="$(date +%Y%m%d_%H%M%S)"
    sha="$(pingmesh_git_short_sha)"
    stem="${experiment}"
    if [[ -n "${variant}" ]]; then
        stem="${stem}_${variant}"
    fi
    stem="${stem}_${timestamp}_${sha}"
    candidate="${PINGMESH_RESULTS}/${stem}"
    suffix=1
    while [[ -e "${candidate}" ]]; do
        candidate="${PINGMESH_RESULTS}/${stem}_$(printf '%02d' "${suffix}")"
        suffix=$((suffix + 1))
    done
    printf '%s\n' "${candidate}"
}

pingmesh_create_run_dir() {
    local experiment="$1"
    local variant="${2:-}"
    local candidate

    mkdir -p "${PINGMESH_RESULTS}"
    candidate="$(pingmesh_preview_run_dir "${experiment}" "${variant}")"
    while ! mkdir "${candidate}" 2>/dev/null; do
        if [[ ! -e "${candidate}" ]]; then
            echo "[ERROR] Cannot create run directory: ${candidate}" >&2
            return 1
        fi
        candidate="$(pingmesh_preview_run_dir "${experiment}" "${variant}")"
    done
    printf '%s\n' "${candidate}"
}
