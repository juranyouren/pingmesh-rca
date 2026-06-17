#!/usr/bin/env bash
# ============================================================
# Skill 消融实验 — 纯算法，不依赖 LLM/NPU
#
# 组合: [1] topo, [2] temporal, [1,2] topo+temporal
#       每组合 × 2 权重来源 (人工 / LLM学习)
#       共 6 组
#
# 用法:
#   ./scripts/run_full_ablation.sh
#   ./scripts/run_full_ablation.sh /path/to/data
# ============================================================
set -euo pipefail

PROJECT_ROOT="/home/sbp/lixinyang/pingmesh"
DATA="${1:-${PROJECT_ROOT}/data/nodes_labeled}"
RES="${PROJECT_ROOT}/data/res"

WEIGHT_MANUAL="${PROJECT_ROOT}/data/weights/classified_alarms/all_alarms.json"
WEIGHT_LLM="${PROJECT_ROOT}/data/weights/alarm_weights.json"

PREFIX="ablation"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
WORKDIR="${RES}/${PREFIX}_${TIMESTAMP}"
SUMMARY="${WORKDIR}/summary.json"

mkdir -p "${WORKDIR}"

echo "============================================"
echo "  Skill 消融实验 (topo + temporal)"
echo "  数据: ${DATA}"
echo "  结果: ${WORKDIR}"
echo "============================================"

cd "${PROJECT_ROOT}"

# ── 3 skill组合 × 2 权重 = 6 组 ──
COMBOS=(
    "1|topo"
    "2|temporal"
    "1 2|topo_temporal"
)

WEIGHTS=(
    "manual|${WEIGHT_MANUAL}"
    "llm|${WEIGHT_LLM}"
)

for combo in "${COMBOS[@]}"; do
    IFS="|" read -r skills tag <<< "${combo}"

    for wvar in "${WEIGHTS[@]}"; do
        IFS="|" read -r wtag wpath <<< "${wvar}"

        out_dir="${PREFIX}_${TIMESTAMP}/${tag}__w_${wtag}"

        echo ""
        echo "=== ${tag} w=[${wtag}] ==="

        python Sys/RootCauseAnalyze/skill_pipeline.py \
            -d "${DATA}" \
            -s ${skills} \
            -k 5 \
            -w "${wpath}" \
            -o "${out_dir}" 2>&1 | tail -3

        res_json="${RES}/${out_dir}/res.json"
        if [ ! -f "${res_json}" ]; then
            echo "  [ERROR] res.json 不存在"
            continue
        fi

        python -c "
import json, os, sys
sys.path.insert(0, '${PROJECT_ROOT}')
from Sys.Score.Score_N import Scorer
s = Scorer('${res_json}')
summary = s.calculate_metrics()
m = summary['skill_evaluation']['ranking_metrics']

with open('${RES}/${out_dir}/_metrics.json', 'w') as f:
    json.dump({
        'tag': '${tag}',
        'skills': '${skills}',
        'directed': True,
        'weight_source': '${wtag}',
        'total_cases': m.get('Total Evaluated Cases', 0),
        'top1': m.get('Top-1 Acc (%)', 0),
        'top2': m.get('Top-2 Acc (%)', 0),
        'top3': m.get('Top-3 Acc (%)', 0),
        'top4': m.get('Top-4 Acc (%)', 0),
        'top5': m.get('Top-5 Acc (%)', 0),
    }, f, ensure_ascii=False, indent=2)
" 2>&1 | tail -3

    done
done

# ── 汇总 ──
echo ""
echo "========================================="
echo "  汇总到 ${SUMMARY}"
echo "========================================="

python -c "
import json, os, glob
workdir = '${WORKDIR}'
rows = []
for tag_dir in sorted(os.listdir(workdir)):
    mfile = os.path.join(workdir, tag_dir, '_metrics.json')
    if not os.path.exists(mfile):
        mfile2 = os.path.join('${RES}', workdir, tag_dir, '_metrics.json')
        if os.path.exists(mfile2): mfile = mfile2
        else: continue
    try:
        with open(mfile, 'r') as f: rows.append(json.load(f))
    except Exception as e: print(f'  skip {tag_dir}: {e}')

rows.sort(key=lambda r: r.get('top1', 0), reverse=True)

summary = {
    'timestamp': '${TIMESTAMP}',
    'total_combinations': len(rows),
    'results': rows,
}

with open('${SUMMARY}', 'w') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print()
print('=== 最终排名（按 Top-1 降序） ===')
print(f'{\"#\":<3} {\"组合\":<22} {\"权重\":<7} {\"Top-1\":<8} {\"Top-3\":<8} {\"Top-5\":<8} {\"样本\":<6}')
print('-' * 60)
for i, r in enumerate(rows, 1):
    print(f'{i:<3} {r[\"tag\"]:<22} {r.get(\"weight_source\",\"-\"):<7} '
          f'{r[\"top1\"]:<8.2f} {r[\"top3\"]:<8.2f} {r[\"top5\"]:<8.2f} '
          f'{r[\"total_cases\"]:<6}')

print()
print(f'汇总文件: ${SUMMARY}')
"