#!/usr/bin/env bash
# ============================================================
# Unified RCA experiment runner.
#
# Edit the experiment list below, or override it with PINGMESH_EXPERIMENTS.
#
# Available experiments:
#   pipe                  deterministic fused ranking only
#   gate_eval             evaluate trust-tree gate routing on pipe result
#   gate_pipe             apply gate without LLM; LLM/operator routes stay empty
#   pipe_llm              pipe evidence -> main LLM reranking
#   gate_pipe_llm         pipe evidence -> gate -> main LLM only for routed cases
#   pipe_summary_llm      pipe evidence -> small-model NODES summary -> main LLM
#   gate_pipe_summary_llm pipe evidence -> gate -> summary -> main LLM routed cases
#
# Typical runs:
#   ./scripts/run_gate_pipe_experiments.sh
#   ./scripts/run_gate_pipe_experiments.sh my_prefix
#   PINGMESH_EXPERIMENTS="pipe gate_eval gate_pipe" ./scripts/run_gate_pipe_experiments.sh
#
# Summary experiments require:
#   export PINGMESH_SUMMARY_MODEL_PATH=/path/to/1.5B-model
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

# ---------------- user-editable experiment config ----------------
RUN_EXPERIMENTS="${PINGMESH_EXPERIMENTS:-pipe gate_eval gate_pipe pipe_llm gate_pipe_llm}"
# To include small-model summary experiments, for example:
# RUN_EXPERIMENTS="${PINGMESH_EXPERIMENTS:-pipe gate_eval pipe_summary_llm gate_pipe_summary_llm}"
# -----------------------------------------------------------------

PREFIX="${1:-gate_pipe_experiments}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_TAG="${PREFIX}_${TIMESTAMP}"
WORKDIR="${PINGMESH_RESULTS}/${RUN_TAG}"
SUMMARY_JSON="${WORKDIR}/summary.json"
SUMMARY_CSV="${WORKDIR}/summary.csv"
GATE_EFFECT_JSON="${WORKDIR}/gate_effectiveness.json"
GATE_EFFECT_CSV="${WORKDIR}/gate_effectiveness.csv"

SKILLS="${PINGMESH_SKILLS:-1 2}"
TOPK="${PINGMESH_TOP_K:-5}"
BATCH="${PINGMESH_BATCH_SIZE:-8}"
NPU="${PINGMESH_NPU_CARDS:-0,1,2,3,4,5,6,7}"
WEIGHT_FILE="${PINGMESH_WEIGHTS_MANUAL}"
SUMMARY_MODEL_PATH="${PINGMESH_SUMMARY_MODEL_PATH:-}"
SUMMARY_NPU_CARDS="${PINGMESH_SUMMARY_NPU_CARDS:-}"
SUMMARY_MAX_TOKENS="${PINGMESH_SUMMARY_MAX_TOKENS:-1024}"

mkdir -p "${WORKDIR}"

has_experiment() {
    local target="$1"
    for item in ${RUN_EXPERIMENTS}; do
        if [ "${item}" = "${target}" ]; then
            return 0
        fi
    done
    return 1
}

needs_pipe_result() {
    has_experiment pipe || has_experiment gate_eval || has_experiment gate_pipe
}

needs_summary_model() {
    has_experiment pipe_summary_llm || has_experiment gate_pipe_summary_llm
}

score_res() {
    local res_json="$1"
    python -c "
import json
from Sys.Score.Score_N import Scorer
s = Scorer('${res_json}')
summary = s.calculate_metrics()
print(json.dumps(summary, ensure_ascii=False, indent=2))
"
}

summary_args=()
build_summary_args() {
    if [ -z "${SUMMARY_MODEL_PATH}" ]; then
        echo "[ERROR] summary experiments require PINGMESH_SUMMARY_MODEL_PATH." >&2
        exit 1
    fi
    summary_args=(--summarize-nodes --summary-model-path "${SUMMARY_MODEL_PATH}" --summary-max-tokens "${SUMMARY_MAX_TOKENS}")
    if [ -n "${SUMMARY_NPU_CARDS}" ]; then
        summary_args+=(--summary-npu-cards "${SUMMARY_NPU_CARDS}")
    fi
}

