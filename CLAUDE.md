# Claude Code Entry Point

Updated: 2026-09-12. You are the engineering execution agent for this repository.

Before substantial work, read:

1. `.ai/WORKFLOW.md`
2. `.ai/PROJECT.md`
3. `.ai/CURRENT_TASK.md`
4. `.ai/STATUS.md` when relevant

## Responsibilities

- implementation
- debugging
- testing
- experiments
- relevant repository exploration
- evidence collection
- local Git management

Do not independently change:

- project goals
- research direction
- scientific claims
- strategic decisions

unless explicitly instructed.

## Project Invariants

`.ai/PROJECT.md` holds the binding constraints. Read it before touching
evaluation, label, or experiment code. In particular: inference must not read
root or propagation labels (the explicit Oracle wrapper is the only exception),
experiments must not call external LLM APIs, every emitted propagation edge must
exist in the raw `task_topo`, unknown relations are masked rather than treated
as negatives, and splits/calibration are grouped by verified incident.

Run tests with `python -m pytest`, not bare `pytest`.

## Before Modifying Project Files

1. understand CURRENT_TASK;
2. inspect only relevant files;
3. avoid broad repository scans;
4. form a minimal implementation plan.

## Common Commands

From the Windows repository root, reuse the existing CPU validation environment:

```powershell
& tmp/baselines-venv/Scripts/python.exe -m pytest tests -q
& tmp/baselines-venv/Scripts/python.exe -m pytest pingmesh-propagation-labeler/tests -q
& tmp/baselines-venv/Scripts/python.exe -m Baseline.common --help
& tmp/baselines-venv/Scripts/python.exe Sys/Score/evaluate_propagation.py --help
```

In the configured Linux/NPU environment:

```bash
source scripts/common.sh
bash scripts/run_full_experiment.sh --dry-run
```

## After Completion

Update as relevant:

- `.ai/HANDOFF.md`
- `.ai/EVIDENCE.md`
- `.ai/STATUS.md`
- `.ai/EXPERIMENTS.md`

Follow Git policy in `.ai/WORKFLOW.md`.
