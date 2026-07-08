# Archive

This directory keeps historical notebooks, one-off diagnostics, and maintenance
scripts that are not part of the thesis runtime path.

Do not import from this directory in production RCA code or paper experiment
scripts. If a tool becomes reusable, move the logic into `Sys/` with tests and
call it from a `scripts/run_paper_*.sh` entrypoint.

| Path | Contents |
| --- | --- |
| `notebooks/` | Scratch notebooks kept for traceability. |
| `tmp_tools/` | Historical diagnostic, labeling, and data-repair scripts. |
| `tests/` | Tests for archived tools, kept with the archived code. |
