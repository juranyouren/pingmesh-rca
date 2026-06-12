#!/usr/bin/env bash
# ============================================================
# Test 2: LLM 前置告警打分 → topo+temp 评估
#
# 流程:
#   1. 扫描数据集, 提取所有不在权重表中的告警名
#   2. LLM 对缺失告警逐一打分 (1-100)
#   3. 合并到新权重文件
#   4. skill_pipeline 跑 [1,3] dir/undir × 新权重
#   5. 评测, 对比 baseline 87.41%
#
# 用法:
#   ./scripts/run_llm_alarm_scoring.sh
#   ./scripts/run_llm_alarm_scoring.sh /path/to/data
# ============================================================
set -euo pipefail

PROJECT_ROOT="/home/sbp/lixinyang/pingmesh"
DATA="${1:-${PROJECT_ROOT}/data/nodes_labeled}"
RES="${PROJECT_ROOT}/data/res"

# 基础权重文件（人工总结）
BASE_WEIGHTS="${PROJECT_ROOT}/data/weights/classified_alarms/all_alarms.json"

PREFIX="llm_alarm_scoring"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
WORKDIR="${RES}/${PREFIX}_${TIMESTAMP}"
ENRICHED_WEIGHTS="${WORKDIR}/enriched_weights.json"

mkdir -p "${WORKDIR}"

echo "============================================"
echo "  Test 2: LLM 前置告警打分"
echo "  数据:       ${DATA}"
echo "  基础权重:   ${BASE_WEIGHTS}"
echo "  工作目录:   ${WORKDIR}"
echo "============================================"

cd "${PROJECT_ROOT}"

# ── 步骤 1: 扫描所有缺失告警 ──
echo ""
echo "--- 步骤 1: 扫描数据集, 提取缺失告警 ---"

python -c "
import json, os, sys
sys.path.insert(0, '${PROJECT_ROOT}')

# 加载基础权重
base = {}
if os.path.exists('${BASE_WEIGHTS}'):
    with open('${BASE_WEIGHTS}', 'r') as f:
        for item in json.load(f):
            base[item['alarm_name'].lower()] = item['alarm_priority']
print(f'基础权重表: {len(base)} 条')

# 扫描数据集
all_alarms = set()
for dirpath, _, filenames in os.walk('${DATA}'):
    # 找全链路文件
    node_file = None
    for fn in filenames:
        if '全链路.json' in fn and 'pingmesh' in fn:
            node_file = fn
            break
    if not node_file:
        continue
    raw = json.load(open(os.path.join(dirpath, node_file), 'r', encoding='utf-8'))
    nodes = list(raw.values()) if isinstance(raw, dict) else raw
    for nd in nodes:
        for evt in nd.get('alarms', []) + nd.get('logs', []):
            name = evt if isinstance(evt, str) else evt.get('alarm_name', evt.get('name', ''))
            if name:
                all_alarms.add(name.strip())

missing = sorted(a for a in all_alarms if a.lower() not in base)
print(f'扫描到 {len(all_alarms)} 种告警, 缺失 {len(missing)} 种')

# 保存缺失列表
with open('${WORKDIR}/missing_alarms.json', 'w') as f:
    json.dump(missing, f, ensure_ascii=False, indent=2)
print(f'缺失列表: ${WORKDIR}/missing_alarms.json')
"

if [ ! -f "${WORKDIR}/missing_alarms.json" ]; then
    echo "ERROR: 无缺失告警列表"
    exit 1
fi

# ── 步骤 2: LLM 批量打分 ──
echo ""
echo "--- 步骤 2: LLM 批量打分 ---"
echo "检查缺失告警数量..."

MISSING_COUNT=$(python -c "import json;print(len(json.load(open('${WORKDIR}/missing_alarms.json'))))")
echo "共 ${MISSING_COUNT} 条待打分告警"

if [ "${MISSING_COUNT}" -gt 500 ]; then
    echo "WARNING: 缺失告警超过 500，LLM 打分将耗时较长"
fi

python Sys/RootCauseAnalyze/llm_alarm_scorer.py \
    --missing "${WORKDIR}/missing_alarms.json" \
    --output "${ENRICHED_WEIGHTS}" \
    --base-weights "${BASE_WEIGHTS}" \
    --batch-size 32

# ── 步骤 3: skill_pipeline 消融 ──
echo ""
echo "--- 步骤 3: skill_pipeline [1,3] 对比 ---"

for dflag in "" "--directed"; do
    if [ -z "${dflag}" ]; then
        dname="undir"
    else
        dname="dir"
    fi

    out_dir="${PREFIX}_${TIMESTAMP}/topo_temporal_${dname}_enriched"
    echo "--- ${dname} ---"
    python Sys/RootCauseAnalyze/skill_pipeline.py \
        -d "${DATA}" \
        -s 1 3 \
        ${dflag} \
        -k 5 \
        -w "${ENRICHED_WEIGHTS}" \
        -o "${out_dir}" 2>&1 | tail -3

    # 评分
    res_json="${RES}/${out_dir}/res.json"
    if [ -f "${res_json}" ]; then
        python -c "
import json, sys; sys.path.insert(0, '${PROJECT_ROOT}')
from Sys.Score.Score_N import Scorer, LlmTextParser
s = Scorer('${res_json}')
summary = s.calculate_metrics()
m = summary['draft_evaluation']['all']['ranking_metrics']
print(f'  [LLM enriched weights] Top-1={m[\"Top-1 Acc (%)\"]}  Top-3={m[\"Top-3 Acc (%)\"]}  Top-5={m[\"Top-5 Acc (%)\"]}')
" 2>&1
    fi
done

echo ""
echo "============================================"
echo "  Test 2 完成"
echo "  新权重文件: ${ENRICHED_WEIGHTS}"
echo "  对比基线 (llm weights): 87.41% (dir) / 83.22% (undir)"
echo "============================================"
