# Project Agent Entry Point

This project uses `.ai/` as its persistent AI context layer.

Start with:

`.ai/GPT_BRIEF.md`

For normal project reasoning, load additional files only when needed.

For task acceptance, use:

1. `.ai/CURRENT_TASK.md`
2. `.ai/HANDOFF.md`
3. `.ai/EVIDENCE.md`
4. relevant diff only when necessary

Read:

`.ai/WORKFLOW.md`

for shared operating rules.

Default review policy: **Summary First → Evidence On Demand.**

Do not perform broad repository exploration or broad external research during
normal acceptance unless a concrete high-risk issue requires verification.

Claude Code performs broad implementation/exploration work.

ChatGPT Work primarily performs high-value judgment and decision-making.

The file map for `.ai/` is in `.ai/README.md`; stable project facts, scope, and
binding constraints are in `.ai/PROJECT.md`.

Keep this file concise.