echo "============================================"
echo "  Unified Gate/Pipe/LLM experiments"
echo "  data:          ${PINGMESH_DATA}"
echo "  results:       ${WORKDIR}"
echo "  experiments:   ${RUN_EXPERIMENTS}"
echo "  skills:        ${SKILLS}"
echo "  top_k:         ${TOPK}"
echo "  npu:           ${NPU}"
echo "  weights:       ${WEIGHT_FILE}"
echo "  summary_model: ${SUMMARY_MODEL_PATH:-<unset>}"
echo "============================================"

if needs_summary_model; then
    build_summary_args
fi

PIPE_OUTDIR="${RUN_TAG}/pipe"
PIPE_RESDIR="${PINGMESH_RESULTS}/${PIPE_OUTDIR}"
PIPE_RES="${PIPE_RESDIR}/res.json"

if needs_pipe_result; then
    echo ""
    echo "=== [pipe] deterministic fused ranking ==="
    python Sys/RootCauseAnalyze/skill_pipeline.py \
        -d "${PINGMESH_DATA}" \
        -s ${SKILLS} \
        -k "${TOPK}" \
        -w "${WEIGHT_FILE}" \
        -o "${PIPE_OUTDIR}"
    score_res "${PIPE_RES}"
fi

if has_experiment gate_eval; then
    echo ""
    echo "=== [gate_eval] validate trust-tree gate routing ==="
    python Sys/Score/evaluate_trust_gate.py \
        --res "${PIPE_RES}" \
        --out-dir "${WORKDIR}/gate_eval"
fi

if has_experiment gate_pipe; then
    echo ""
    echo "=== [gate_pipe] trust gate without LLM ==="
    GATE_PIPE_RESDIR="${WORKDIR}/gate_pipe"
    mkdir -p "${GATE_PIPE_RESDIR}"
    python Sys/Score/apply_trust_gate.py \
        --res "${PIPE_RES}" \
        --out "${GATE_PIPE_RESDIR}/res.json"
    score_res "${GATE_PIPE_RESDIR}/res.json"
fi

if has_experiment pipe_llm; then
    echo ""
    echo "=== [pipe_llm] pipe evidence with LLM reranking ==="
    python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
        -d "${PINGMESH_DATA}" \
        -s ${SKILLS} \
        -n "${NPU}" \
        -b "${BATCH}" \
        -k "${TOPK}" \
        -o "${RUN_TAG}/pipe_llm"
    score_res "${WORKDIR}/pipe_llm/res.json"
fi

if has_experiment gate_pipe_llm; then
    echo ""
    echo "=== [gate_pipe_llm] gated pipe with LLM arbitration ==="
    python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
        -d "${PINGMESH_DATA}" \
        -s ${SKILLS} \
        -n "${NPU}" \
        -b "${BATCH}" \
        -k "${TOPK}" \
        -o "${RUN_TAG}/gate_pipe_llm" \
        --confidence-gate
    score_res "${WORKDIR}/gate_pipe_llm/res.json"
fi

if has_experiment pipe_summary_llm; then
    echo ""
    echo "=== [pipe_summary_llm] small-model NODES summary with LLM reranking ==="
    python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
        -d "${PINGMESH_DATA}" \
        -s ${SKILLS} \
        -n "${NPU}" \
        -b "${BATCH}" \
        -k "${TOPK}" \
        -o "${RUN_TAG}/pipe_summary_llm" \
        "${summary_args[@]}"
    score_res "${WORKDIR}/pipe_summary_llm/res.json"
fi

if has_experiment gate_pipe_summary_llm; then
    echo ""
    echo "=== [gate_pipe_summary_llm] gated pipe with small-model NODES summary and LLM arbitration ==="
    python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
        -d "${PINGMESH_DATA}" \
        -s ${SKILLS} \
        -n "${NPU}" \
        -b "${BATCH}" \
        -k "${TOPK}" \
        -o "${RUN_TAG}/gate_pipe_summary_llm" \
        "${summary_args[@]}" \
        --confidence-gate
    score_res "${WORKDIR}/gate_pipe_summary_llm/res.json"
