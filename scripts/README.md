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
