# Experiment Scripts

Use `scripts/common.sh` as the single source of server paths and model defaults.
The `run_paper_*.sh` scripts are thin wrappers for thesis experiments; they avoid
duplicating algorithm logic and keep each experiment tied to one research question.

| Script | Purpose |
| --- | --- |
| `run_paper_01_skill_ablation.sh` | Topology, temporal, and fused deterministic ablation. |
| `run_paper_02_gate_routing.sh` | Trust-tree routing without LLM calls. |
| `run_paper_03_llm_arbitration.sh` | Full LLM reranking vs gated LLM arbitration. |
| `run_paper_04_gate_policy_analysis.sh` | Gate policy comparison and route selection analysis. |
| `run_paper_05_precompute_summary_cache.sh` | Precompute small-model candidate summaries. |
| `run_paper_06_cached_summary_llm.sh` | Cached-summary LLM arbitration experiment. |
| `stat_focus_device_evidence.py` | Quantify anonymized alarm/log volume on the Top-K highest-volume devices. |

Typical order:

```bash
source scripts/common.sh

./scripts/run_paper_01_skill_ablation.sh
./scripts/run_paper_02_gate_routing.sh
./scripts/run_paper_03_llm_arbitration.sh

# After paper_03 produces <run>/gate_pipe_llm:
./scripts/run_paper_04_gate_policy_analysis.sh "$PINGMESH_RESULTS/<run>/gate_pipe_llm"

# Optional summary-cache experiments:
export PINGMESH_SUMMARY_CACHE_DIR="$PINGMESH_RESULTS/summary_cache"
./scripts/run_paper_05_precompute_summary_cache.sh
./scripts/run_paper_06_cached_summary_llm.sh
```

Focused-device evidence-volume report:

```bash
python scripts/stat_focus_device_evidence.py \
  --large-event-threshold 10
```

The command ranks devices by `alarm_count + log_count` and writes
`device_statistics.csv`, `case_statistics.csv`, `report.json`, and a
paper-ready `summary.md`. The defaults are `data/node/nodes_max_labeled` and
Top-5; the output directory is generated as
`data/res/focus_device_evidence_YYYYMMDD_HHMMSS`. It does not read
`label.json`, does not emit alarm text, and anonymizes case/device identifiers
by default.

The case-level log count comes from `full_link.log_list.total` (also compatible
with `loglist.total`) under `data/raw/pingmesh_extend_dedup`. Per-device log
counts are estimates allocated in proportion to `alarm_count + 1` with the
largest-remainder method, so the integer estimates exactly conserve each raw
case total.
