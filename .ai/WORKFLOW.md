# AI Project Workflow

Generic operating protocol shared by all agents on this project.
Project-specific facts live in [PROJECT.md](PROJECT.md); this file holds rules.

## Agent Roles

### ChatGPT Work

Responsible for:

- research / project direction
- architecture decisions
- experiment design
- strategic reasoning
- paper/product strategy
- review
- acceptance
- difficult trade-offs

ChatGPT Work should spend expensive reasoning primarily on decisions,
not broad information retrieval.

### Claude Code

Responsible for:

- repository exploration when explicitly required by CURRENT_TASK
- implementation
- debugging
- testing
- experiments
- information gathering
- evidence compression
- local Git operations

## Persistent Context

`.ai/` is the persistent shared memory layer.

Chat history is temporary working context.

Use:

| File | Role |
|---|---|
| [PROJECT.md](PROJECT.md) | stable project knowledge |
| [GPT_BRIEF.md](GPT_BRIEF.md) | compressed high-level project state |
| [STATUS.md](STATUS.md) | current operational state |
| [DECISIONS.md](DECISIONS.md) | important historical decisions |
| [EXPERIMENTS.md](EXPERIMENTS.md) | experiment/evaluation registry |
| [CURRENT_TASK.md](CURRENT_TASK.md) | task specification for Claude Code |
| [HANDOFF.md](HANDOFF.md) | Claude Code result summary |
| [EVIDENCE.md](EVIDENCE.md) | compressed evidence for review |

## Progressive Context Loading

Do not load everything by default.

ChatGPT Work should normally read:

`GPT_BRIEF` → `CURRENT_TASK` → `HANDOFF` → `EVIDENCE`

Then load additional information only when necessary.

Claude Code should normally read:

`CLAUDE.md` → `WORKFLOW` → `PROJECT` → `CURRENT_TASK`

Then inspect repository files only when the actual task requires it.

## Token-Efficient Review

Use: **Summary First → Evidence On Demand.**

### Level 0

Default acceptance review. Use:

- GPT_BRIEF
- CURRENT_TASK
- HANDOFF
- EVIDENCE
- targeted diff when needed

Do not reopen original sources.

### Level 1

Targeted verification only when:

- evidence conflicts
- a critical fact is ambiguous
- a metric looks suspicious
- implementation may violate an invariant
- exact source support matters

Inspect only the relevant source fragment.

### Level 2

Full re-investigation only when:

- evidence is materially incomplete
- leakage is suspected
- methodology may be invalid
- a central claim may be false
- the decision could materially change project direction

## Evidence Policy

Broad exploration should be compressed before being handed to ChatGPT Work.

Do not copy large source texts into `.ai/`.

Record:

- Claim ID
- claim
- source
- locator
- finding
- interpretation
- confidence
- verification need

## Task Lifecycle

```text
Planning
  -> CURRENT_TASK
  -> Claude execution
  -> verification
  -> HANDOFF + EVIDENCE
  -> GPT review
  -> decision/state update
```

## Git Policy

Claude Code may:

- inspect local status/diff relevant to its task
- create task-specific branches
- stage task-related changes
- create clean local commits

Claude Code must NOT without explicit user approval:

- `git push`
- force push
- merge into main
- rewrite shared history
- delete remote branches
- `git reset --hard`
- discard user changes

The user owns publication of repository history.

Claude owns local task commits.

## Scope Discipline

For normal implementation tasks:

- inspect only relevant files
- avoid unnecessary repository-wide scans
- avoid unrelated refactors
- avoid unrelated formatting changes
- prefer minimal reversible changes

## Completion Protocol

Claude should leave enough compressed information that ChatGPT Work does not
need to repeat the implementation investigation.

A completed task should record:

- task
- modified files
- branch/commit when applicable
- implementation summary
- commands
- tests
- experiments
- results
- problems
- risks
- recommended next action
