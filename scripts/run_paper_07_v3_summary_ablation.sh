#!/usr/bin/env bash
# Paper Exp 07: V3 summary-module ablation under the same trust gate.
#
# Variants:
#   gate_raw_llm       raw candidate JSON, no summary cache
#   gate_skeleton_llm  deterministic lossless compact facts, no small model
#   gate_hybrid_v3_llm lossless compact facts + small-model semantic_summary
#
# Common run:
#   source scripts/common.sh
#   export PINGMESH_SUMMARY_CACHE_DIR="$PINGMESH_RESULTS/node_summary_cache_hybrid_v3"
#   ./scripts/run_paper_07_v3_summary_ablation.sh
#
# Optional:
#   PINGMESH_V3_ABLATION_TEMPERATURE=0.6  # optional override; default keeps common.sh value
#   PINGMESH_V3_REBUILD_SKELETON=1        # overwrite skeleton cache
#   ./scripts/run_paper_07_v3_summary_ablation.sh my_v3_ablation
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/common.sh

PREFIX="${1:-paper_07_v3_summary_ablation}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_TAG="${PREFIX}_${TIMESTAMP}"
WORKDIR="${PINGMESH_RESULTS}/${RUN_TAG}"
HYBRID_CACHE_DIR="${PINGMESH_SUMMARY_CACHE_DIR}"
SKELETON_CACHE_DIR="${PINGMESH_V3_SKELETON_CACHE_DIR:-${PINGMESH_RESULTS}/node_summary_cache_skeleton_v3}"

if [ -n "${PINGMESH_V3_ABLATION_TEMPERATURE:-}" ]; then
    export PINGMESH_TEMPERATURE="${PINGMESH_V3_ABLATION_TEMPERATURE}"
fi

if [ ! -d "${HYBRID_CACHE_DIR}" ]; then
    echo "[ERROR] Hybrid V3 cache not found: ${HYBRID_CACHE_DIR}" >&2
    echo "        Run ./scripts/run_paper_05_precompute_summary_cache.sh first." >&2
    exit 2
fi

if ! python - "${HYBRID_CACHE_DIR}/manifest.json" "${PINGMESH_TOP_K}" <<'PY'
import json
import sys

path, expected_top_k = sys.argv[1], int(sys.argv[2])
try:
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)
except Exception as exc:
    print(f"[ERROR] Cannot read hybrid cache manifest {path}: {exc}", file=sys.stderr)
    raise SystemExit(1)
if manifest.get("summary_prompt_version") != "device-evidence-hybrid-v3":
    print("[ERROR] Cache is not device-evidence-hybrid-v3.", file=sys.stderr)
    raise SystemExit(1)
