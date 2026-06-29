# CREDENCE design package

This directory is the compact paper-facing design package for CREDENCE:
**Calibrated Risk-aware Evidence Deferment for Network RCA**.

## Thesis

CREDENCE treats Pingmesh-triggered root-cause localization as a selective
decision problem. For each case, the system decides whether deterministic
topology/temporal evidence is reliable enough to bypass LLM reranking, whether
the case should be sent to LLM arbitration, or whether the observations are too
incomplete and should be escalated as low-diagnosability.

The NSDI-style claim is:

> The key production RCA question is not whether an LLM can rerank every case,
> but when existing evidence is sufficiently calibrated to be trusted without
> semantic arbitration.

## Core documents

- `credence_nsdi_final_blueprint.md`: main contribution, claim ladder,
  algorithm story, and server milestone.
- `credence_paper_method_and_figures.md`: paper method text, figure plan, table
  plan, and artifact-to-claim map.
- `credence_algorithm_box_and_proofs.md`: algorithm boxes, assumptions,
  finite-sample risk bound, and small-data caveats.
- `credence_feature_schema.md`: per-case schema and artifact contracts for
  `confidence_cases.jsonl`, `risk_coverage.csv`, `calibration_bins.csv`,
  `llm_value.csv`, and `diagnosability_frontier.csv`.
- `server_handoff_runbook.md`: server-side execution guide for the first
  CREDENCE run.
- `server_artifact_acceptance_criteria.md`: stop/go gates for deciding whether
  server artifacts can support paper claims.
- `credence_public_pretraining_decision_zh.md`: Chinese note on using public RCA
  datasets for source pretraining while preserving Pingmesh target calibration.
- `credence_advisor_briefing_zh.md`: short Chinese briefing for advisor/group
  discussion.
- `source_verified_literature_catalog.md`: source-backed literature catalog for
  production network diagnosis, LLM-RCA, routing, calibration, and public RCA
  datasets.

## Implemented artifact scripts

The design has been connected to runnable server scripts:

- `Sys/Score/export_confidence_cases.py`
- `Sys/Score/calibrate_confidence.py`
- `Sys/Score/evaluate_llm_value.py`
- `Sys/Score/evaluate_diagnosability.py`
- `scripts/run_credence_artifacts.sh`

Synthetic coverage lives in:

- `tests/test_credence_artifacts.py`

## Server run

On the server:

```bash
cd /home/sbp/lixinyang/pingmesh

export PINGMESH_DATA=/path/to/nodes_labeled
export PINGMESH_RESULTS=/path/to/results
export PINGMESH_NPU_CARDS=0,1
export CREDENCE_RUN_ID=credence_$(date +%Y%m%d_%H%M%S)

bash scripts/run_credence_artifacts.sh
```

The script runs two inference passes:

1. `PINGMESH_CONFIDENCE_GATE=0`: an always-LLM pass used only to measure LLM
   rescue and harm.
2. `PINGMESH_CONFIDENCE_GATE=1`: a confidence-gated pass used to export
   CREDENCE gate features and routed decisions.

`export_confidence_cases.py` merges the two `res.json` files by `case_id`, so
`llm_value.csv` is based on real always-LLM responses rather than synthetic
BYPASS responses.

The run writes artifacts under:

```text
${PINGMESH_RESULTS}/credence/${CREDENCE_RUN_ID}
```

Minimum expected outputs:

```text
confidence_cases.jsonl
confidence_extraction_summary.json
confidence_manifest.json
confidence_calibration.json
risk_coverage.csv
calibration_bins.csv
paired_case_outcomes.csv
bootstrap_intervals.csv
llm_value.csv
diagnosability_frontier.csv
manifest/git_commit.txt
manifest/data_file_list.sha256
manifest/weights.sha256
manifest/env.txt
```

## Claim discipline

- No artifact, no paper claim.
- No target-domain calibration, no Pingmesh risk statement.
- No denominator, no rate.
- No label-only isolation, no confidence result.
- If no safe threshold exists, report `no_safe_threshold` and lower the claim
  instead of forcing a threshold.

## Commit boundary

The commit-worthy package should include this compact `design/` directory plus
the CREDENCE artifact scripts and tests. Server-generated data and private raw
case files should not be committed.
