#!/usr/bin/env bash
# ============================================================
# 完整 Skill 消融实验
# 维度: Skill 组合 × 有向/无向(含 topo 时) × 告警权重来源
#
# 告警权重文件:
#   all_alarms.json = 人工总结
#   alarm_weights.json = 大模型总结 (AlarmWeightBuilder)
#
# 总共 22 组, 全部结果汇总到 summary.json
#
# 用法:
#   ./scripts/run_full_ablation.sh
#   ./scripts/run_full_ablation.sh /path/to/data
# ============================================================
set -euo pipefail

PROJECT_ROOT="/home/sbp/lixinyang/pingmesh"
DATA="${1:-${PROJECT_ROOT}/data/nodes_labeled}"
RES="${PROJECT_ROOT}/data/res"

# 两种告警权重
WEIGHT_MANUAL="${PROJECT_ROOT}/data/weights/classified_alarms/all_alarms.json"
WEIGHT_LLM="${PROJECT_ROOT}/data/weights/alarm_weights.json"

PREFIX="full_ablation"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
WORKDIR="${RES}/${PREFIX}_${TIMESTAMP}"
SUMMARY="${WORKDIR}/summary.json"

mkdir -p "${WORKDIR}"

echo "============================================"
echo "  完整 Skill 消融实验 (含权重消融)"
echo "  数据:       ${DATA}"
echo "  结果:       ${WORKDIR}"
echo "  人工权重:   ${WEIGHT_MANUAL}"
echo "  大模型权重: ${WEIGHT_LLM}"
echo "============================================"

cd "${PROJECT_ROOT}"

# ── 定义组合: "skill_ids|directed_flag|tag_suffix" ──
# directed_flag: "undir" / "dir" / "none"

COMBOS=(
    "1|undir|topo_undir"
    "1|dir|topo_dir"
    "2|none|co_occur"
    "3|none|temporal"
    "1 2|undir|topo_co_undir"
    "1 2|dir|topo_co_dir"
    "1 3|undir|topo_temporal_undir"
    "1 3|dir|topo_temporal_dir"
    "2 3|none|co_temporal"
    "1 2 3|undir|all_undir"
    "1 2 3|dir|all_dir"
)

# 权重变体
WEIGHT_VARIANTS=(
    "manual|${WEIGHT_MANUAL}"
    "llm|${WEIGHT_LLM}"
)

# ── 逐个运行 ──

for combo in "${COMBOS[@]}"; do
    IFS="|" read -r skills dflag tag <<< "${combo}"

    for wvar in "${WEIGHT_VARIANTS[@]}"; do
        IFS="|" read -r wtag wpath <<< "${wvar}"

        dir_flag=""
        if [ "${dflag}" = "dir" ]; then
            dir_flag="--directed"
        fi

        out_dir="${PREFIX}_${TIMESTAMP}/${tag}__w_${wtag}"

        echo ""
        echo "========================================="
        echo "  [${tag}] w=[${wtag}] skills=${skills} ${dir_flag}"
        echo "========================================="

        # ── 步骤 1: 跑 skill pipeline ──
        python Sys/RootCauseAnalyze/skill_pipeline.py \
            -d "${DATA}" \
            -s ${skills} \
            ${dir_flag} \
            -k 5 \
            -w "${wpath}" \
            -o "${out_dir}" 2>&1 | tail -3

        # ── 步骤 2: 评分 ──
        res_json="${RES}/${out_dir}/res.json"
        if [ ! -f "${res_json}" ]; then
            echo "  [ERROR] res.json 不存在，跳过评分"
            continue
        fi

        python -c "
import json, os, sys
sys.path.insert(0, '${PROJECT_ROOT}')
from Sys.Score.Score_N import Scorer, LlmTextParser

s = Scorer('${res_json}')
summary = s.calculate_metrics()

all_metrics = summary.get('draft_evaluation', {}).get('all', {})
rm = all_metrics.get('ranking_metrics', {})

with open('${RES}/${out_dir}/_metrics.json', 'w') as f:
    json.dump({
        'tag': '${tag}',
        'skills': '${skills}',
        'directed': '${dflag}' not in ['undir', 'none'],
        'weight_source': '${wtag}',
        'total_cases': rm.get('Total Evaluated Cases', 0),
        'top1': rm.get('Top-1 Acc (%)', 0),
        'top2': rm.get('Top-2 Acc (%)', 0),
        'top3': rm.get('Top-3 Acc (%)', 0),
        'top4': rm.get('Top-4 Acc (%)', 0),
        'top5': rm.get('Top-5 Acc (%)', 0),
        'failed_count': all_metrics.get('failed_cases_count', 0),
    }, f, ensure_ascii=False, indent=2)
" 2>&1 | tail -3

    done
done

# ── 汇总到 summary.json ──
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
        # 可能是结果子目录
        mfile2 = os.path.join('${RES}', workdir, tag_dir, '_metrics.json')
        if os.path.exists(mfile2):
            mfile = mfile2
        else:
            continue
    try:
        with open(mfile, 'r') as f:
            row = json.load(f)
            rows.append(row)
    except Exception as e:
        print(f'  skip {tag_dir}: {e}')

# 按 top1 降序排列
rows.sort(key=lambda r: r.get('top1', 0), reverse=True)

summary = {
    'timestamp': '${TIMESTAMP}',
    'data_root': '${DATA}',
    'weight_manual': '${WEIGHT_MANUAL}',
    'weight_llm': '${WEIGHT_LLM}',
    'total_combinations': len(rows),
    'results': rows,
}

with open('${SUMMARY}', 'w') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

# 打印排名表
print()
print('=== 最终排名（按 Top-1 降序） ===')
print(f'{\"#\":<3} {\"组合\":<24} {\"权重\":<7} {\"有向\":<4} {\"Top-1\":<8} {\"Top-3\":<8} {\"Top-5\":<8} {\"样本\":<6}')
print('-' * 74)
for i, r in enumerate(rows, 1):
    print(f'{i:<3} {r[\"tag\"]:<24} {r.get(\"weight_source\",\"-\"):<7} '
          f'{str(r.get(\"directed\",\"-\")):<4} '
          f'{r[\"top1\"]:<8.2f} {r[\"top3\"]:<8.2f} {r[\"top5\"]:<8.2f} '
          f'{r[\"total_cases\"]:<6}')

print()
print(f'汇总文件: ${SUMMARY}')
"