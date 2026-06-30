#!/usr/bin/env bash
# ============================================================
# Run the four main RCA experiment paths:
#   1. gate+pipe+llm : deterministic pipe, trust-tree gate, LLM only when routed
#   2. gate+pipe     : deterministic pipe plus trust-tree gate, no LLM call
#   3. pipe+llm      : deterministic pipe evidence, always send to LLM reranking
#   4. pipe          : deterministic fused ranking only
#
# Configuration comes from scripts/common.sh and environment variables.
#
# Usage:
#   ./scripts/run_gate_pipe_experiments.sh
#   ./scripts/run_gate_pipe_experiments.sh my_prefix
#
# Optional:
#   PINGMESH_EXPERIMENTS="pipe gate_pipe" ./scripts/run_gate_pipe_experiments.sh
#   PINGMESH_DATA=/path/to/data ./scripts/run_gate_pipe_experiments.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

PREFIX="${1:-gate_pipe_experiments}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_TAG="${PREFIX}_${TIMESTAMP}"
WORKDIR="${PINGMESH_RESULTS}/${RUN_TAG}"
SUMMARY_JSON="${WORKDIR}/summary.json"
SUMMARY_CSV="${WORKDIR}/summary.csv"
EXPERIMENTS="${PINGMESH_EXPERIMENTS:-gate_pipe_llm gate_pipe pipe_llm pipe}"
SKILLS="${PINGMESH_SKILLS:-1 2}"
TOPK="${PINGMESH_TOP_K:-5}"
BATCH="${PINGMESH_BATCH_SIZE:-8}"
NPU="${PINGMESH_NPU_CARDS:-0,1,2,3,4,5,6,7}"
WEIGHT_FILE="${PINGMESH_WEIGHTS_MANUAL}"

mkdir -p "${WORKDIR}"

has_experiment() {
    local target="$1"
    for item in ${EXPERIMENTS}; do
        if [ "${item}" = "${target}" ]; then
            return 0
        fi
    done
    return 1
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

echo "============================================"
echo "  Gate/Pipe/LLM experiments"
echo "  data:       ${PINGMESH_DATA}"
echo "  results:    ${WORKDIR}"
echo "  experiments:${EXPERIMENTS}"
echo "  skills:     ${SKILLS}"
echo "  top_k:      ${TOPK}"
echo "  npu:        ${NPU}"
echo "  weights:    ${WEIGHT_FILE}"
echo "============================================"

PIPE_OUTDIR="${RUN_TAG}/pipe"
PIPE_RESDIR="${PINGMESH_RESULTS}/${PIPE_OUTDIR}"
PIPE_RES="${PIPE_RESDIR}/res.json"

if has_experiment pipe || has_experiment gate_pipe; then
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

if has_experiment gate_pipe; then
    echo ""
    echo "=== [gate+pipe] trust gate without LLM ==="
    GATE_PIPE_RESDIR="${WORKDIR}/gate_pipe"
    mkdir -p "${GATE_PIPE_RESDIR}"
    python Sys/Score/apply_trust_gate.py \
        --res "${PIPE_RES}" \
        --out "${GATE_PIPE_RESDIR}/res.json"
    python Sys/Score/evaluate_trust_gate.py \
        --res "${PIPE_RES}" \
        --out-dir "${GATE_PIPE_RESDIR}/trust_gate_eval"
    score_res "${GATE_PIPE_RESDIR}/res.json"
fi

if has_experiment pipe_llm; then
    echo ""
    echo "=== [pipe+llm] pipe evidence with LLM reranking ==="
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
    echo "=== [gate+pipe+llm] gated pipe with LLM arbitration ==="
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

python -c "
import csv, json, os

workdir = '${WORKDIR}'
experiments = ['gate_pipe_llm', 'gate_pipe', 'pipe_llm', 'pipe']
rows = []

def metric_block(summary, key):
    block = (summary.get(key) or {}).get('ranking_metrics') or {}
    return {
        'total_cases': block.get('Total Evaluated Cases', 0),
        'top1': block.get('Top-1 Acc (%)', 0),
        'top3': block.get('Top-3 Acc (%)', 0),
        'top5': block.get('Top-5 Acc (%)', 0),
    }

for name in experiments:
    path = os.path.join(workdir, name, 'sum.json')
    if not os.path.exists(path):
        continue
    with open(path, encoding='utf-8') as f:
        summary = json.load(f)
    eval_key = 'skill_evaluation' if name in {'pipe', 'gate_pipe'} else 'llm_evaluation'
    row = {'experiment': name, 'primary_metric': eval_key, **metric_block(summary, eval_key)}
    rows.append(row)

with open('${SUMMARY_JSON}', 'w', encoding='utf-8') as f:
    json.dump({'workdir': workdir, 'results': rows}, f, ensure_ascii=False, indent=2)

with open('${SUMMARY_CSV}', 'w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['experiment', 'primary_metric', 'total_cases', 'top1', 'top3', 'top5'])
    writer.writeheader()
    writer.writerows(rows)

print()
print('=== Experiment Summary ===')
print(f'{\"experiment\":<16} {\"metric\":<16} {\"cases\":<8} {\"top1\":<8} {\"top3\":<8} {\"top5\":<8}')
print('-' * 72)
for row in rows:
    print(f'{row[\"experiment\"]:<16} {row[\"primary_metric\"]:<16} {row[\"total_cases\"]:<8} '
          f'{row[\"top1\"]:<8.2f} {row[\"top3\"]:<8.2f} {row[\"top5\"]:<8.2f}')
print()
print('summary_json:', '${SUMMARY_JSON}')
print('summary_csv: ', '${SUMMARY_CSV}')
"
