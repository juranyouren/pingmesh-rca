#!/usr/bin/env bash
# ============================================================
# Test 2: LLM 前置告警打分（去重后只打一次分）
# 配置来自 scripts/common.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

PREFIX="llm_alarm_scoring"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
WORKDIR="${PINGMESH_RESULTS}/${PREFIX}_${TIMESTAMP}"
ENRICHED_WEIGHTS="${WORKDIR}/enriched_weights.json"
mkdir -p "${WORKDIR}"

echo "============================================"
echo "  Test 2: LLM 前置告警打分（去重）"
echo "  基础权重: ${PINGMESH_WEIGHTS_MANUAL}"
echo "============================================"

# ── 1. 扫描去重 ──
echo ""; echo "--- 步骤 1: 扫描去重 ---"
python -c "
import json, os, sys
sys.path.insert(0, '${PINGMESH_PROJECT_ROOT}')
base = {}
with open('${PINGMESH_WEIGHTS_MANUAL}') as f:
    for item in json.load(f): base[item['alarm_name'].lower()] = item['alarm_priority']
all_alarms = set(); case_count = 0
for dirpath, _, filenames in os.walk('${PINGMESH_DATA}'):
    node_file = None
    for fn in filenames:
        if '全链路.json' in fn and 'pingmesh' in fn: node_file = fn; break
    if not node_file: continue
    case_count += 1
    raw = json.load(open(os.path.join(dirpath, node_file), 'r', encoding='utf-8'))
    nodes = list(raw.values()) if isinstance(raw, dict) else raw
    for nd in nodes:
        for evt in nd.get('alarms', []) + nd.get('logs', []):
            name = evt if isinstance(evt, str) else evt.get('alarm_name', evt.get('name', ''))
            if name: all_alarms.add(name.strip())
missing = sorted(a for a in all_alarms if a.lower() not in base)
print(f'{case_count} case, {len(all_alarms)} 种告警, 缺失 {len(missing)} 种')
with open('${WORKDIR}/missing_alarms.json', 'w') as f: json.dump(missing, f, ensure_ascii=False, indent=2)
"

if [ ! -f "${WORKDIR}/missing_alarms.json" ]; then echo "ERROR: 无缺失告警列表"; exit 1; fi

# ── 2. LLM 打分 ──
echo ""; echo "--- 步骤 2: LLM 打分 ---"
python Sys/RootCauseAnalyze/llm_alarm_scorer.py \
    --missing "${WORKDIR}/missing_alarms.json" \
    --output "${ENRICHED_WEIGHTS}" \
    --base-weights "${PINGMESH_WEIGHTS_MANUAL}"

# ── 3. skill_pipeline 对比 ──
echo ""; echo "--- 步骤 3: 新权重 vs 基线 ---"
out_dir="${PREFIX}_${TIMESTAMP}/topo_temporal_enriched"
python Sys/RootCauseAnalyze/skill_pipeline.py \
    -d "${PINGMESH_DATA}" -s 1 2 -k 5 -w "${ENRICHED_WEIGHTS}" -o "${out_dir}" 2>&1 | tail -3

res_json="${PINGMESH_RESULTS}/${out_dir}/res.json"
if [ -f "${res_json}" ]; then
    python -c "
import json, sys; sys.path.insert(0, '${PINGMESH_PROJECT_ROOT}')
from Sys.Score.Score_N import Scorer
m = Scorer('${res_json}').calculate_metrics()['skill_evaluation']['ranking_metrics']
print(f'  [LLM enriched] Top-1={m[\"Top-1 Acc (%)\"]} Top-3={m[\"Top-3 Acc (%)\"]} Top-5={m[\"Top-5 Acc (%)\"]}')
" 2>&1
fi

echo ""; echo "基线: topo+temporal = 56.64%"; echo "新权重: ${ENRICHED_WEIGHTS}"
