#!/usr/bin/env bash
# ============================================================
# 完整 Skill 消融实验 — 遍历所有可能组合，汇总到单 JSON
#
# 组合空间:
#   skill_id ∈ {1-topo, 2-co_occur, 3-temporal}
#   含 skill=1 的组合 → 无向 + 有向各跑一次
#   不含 skill=1 的组合 → 跑一次
#
# 共 11 组:
#   [1]undir  [1]dir  [2]  [3]
#   [1,2]undir  [1,2]dir  [1,3]undir  [1,3]dir  [2,3]
#   [1,2,3]undir  [1,2,3]dir
#
# 用法:
#   ./scripts/run_full_ablation.sh              # 默认跑全部
#   ./scripts/run_full_ablation.sh /path/to/data  # 指定数据目录
# ============================================================
set -euo pipefail

PROJECT_ROOT="/home/sbp/lixinyang/pingmesh"
DATA="${1:-${PROJECT_ROOT}/data/nodes_labeled}"
RES="${PROJECT_ROOT}/data/res"

PREFIX="full_ablation"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
WORKDIR="${RES}/${PREFIX}_${TIMESTAMP}"
SUMMARY="${WORKDIR}/summary.json"

mkdir -p "${WORKDIR}"

echo "============================================"
echo "  完整 Skill 消融实验"
echo "  数据:   ${DATA}"
echo "  结果:   ${WORKDIR}"
echo "============================================"

cd "${PROJECT_ROOT}"

# ── 定义全部 11 组组合 ──
# 格式: "skill_ids|directed_flag|tag"
# skill_ids: 空格分隔
# directed_flag: "" 或 "--directed"
# tag: 输出子目录名

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

# ── 逐个运行 ──
SUMMARY_ROWS="["
FIRST=true

for combo in "${COMBOS[@]}"; do
    IFS="|" read -r skills dflag tag <<< "${combo}"

    dir_flag=""
    if [ "${dflag}" = "dir" ]; then
        dir_flag="--directed"
    fi

    out_dir="${PREFIX}_${TIMESTAMP}/${tag}"

    echo ""
    echo "========================================="
    echo "  [${tag}] skills=${skills} ${dir_flag}"
    echo "========================================="

    # ── 步骤 1: 跑 skill pipeline ──
    python Sys/RootCauseAnalyze/skill_pipeline.py \
        -d "${DATA}" \
        -s ${skills} \
        ${dir_flag} \
        -k 5 \
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

# 提取 all 维度的指标
all_metrics = summary.get('draft_evaluation', {}).get('all', {})
rm = all_metrics.get('ranking_metrics', {})
total = rm.get('Total Evaluated Cases', 0)
top1 = rm.get('Top-1 Acc (%)', 0)
top2 = rm.get('Top-2 Acc (%)', 0)
top3 = rm.get('Top-3 Acc (%)', 0)
top4 = rm.get('Top-4 Acc (%)', 0)
top5 = rm.get('Top-5 Acc (%)', 0)
failed = all_metrics.get('failed_cases_count', 0)

# 写入该组的指标文件
os.makedirs('${WORKDIR}', exist_ok=True)
with open('${RES}/${out_dir}/_metrics.json', 'w') as f:
    json.dump({
        'tag': '${tag}',
        'skills': '${skills}',
        'directed': '${dflag}' not in ['undir', 'none'],
        'total_cases': total,
        'top1': top1,
        'top2': top2,
        'top3': top3,
        'top4': top4,
        'top5': top5,
        'failed_count': failed,
    }, f, ensure_ascii=False, indent=2)
" 2>&1 | grep -v "^\$" | tail -5

done

# ── 汇总所有组的 _metrics.json 到单个 summary.json ──
echo ""
echo "========================================="
echo "  汇总到 ${SUMMARY}"
echo "========================================="

python -c "
import json, os, glob

workdir = '${WORKDIR}'
rows = []

for tag_dir in sorted(os.listdir(workdir)):
    if not os.path.isdir(os.path.join(workdir, tag_dir)):
        continue
    mfile = os.path.join('${RES}', workdir, tag_dir, '_metrics.json')
    if not os.path.exists(mfile):
        # 尝试直接读子目录
        mfile2 = os.path.join(workdir, tag_dir, '_metrics.json')
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
    'total_combinations': len(rows),
    'results': rows,
}

with open('${SUMMARY}', 'w') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

# 打印排名表
print()
print('=== 最终排名（按 Top-1 降序） ===')
print(f'{\"排名\":<4} {\"组合\":<25} {\"有向\":<4} {\"Top-1\":<8} {\"Top-3\":<8} {\"Top-5\":<8} {\"样本\":<6}')
print('-' * 68)
for i, r in enumerate(rows, 1):
    print(f'{i:<4} {r[\"tag\"]:<25} {str(r.get(\"directed\",\"-\")):<4} '
          f'{r[\"top1\"]:<8.2f} {r[\"top3\"]:<8.2f} {r[\"top5\"]:<8.2f} '
          f'{r[\"total_cases\"]:<6}')

print()
print(f'汇总文件: ${SUMMARY}')
"