# AGENT.md

## Project

This repository is a DCN root-cause analysis research prototype for Huawei Cloud
Pingmesh-triggered incidents. The active pipeline is:

`Pingmesh case data -> topo ranker + temporal ranker -> fused evidence -> trust-tree gate -> optional local LLM review -> Score_N evaluation`

## Non-Negotiables

- Internal fault data is not publishable. Do not move `data/` into tracked code.
- Do not call external LLM APIs for project experiments. The intended runtime is local vLLM on Ascend NPU servers.
- Do not let inference code read `label.json`; labels are only for evaluation.
- Run tests with `python -m pytest`, not bare `pytest`, unless a local `PYTHONPATH` is already configured.

## Key Paths

### Core pipeline
- `Sys/RootCauseAnalyze/skill_pipeline.py`: deterministic topo/temporal skill pipeline (offline, no LLM).
- `Sys/RootCauseAnalyze/skills/`: built-in topo, temporal, and fusion logic.
- `Sys/RootCauseAnalyze/gate/`: evidence builder, trust-tree decision, summarizer, bypass response.
- `Sys/RootCauseAnalyze/trust_trees/`: auditable topo/temporal trust tree rules.
- `Sys/RootCauseAnalyze/SkilledAnalyzer.py`: LLM inference path, gate integration, NPU-aware worker orchestration.

### Evaluation
- `Sys/Score/Score_N.py`: Top-K hit-rate evaluation for skill_ips and LLM responses.
- `Sys/Score/evaluate_trust_gate.py`: gate routing evaluation (per-route Top-K stats).
- `Sys/Score/evaluate_gate_selection.py`: per-case topo-vs-temporal-vs-LLM comparison for invoke_llm cases.
- `Sys/Score/apply_trust_gate.py`: apply gate to skillpipe results without calling LLM.
- `Sys/Score/score_utils.py`: backward-compat shim → real implementations in `Sys/utils/io_utils.py`.

### Utilities & config
- `Sys/config.py`: single Python-side config reading env vars set by `scripts/common.sh`.
- `Sys/utils/io_utils.py`: canonical I/O helpers (`load_json`, `save_json`, `write_jsonl`, `write_csv`, `case_id_from_dir`, `dedupe`, `hit_at`). **Prefer this over `score_utils`.**
- `Sys/utils/npu_utils.py`: Ascend NPU memory inspection and waiting (`get_npu_memory_info`, `wait_npu_memory`).
- `Sys/utils/case_utils.py`: case file discovery, node/info loading, ground-truth reading.
- `Sys/utils/alarm_utils.py`: alarm/event extraction and weight helpers.
- `Sys/utils/ranking_utils.py`: stable score sorting and fusion helpers.

### Backward-compat shims (thin re-exports to old paths)
- `Sys/RootCauseAnalyze/confidence_gate.py` → `gate/decision.py` + `gate/response.py`
- `Sys/RootCauseAnalyze/evidence_fusion.py` → `gate/evidence.py`

### Prompts, scripts, data
- `prompts/`: active LLM prompt templates; do not recreate root-level `utils/`.
- `scripts/common.sh`: single source of default server paths and model parameters.
- `scripts/run_gate_pipe_experiments.sh`: current main experiment driver.
- `Baseline/`: TraceRCA, NetEventCause, and BiAn baseline adapters.
- `docs/project_overview.md`: detailed project state and roadmap.

## Data And Artifacts

- `data/` is ignored and should stay local.
- `docs/papers/` keeps text extractions and summaries only.

## Common Commands

```bash
python -m pytest -q
source scripts/common.sh
python Sys/RootCauseAnalyze/skill_pipeline.py --help
python Sys/Score/evaluate_trust_gate.py --help
python Sys/Score/evaluate_gate_selection.py --help
```