fi

python -c "
import csv, json, os

workdir = '${WORKDIR}'
experiments = ['pipe', 'gate_pipe', 'pipe_llm', 'gate_pipe_llm', 'pipe_summary_llm', 'gate_pipe_summary_llm']
rows = []

def metric_block(summary, key):
    block = (summary.get(key) or {}).get('ranking_metrics') or {}
    return {
        'total_cases': block.get('Total Evaluated Cases', 0),
        'top1': block.get('Top-1 Acc (%)', 0),
        'top3': block.get('Top-3 Acc (%)', 0),
        'top5': block.get('Top-5 Acc (%)', 0),
    }

def read_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)

metrics = {}
for name in experiments:
    summary = read_json(os.path.join(workdir, name, 'sum.json'))
    if not summary:
        continue
    eval_key = 'skill_evaluation' if name in {'pipe', 'gate_pipe'} else 'llm_evaluation'
    row = {'experiment': name, 'primary_metric': eval_key, **metric_block(summary, eval_key)}
    metrics[name] = row
    rows.append(row)

with open('${SUMMARY_JSON}', 'w', encoding='utf-8') as f:
    json.dump({'workdir': workdir, 'results': rows}, f, ensure_ascii=False, indent=2)

with open('${SUMMARY_CSV}', 'w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['experiment', 'primary_metric', 'total_cases', 'top1', 'top3', 'top5'])
    writer.writeheader()
    writer.writerows(rows)

gate_summary = read_json(os.path.join(workdir, 'gate_eval', 'trust_gate_summary.json'))
effect = {
    'workdir': workdir,
    'gate_eval_available': bool(gate_summary),
    'metrics': metrics,
}

if gate_summary:
    total = gate_summary.get('total_cases') or 0
    route_counts = gate_summary.get('route_counts') or {}
    route_metrics = gate_summary.get('route_metrics') or []
    auto_routes = {'combined', 'topo', 'temporal'}
    auto_n = sum((route_counts.get(route) or 0) for route in auto_routes)
    llm_n = route_counts.get('llm') or 0
    operator_n = route_counts.get('operator') or 0

    weighted_hits = 0.0
    weighted_n = 0
    by_route = {}
    for row in route_metrics:
        route = row.get('route')
        by_route[route] = row
        if route in auto_routes and row.get('top1') is not None:
            n = row.get('labeled_n') or 0
            weighted_hits += float(row['top1']) * n
            weighted_n += n

    gate_effect = {
        'total_cases': total,
        'route_counts': route_counts,
        'route_metrics': route_metrics,
        'auto_accept_cases': auto_n,
        'auto_accept_coverage': round(auto_n / total, 6) if total else 0.0,
        'llm_call_cases': llm_n,
        'llm_call_coverage': round(llm_n / total, 6) if total else 0.0,
        'operator_review_cases': operator_n,
        'operator_review_coverage': round(operator_n / total, 6) if total else 0.0,
        'auto_accept_top1': round(weighted_hits / weighted_n, 6) if weighted_n else None,
        'invoke_llm_top1_miss_gt_in_top3_cases': gate_summary.get('invoke_llm_top1_miss_gt_in_top3_cases', 0),
        'operator_review_miss_top5_cases': gate_summary.get('operator_review_miss_top5_cases', 0),
    }

    pipe = metrics.get('pipe', {})
    gate_pipe = metrics.get('gate_pipe', {})
    pipe_llm = metrics.get('pipe_llm', {})
    gate_pipe_llm = metrics.get('gate_pipe_llm', {})
    pipe_summary_llm = metrics.get('pipe_summary_llm', {})
    gate_pipe_summary_llm = metrics.get('gate_pipe_summary_llm', {})

    def delta(a, b):
        return round(float(a) - float(b), 2) if a not in (None, '') and b not in (None, '') else None

    gate_effect.update({
        'pipe_top1': pipe.get('top1'),
        'gate_pipe_top1': gate_pipe.get('top1'),
        'pipe_llm_top1': pipe_llm.get('top1'),
        'gate_pipe_llm_top1': gate_pipe_llm.get('top1'),
        'pipe_summary_llm_top1': pipe_summary_llm.get('top1'),
        'gate_pipe_summary_llm_top1': gate_pipe_summary_llm.get('top1'),
        'gate_pipe_vs_pipe_top1_delta': delta(gate_pipe.get('top1'), pipe.get('top1')) if gate_pipe and pipe else None,
        'gate_pipe_llm_vs_pipe_llm_top1_delta': delta(gate_pipe_llm.get('top1'), pipe_llm.get('top1')) if gate_pipe_llm and pipe_llm else None,
        'gate_pipe_summary_llm_vs_pipe_summary_llm_top1_delta': (
            delta(gate_pipe_summary_llm.get('top1'), pipe_summary_llm.get('top1'))
            if gate_pipe_summary_llm and pipe_summary_llm else None
        ),
        'gate_cost_useful': llm_n < total if total else None,
        'gate_final_llm_useful': (
            gate_pipe_llm.get('top1') is not None and pipe_llm.get('top1') is not None
            and gate_pipe_llm.get('top1') >= pipe_llm.get('top1')
            and llm_n < total
        ) if gate_pipe_llm and pipe_llm else None,
    })
    effect['gate_effectiveness'] = gate_effect

    with open('${GATE_EFFECT_JSON}', 'w', encoding='utf-8') as f:
        json.dump(gate_effect, f, ensure_ascii=False, indent=2)

    with open('${GATE_EFFECT_CSV}', 'w', encoding='utf-8', newline='') as f:
        fields = [
            'total_cases', 'auto_accept_cases', 'auto_accept_coverage', 'auto_accept_top1',
            'llm_call_cases', 'llm_call_coverage', 'operator_review_cases', 'operator_review_coverage',
            'pipe_top1', 'gate_pipe_top1', 'gate_pipe_vs_pipe_top1_delta',
            'pipe_llm_top1', 'gate_pipe_llm_top1', 'gate_pipe_llm_vs_pipe_llm_top1_delta',
            'pipe_summary_llm_top1', 'gate_pipe_summary_llm_top1',
            'gate_pipe_summary_llm_vs_pipe_summary_llm_top1_delta',
            'invoke_llm_top1_miss_gt_in_top3_cases', 'operator_review_miss_top5_cases',
            'gate_cost_useful', 'gate_final_llm_useful',
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerow({field: gate_effect.get(field) for field in fields})

print()
print('=== Experiment Summary ===')
print(f'{\"experiment\":<24} {\"metric\":<16} {\"cases\":<8} {\"top1\":<8} {\"top3\":<8} {\"top5\":<8}')
print('-' * 88)
for row in rows:
    print(f'{row[\"experiment\"]:<24} {row[\"primary_metric\"]:<16} {row[\"total_cases\"]:<8} '
          f'{row[\"top1\"]:<8.2f} {row[\"top3\"]:<8.2f} {row[\"top5\"]:<8.2f}')

if gate_summary:
    g = effect['gate_effectiveness']
    print()
    print('=== Gate Effectiveness ===')
    print(f'auto_accept_coverage: {g[\"auto_accept_coverage\"]:.4f}, auto_accept_top1: {g[\"auto_accept_top1\"]}')
    print(f'llm_call_coverage:    {g[\"llm_call_coverage\"]:.4f}, operator_review_coverage: {g[\"operator_review_coverage\"]:.4f}')
    print(f'gate_pipe_vs_pipe_top1_delta: {g[\"gate_pipe_vs_pipe_top1_delta\"]}')
    print(f'gate_pipe_llm_vs_pipe_llm_top1_delta: {g[\"gate_pipe_llm_vs_pipe_llm_top1_delta\"]}')
    print(f'gate_cost_useful: {g[\"gate_cost_useful\"]}, gate_final_llm_useful: {g[\"gate_final_llm_useful\"]}')
    print('gate_effect_json:', '${GATE_EFFECT_JSON}')
    print('gate_effect_csv: ', '${GATE_EFFECT_CSV}')

print()
print('summary_json:', '${SUMMARY_JSON}')
print('summary_csv: ', '${SUMMARY_CSV}')
"
