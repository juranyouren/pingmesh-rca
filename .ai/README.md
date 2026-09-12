# `.ai/` — Persistent AI Context Layer

`.ai/` is persistent shared context for AI agents working on this repository.

It is **not** raw project storage: no datasets, logs, checkpoints, or large
source excerpts. It holds summaries, pointers, and decisions. Raw material stays
in its own ignored locations and is referenced, not copied.

## Files

| File | Role | Owner |
|---|---|---|
| [WORKFLOW.md](WORKFLOW.md) | generic shared operating rules (roles, loading, review levels, Git policy) | shared |
| [PROJECT.md](PROJECT.md) | stable project facts: goal, scope, constraints, evaluation contract, key sources | shared |
| [GPT_BRIEF.md](GPT_BRIEF.md) | compressed high-level state; preferred lightweight entry point | ChatGPT Work |
| [STATUS.md](STATUS.md) | current operational state, repository map, blockers, next actions | shared |
| [DECISIONS.md](DECISIONS.md) | decision history with context, evidence, and consequence | ChatGPT Work |
| [EXPERIMENTS.md](EXPERIMENTS.md) | experiment/evaluation registry (summaries and pointers, not raw logs) | shared |
| [CURRENT_TASK.md](CURRENT_TASK.md) | the single current execution specification for Claude Code | ChatGPT Work |
| [HANDOFF.md](HANDOFF.md) | Claude Code completion report for review | Claude Code |
| [EVIDENCE.md](EVIDENCE.md) | claim/evidence compression so review need not reopen sources | Claude Code |

Entry points at repository root:

- `AGENT.md` — concise entry point for ChatGPT Work / high-level agents.
- `CLAUDE.md` — concise entry point for Claude Code.

Both are thin pointers; the substance lives here.

## Information Flow

```text
ChatGPT Work
     |
     v
CURRENT_TASK.md
     |
     v
Claude Code
     |
     v
HANDOFF.md + EVIDENCE.md
     |
     v
ChatGPT Work review
     |
     v
DECISIONS.md / STATUS.md / GPT_BRIEF.md
```

ChatGPT Work reasons and decides; Claude Code executes and compresses evidence;
`.ai/` carries that state between sessions so nothing has to be re-derived.

See [WORKFLOW.md](WORKFLOW.md) for loading order, review levels, and Git policy.

## Per-Task Artifacts

`T###_*.md` files in this directory are immutable per-task records from
completed rounds (task specification, handoff, independent acceptance). They are
archives, not live state. Current state lives in the files listed above; when an
archive and a live file disagree, the live file wins.
