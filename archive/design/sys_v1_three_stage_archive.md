# Sys_v1 Three-Stage Prototype Archive

`Sys_v1/` was an isolated copy of the RCA implementation used to explore a
three-stage M1/M2/M3 pipeline without modifying the then-current `Sys/` tree.
The active implementation has since moved to `Sys/`, and no active script,
documentation entrypoint, or production test imports `Sys_v1`.

## Historical design

- M1: topology-focused candidate ranking.
- M2: candidate evidence construction and optional small-model summaries.
- M3: deterministic fusion, confidence routing, and local-LLM review.
- Historical ablations: `m1`, `m1_m3`, `m2_m3`, and `m123`.

## Recovery points

The complete implementation remains available in Git history. Its principal
commits are:

- `e553b78`: initial three-module ablation pipeline.
- `7c4162d`: refactor from the historical `Sys` baseline.
- `6961222`: restore topology initialization with alarm weights.
- `fa55a00`: integrate the Sys_v1 ablation runner.

Use those commits for historical reproduction. New RCA development must use
`Sys/` and the entrypoints documented in `scripts/README.md`.
