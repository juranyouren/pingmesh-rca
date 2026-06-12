#!/usr/bin/env bash
# ============================================================
# Test 2: LLM 前置告警打分（去重后只打一次分）
#
# 流程:
#   1. 扫描全数据集, 提取所有唯一告警名（去重）
#   2. 查权重表, 找出缺失的
#   3. LLM 对缺失告警逐条打分 (1-100)
#   4. 合并到新权重文件
#   5. skill_pipeline [1,3] 跑两种权重对比
# ============================================================
set -euo pipefail

PROJECT_ROOT="/home/sbp/lixinyang/pingmesh"
DATA="${1:-${PROJECT_ROOT}/data/nodes_labeled}"
RES="${PROJECT_ROOT}/data/res"

BASE_WEIGHTS="${PROJECT_ROOT}/data/weights/classified_alarms/all_alarms.json"
PREFIX="llm_alarm_scoring"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
WORKDIR="${RES}/${PREFIX}_${TIMESTAMP}"
ENRICHED_WEIGHTS="${WORKDIR}/enriched_weights.json"

mkdir -p "${WORKDIR}"

cd "${PROJECT_ROOT}"

echo "============================================"
echo "  Test 2: LLM 前置告警打分（去重）"
echo "  基础权重: ${BASE_WEIGHTS}"
echo "  输出权重: ${ENRICHED_WEIGHTS}"
echo "============================================"

# ── 步骤 1: 扫描去重 ──
echo ""
echo "--- 步骤 1: 扫描去重 ---"

python -c "
import json, os, sys
sys.path.insert(0, '${PROJECT_ROOT}')

# 加载基础权重
base = {}
if os.path.exists('${BASE_WEIGHTS}'):
    with open('${BASE_WEIGHTS}', 'r') as f:
        for item in json.load(f):
            base[item['alarm_name'].lower()] = item['alarm_priority']

# 扫描全数据集去重
all_alarms = set()
case_count = 0
for dirpath, _, filenames in os.walk('${DATA}'):
    node_file = None
    for fn in filenames:
        if '全链路.json' in fn and 'pingmesh' in fn:
            node_file = fn; break
    if not node_file: continue
    case_count += 1
    raw = json.load(open(os.path.join(dirpath, node_file), 'r', encoding='utf-8'))
    nodes = list(raw.values()) if isinstance(raw, dict) else raw
    for nd in nodes:
        for evt in nd.get('alarms', []) + nd.get('logs', []):
            name = evt if isinstance(evt, str) else evt.get('alarm_name', evt.get('name', ''))
            if name: all_alarms.add(name.strip())

print(f'{case_count} 个 case, {len(all_alarms)} 种唯一告警')
print(f'基础权重已覆盖: {sum(1 for a in all_alarms if a.lower() in base)} 种')
missing = sorted(a for a in all_alarms if a.lower() not in base)
print(f'缺失（需 LLM 打分）: {len(missing)} 种')
with open('${WORKDIR}/missing_alarms.json', 'w') as f:
    json.dump(missing, f, ensure_ascii=False, indent=2)
"

if [ ! -f "${WORKDIR}/missing_alarms.json" ]; then
    echo "ERROR: 无缺失告警列表"
    exit 1
fi

# ── 步骤 2: LLM 批量打分 ──
echo ""
echo "--- 步骤 2: LLM 批量打分 ---"

python Sys/RootCauseAnalyze/llm_alarm_scorer.py \
    --missing "${WORKDIR}/missing_alarms.json" \
    --output "${ENRICHED_WEIGHTS}" \
    --base-weights "${BASE_WEIGHTS}"

# ── 步骤 3: skill_pipeline [1,3] 对比 ──
echo ""
echo "--- 步骤 3: 新权重 vs 基线 ---"
echo ""

for dflag in "" "--directed"; do
    if [ -z "${dflag}" ]; then dname="undir"; else dname="dir"; fi
    out_dir="${PREFIX}_${TIMESTAMP}/topo_temporal_${dname}_enriched"

    python Sys/RootCauseAnalyze/skill_pipeline.py \
        -d "${DATA}" -s 1 3 ${dflag} -k 5 -w "${ENRICHED_WEIGHTS}" -o "${out_dir}" 2>&1 | tail -3

    res_json="${RES}/${out_dir}/res.json"
    if [ -f "${res_json}" ]; then
        python -c "
import json, sys; sys.path.insert(0, '${PROJECT_ROOT}')
from Sys.Score.Score_N import Scorer, LlmTextParser
m = Scorer('${res_json}').calculate_metrics()['draft_evaluation']['all']['ranking_metrics']
print(f'  [LLM enriched] ${dname} Top-1={m[\"Top-1 Acc (%)\"]} Top-3={m[\"Top-3 Acc (%)\"]} Top-5={m[\"Top-5 Acc (%)\"]}')
" 2>&1
    fi
done

echo ""
echo "基线: topo+temporal(dir, llm_weight) = 87.41%"
echo "新权重文件: ${ENRICHED_WEIGHTS}"