if manifest.get("top_k") != expected_top_k:
    print(
        f"[ERROR] Cache Top-K={manifest.get('top_k')} does not match run Top-K={expected_top_k}.",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY
then
    echo "        Rebuild it with ./scripts/run_paper_05_precompute_summary_cache.sh." >&2
    exit 2
fi

mkdir -p "${WORKDIR}"

overwrite_args=()
if [ "${PINGMESH_V3_REBUILD_SKELETON:-0}" = "1" ]; then
    overwrite_args+=(--overwrite)
fi

echo "============================================"
echo "  Paper Exp 07: V3 Summary Ablation"
echo "  output:          ${WORKDIR}"
echo "  hybrid_cache:    ${HYBRID_CACHE_DIR}"
echo "  skeleton_cache:  ${SKELETON_CACHE_DIR}"
echo "  temperature:     ${PINGMESH_TEMPERATURE}"
echo "  top_k:           ${PINGMESH_TOP_K}"
echo "============================================"

echo ""
echo "=== [prepare] deterministic skeleton-only cache (no small model) ==="
python scripts/precompute_node_summaries.py \
    --data-root "${PINGMESH_DATA}" \
    --out-cache "${SKELETON_CACHE_DIR}" \
    --top-k "${PINGMESH_TOP_K}" \
    --skeleton-only \
    "${overwrite_args[@]}"

run_variant() {
    local name="$1"
    local cache_dir="$2"
    local expected_mode="$3"
    local cache_args=()
    if [ -n "${cache_dir}" ]; then
        cache_args+=(--summary-cache-dir "${cache_dir}")
    else
        # An explicit empty value is required because common.sh defines a
        # default cache directory for cached-summary experiments.
        cache_args+=(--summary-cache-dir "")
    fi

    echo ""
    echo "=== [${name}] ==="
    python Sys/RootCauseAnalyze/SkilledAnalyzer.py \
        -d "${PINGMESH_DATA}" \
        -s ${PINGMESH_SKILLS} \
        -n "${PINGMESH_NPU_CARDS}" \
        -b "${PINGMESH_BATCH_SIZE}" \
        -k "${PINGMESH_TOP_K}" \
        -o "${RUN_TAG}/${name}" \
        "${cache_args[@]}" \
        --confidence-gate

    python Sys/Score/Score_N.py "${WORKDIR}/${name}/res.json"

    python - "${WORKDIR}/${name}/res.json" "${expected_mode}" <<'PY'
from collections import Counter
import json
import sys

path, expected = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    records = json.load(f)
invoke = [
    row for row in records
    if (row.get("confidence_gate") or {}).get("decision") == "invoke_llm"
]
modes = Counter((row.get("confidence_gate") or {}).get("evidence_mode") for row in invoke)
print(f"[evidence-audit] expected={expected}, invoke_cases={len(invoke)}, modes={dict(modes)}")
if not invoke:
    print("[ERROR] No invoke_llm cases were found; ablation is not meaningful.", file=sys.stderr)
    raise SystemExit(1)
if set(modes) != {expected}:
    print(
        f"[ERROR] Evidence isolation failed: expected only {expected}, got {dict(modes)}",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY
}

run_variant gate_raw_llm "" raw
run_variant gate_skeleton_llm "${SKELETON_CACHE_DIR}" skeleton_v3
run_variant gate_hybrid_v3_llm "${HYBRID_CACHE_DIR}" hybrid_v3

python - "${WORKDIR}" <<'PY'
import csv
import json
import os
import sys

workdir = sys.argv[1]
variants = [
    ("gate_raw_llm", "raw candidate JSON"),
    ("gate_skeleton_llm", "lossless skeleton only"),
    ("gate_hybrid_v3_llm", "lossless skeleton + semantic_summary"),
]
rows = []
records_by_variant = {}
for name, description in variants:
    with open(os.path.join(workdir, name, "sum.json"), encoding="utf-8") as f:
        summary = json.load(f)
    metrics = summary["llm_evaluation"]["ranking_metrics"]
    rows.append({
        "variant": name,
        "description": description,
        "cases": metrics["Total Evaluated Cases"],
        "top1": metrics["Top-1 Acc (%)"],
        "top3": metrics["Top-3 Acc (%)"],
        "top5": metrics["Top-5 Acc (%)"],
    })
    with open(os.path.join(workdir, name, "res.json"), encoding="utf-8") as f:
        records_by_variant[name] = {
            row.get("dir"): row for row in json.load(f)
            if (row.get("confidence_gate") or {}).get("decision") == "invoke_llm"
        }

pairwise = []
for left_index, (left, _left_desc) in enumerate(variants):
    for right, _right_desc in variants[left_index + 1:]:
        common_cases = sorted(set(records_by_variant[left]) & set(records_by_variant[right]))
        same_prompt = sum(
            records_by_variant[left][case].get("prompt") == records_by_variant[right][case].get("prompt")
            for case in common_cases
        )
        same_response = sum(
            records_by_variant[left][case].get("response") == records_by_variant[right][case].get("response")
            for case in common_cases
        )
        pairwise.append({
            "left": left,
            "right": right,
            "invoke_cases": len(common_cases),
            "identical_prompt_cases": same_prompt,
            "identical_response_cases": same_response,
            "identical_response_rate": round(same_response / len(common_cases), 6) if common_cases else None,
        })

json_path = os.path.join(workdir, "v3_ablation_summary.json")
csv_path = os.path.join(workdir, "v3_ablation_summary.csv")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(
        {"workdir": workdir, "results": rows, "pairwise_invoke_case_audit": pairwise},
        f,
        ensure_ascii=False,
        indent=2,
    )
with open(csv_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

print("\n=== V3 Summary Ablation ===")
print(f'{"variant":<24} {"cases":<8} {"top1":<8} {"top3":<8} {"top5":<8}')
print("-" * 64)
for row in rows:
    print(f'{row["variant"]:<24} {row["cases"]:<8} {row["top1"]:<8.2f} '
          f'{row["top3"]:<8.2f} {row["top5"]:<8.2f}')
print("\n=== Pairwise Invoke-Case Audit ===")
for item in pairwise:
    print(
        f'{item["left"]} vs {item["right"]}: '
        f'prompts_same={item["identical_prompt_cases"]}/{item["invoke_cases"]}, '
        f'responses_same={item["identical_response_cases"]}/{item["invoke_cases"]}'
    )
print("summary_json:", json_path)
print("summary_csv: ", csv_path)
PY
