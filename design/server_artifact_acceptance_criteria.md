# Server artifact acceptance criteria for CREDENCE

Date: 2026-06-29

## 0. Purpose

This document defines the stop/go checks for the first server-side CREDENCE
run. It is stricter than the runbook because its job is to decide whether
server artifacts are trustworthy enough to support paper claims.

Principle:

> No artifact, no claim. No target calibration, no Pingmesh risk statement.
> No denominators, no rate. No label-only isolation, no confidence result.

All checks should be run inside the run-specific `CREDENCE_OUT` directory. Raw
private data should remain on the server. Local design files should only receive
schemas, aggregate summaries, and anonymized tables.

## 1. Minimum artifact set

A first valid CREDENCE run must produce:

```text
manifest/git_commit.txt
manifest/data_file_list.sha256
manifest/weights.sha256
manifest/env.txt
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
```

The following files are paper-ready extensions:

```text
claim_budget.json
claim_fragility.csv
source_pretraining_config.json
target_calibration_splits.json
transfer_results.csv
source_to_target_feature_map.json
```

The extension files are not required for the first target-only run. They are
required before making source-pretraining or claim-fragility claims.

## 2. Manifest gate

The run fails the manifest gate if any of the following is true:

- `manifest/git_commit.txt` is missing or empty.
- `manifest/data_file_list.sha256` is missing or empty.
- `manifest/weights.sha256` is missing when learned weights or saved model
  outputs are used.
- `manifest/env.txt` is missing or does not record the Python environment.
- `confidence_manifest.json` does not record `run_id`, `created_at`,
  `case_count`, `label_count`, `feature_columns`, `label_only_columns`,
  `calibration_method`, `split_seed`, and `output_paths`.

The manifest is not cosmetic. It is the evidence that paper numbers can be
regenerated from the same server state.

## 3. Baseline reproduction gate

Before CREDENCE artifacts are trusted, the existing deterministic or current
pipeline baseline must reproduce.

Required evidence:

- the current baseline result file exists under the same run or referenced
  baseline run;
- aggregate Top-1, Top-3, Top-5, and `Score_N` values match the existing
  baseline summary within documented rounding;
- each case included in CREDENCE can be mapped back to the baseline case id;
- excluded cases have explicit exclusion reasons.

Stop and fix the extraction if baseline aggregate accuracy changes because of
the CREDENCE export script.

## 4. Extraction gate for `confidence_cases.jsonl`

`confidence_cases.jsonl` is the most important artifact. Every later table
depends on it.

Required checks:

- every line parses as valid JSON;
- every row has a stable, unique `case_id`;
- LLM outcome fields come from an always-LLM result source when gated BYPASS
  responses are present;
- row count equals the number of intended evaluation cases;
- labeled row count equals the number of usable labeled cases in the extraction
  summary;
- failed or partially extracted cases are retained with `extraction_status` and
  `missing_fields`, not silently dropped;
- deterministic rankings are present for all cases where the baseline method
  produced a ranking;
- hit labels such as `deterministic_hit_top1`, `deterministic_hit_top3`, and
  `deterministic_hit_top5` are present for labeled cases;
- score-shape features, agreement features, diagnosability features, and LLM
  fields use explicit `null` values when unavailable;
- aggregates recomputed from the JSONL match the baseline summary;
- all feature columns are listed in `confidence_manifest.json`;
- all label-only columns are listed separately and are excluded from raw
  confidence training, calibration fitting, and online decision logic;
- `confidence_extraction_summary.json` reports total rows, labeled rows,
  extraction failures, missing-field counts, and label-source counts.

Hard failure conditions:

- row count mismatch;
- duplicate `case_id`;
- silent row drops;
- missing labels for cases that the baseline evaluated;
- deterministic Top-K aggregates do not match the baseline;
- `llm_value.csv` is computed from synthetic BYPASS responses rather than real
  always-LLM responses;
- any label-only field appears in `feature_columns`, `transfer_features`, or
  model input columns.

## 5. Calibration gate

The calibration gate decides whether a raw evidence-trust score can be treated
as target-domain confidence.

Required files:

```text
confidence_calibration.json
risk_coverage.csv
calibration_bins.csv
paired_case_outcomes.csv
bootstrap_intervals.csv
```

`confidence_calibration.json` must record:

- calibration method;
- split policy and seed;
- threshold grid;
- selected BYPASS threshold, or an explicit `no_safe_threshold` decision;
- risk budget;
- Clopper-Pearson or other upper-bound method;
- number of target calibration cases;
- number of selected calibration cases;
- wrong BYPASS count among selected calibration cases;
- feature set used by the raw confidence model;
- list of excluded label-only fields.

`risk_coverage.csv` must include denominators and enough columns to reconstruct
the frontier:

```text
threshold,n_selected,n_total,coverage,wrong_bypass_count,
wrong_bypass_rate,wrong_bypass_upper,alpha,selected
```

`calibration_bins.csv` must include:

```text
bin_id,n,confidence_min,confidence_max,mean_confidence,
empirical_accuracy,brier,ece_component
```

Acceptance conditions:

- calibration uses Pingmesh target calibration folds, not public-source labels;
- a test case is never used to calibrate itself in the reported out-of-fold
  result;
- every rate has a denominator;
- `risk_coverage.csv` contains all tested thresholds, not only the selected
  threshold;
- if no threshold satisfies the risk budget, the artifact says so explicitly;
- ECE and Brier are reported for calibrated confidence and raw margin baseline;
- paired outcome rows are case-level rows, not candidate-level rows.

Stop and lower claims if calibrated confidence is worse than raw margin on both
ECE and Brier, or if no non-trivial BYPASS threshold is supportable under any
reasonable risk budget reported by the paper.

## 6. LLM value gate

`llm_value.csv` supports the claim that low confidence should not automatically
mean "ask the LLM." It must quantify rescue and harm.

Required columns:

```text
region_or_bin,n,deterministic_hits,llm_hits,rescue,harm,
rescue_rate,harm_rate,net_utility,avg_latency_ms,avg_tokens
```

Acceptance conditions:

- rescue and harm are computed on the same case set;
- parser failures and missing LLM outputs are counted explicitly;
- denominators are shown for every region or bin;
- cost columns may be `null` only if the paper does not claim token or latency
  savings from those rows;
- high-confidence BYPASS, low-confidence ARBITRATE, and low-diagnosability
  ESCALATE regions are separable in the table or joinable through case ids.

Stop and lower claims if LLM rescue/harm counts are too sparse to support a
regional conclusion. In that case, present LLM value as descriptive and keep the
main claim on calibrated risk coverage.

## 7. Diagnosability gate

`diagnosability_frontier.csv` is required if the paper claims ESCALATE is a real
action rather than a hidden failure bucket.

Required columns:

```text
diagnosability_bin,n,top1,top3,top5,llm_rescue_rate,
llm_harm_rate,escalate_rate,missing_evidence_top_reason
```

Acceptance conditions:

- every bin has a denominator;
- missing evidence reasons are aggregated from actual extraction fields;
- ESCALATE cases remain in the denominator of case-level summaries;
- low diagnosability is shown to differ from ordinary low confidence, either by
  lower evidence coverage, weaker LLM rescue, higher missingness, or explicit
  case examples.

If diagnosability does not stratify outcomes, keep ESCALATE as an engineering
safety action but do not make it a main empirical contribution.

## 8. Statistical gate

Small data is acceptable only if uncertainty is reported honestly.

`paired_case_outcomes.csv` must use one row per `case_id` and include:

```text
case_id,label_available,deterministic_top1,llm_top1,
credence_top1,credence_action,confidence,diagnosability
```

`bootstrap_intervals.csv` must include:

```text
metric,estimate,ci_low,ci_high,n_cases,bootstrap_repeats,seed
```

Acceptance conditions:

- bootstrap resamples case ids, not repeated candidate rows;
- paired comparisons use the same held-out cases;
- repeated cross-fitting reports unique case count and repeat count separately;
- non-inferiority or superiority margins are declared before interpreting the
  result table;
- claim-fragility analysis is present before claiming a strong NSDI result from
  a very small number of discordant cases.

## 9. Claim readiness gate

After the required artifacts pass the gates above, choose the paper claim level.

| Evidence pattern | Claim level |
| --- | --- |
| Non-trivial BYPASS coverage under target-domain upper-bound risk, LLM calls reduced, no accuracy loss, and LLM harm avoided in high-confidence cases. | Level 1: strong CREDENCE systems contribution. |
| Confidence calibrates and risk-coverage is useful, but LLM value is mixed or sparse. | Level 2: calibrated risk frontier for production RCA. |
| Calibration weak, but artifacts expose margin-gate and LLM failure modes. | Level 3: auditable evaluation framework and dataset-driven insight. |
| Extraction or label isolation fails. | No paper claim. Fix artifacts first. |

Do not promote the claim level based on qualitative examples alone. Examples
can explain a frontier; they cannot replace the frontier.

## 10. Minimal server-side sanity checks

These are not a full verifier, but they catch the most damaging artifact errors.

```bash
test -s "${CREDENCE_OUT}/confidence_cases.jsonl"
test -s "${CREDENCE_OUT}/confidence_extraction_summary.json"
test -s "${CREDENCE_OUT}/confidence_manifest.json"
test -s "${CREDENCE_OUT}/confidence_calibration.json"
test -s "${CREDENCE_OUT}/risk_coverage.csv"
test -s "${CREDENCE_OUT}/calibration_bins.csv"
test -s "${CREDENCE_OUT}/llm_value.csv"
test -s "${CREDENCE_OUT}/diagnosability_frontier.csv"
wc -l "${CREDENCE_OUT}/confidence_cases.jsonl"
```

Suggested JSONL check:

```bash
python - <<'PY'
import json, os, sys
path = os.path.join(os.environ["CREDENCE_OUT"], "confidence_cases.jsonl")
seen = set()
rows = 0
missing_status = 0
for line_no, line in enumerate(open(path, encoding="utf-8"), 1):
    row = json.loads(line)
    rows += 1
    cid = row.get("case_id")
    if not cid:
        raise SystemExit(f"missing case_id at line {line_no}")
    if cid in seen:
        raise SystemExit(f"duplicate case_id {cid}")
    seen.add(cid)
    if "extraction_status" not in row:
        missing_status += 1
print({"rows": rows, "unique_case_ids": len(seen), "missing_status": missing_status})
PY
```

Suggested label-isolation check:

```bash
python - <<'PY'
import json, os
manifest = json.load(open(os.path.join(os.environ["CREDENCE_OUT"], "confidence_manifest.json")))
features = set(manifest.get("feature_columns", []))
label_only = set(manifest.get("label_only_columns", []))
leak = sorted(features & label_only)
if leak:
    raise SystemExit({"label_leakage_columns": leak})
print("label_only_isolation_ok")
PY
```

## 11. Final checklist

Before using any number in a paper figure, confirm:

- artifacts are under one run-specific `CREDENCE_OUT`;
- manifest files exist;
- JSONL row counts match expected cases;
- no label-only leakage exists;
- calibration uses target folds;
- every plotted rate has a denominator;
- confidence is compared against raw margin;
- LLM rescue and harm are both counted;
- ESCALATE cases are retained in denominators;
- uncertainty intervals are case-level;
- the chosen claim level matches the artifact evidence.
