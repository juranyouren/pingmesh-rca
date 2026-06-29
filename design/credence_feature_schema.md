# CREDENCE feature and artifact schema

This document is the implementation contract for CREDENCE experiments on the
server. It defines the per-case ledger, derived confidence features, evaluation
artifacts, and invariants needed to make the paper results reproducible.

The schema is intentionally explicit because the paper's central claim depends
on a clean separation between:

- signals available at inference time;
- labels and LLM outcomes used only for calibration/evaluation;
- routing actions that determine whether the LLM is called.

## 1. Primary artifact: `confidence_cases.jsonl`

Each line is one Pingmesh-triggered RCA case. Field groups may be nested JSON
objects in code, but the names below should remain stable so downstream scripts
can generate calibration, risk-coverage, rescue/harm, and diagnosability plots.

### 1.1 Case metadata

| Field | Type | Use | Description |
| --- | --- | --- | --- |
| `case_id` | string | inference/eval | Stable case identifier. |
| `case_dir` | string | eval | Server-side path or logical case folder name. |
| `data_version` | string | eval | Hash, timestamp, or manifest version of the extracted dataset. |
| `split_id` | string | eval | Train/calibration/test fold assignment. |
| `incident_type` | string/null | eval | Optional case family, if available from existing metadata. |
| `label_source` | string/null | eval | Operator ticket, postmortem, synthetic injection, or other label origin. |
| `extraction_status` | string | eval | `ok`, `partial`, or `failed`. |

### 1.2 Labels, evaluation-only

These fields must never be used to compute the online routing decision.

| Field | Type | Use | Description |
| --- | --- | --- | --- |
| `gt_primary_ips` | list[string] | eval only | Primary labeled root-cause devices/IPs. |
| `gt_secondary_ips` | list[string] | eval only | Acceptable secondary roots or co-faults. |
| `gt_all_ips` | list[string] | eval only | Union used for Top-K hit evaluation. |
| `label_confidence` | float/null | eval only | Label reliability score, if available. |
| `root_visible` | bool/null | eval only | Whether the labeled root appears in the available topology/telemetry. |
| `root_has_alarm` | bool/null | eval only | Whether the labeled root generated an alarm/log. |

### 1.3 Deterministic RCA outputs

These are the existing method outputs and fused rankings produced before any
LLM arbitration.

| Field | Type | Use | Description |
| --- | --- | --- | --- |
| `deterministic_topk` | list[object] | inference/eval | Fused Top-K candidates before LLM. |
| `topology_ranking` | list[object] | inference | Topology/path-based ranking. |
| `temporal_ranking` | list[object] | inference | Time-correlation ranking. |
| `semantic_ranking` | list[object] | inference | Alarm/log semantic ranking before LLM. |
| `fused_ranking` | list[object] | inference | Final deterministic ranking and scores. |

Each ranking item should use:

```json
{
  "ip": "10.0.0.1",
  "rank": 1,
  "score": 0.87,
  "score_components": {
    "topology": 0.31,
    "temporal": 0.28,
    "semantic": 0.28
  }
}
```

When a method cannot produce a ranking, store an empty list and record the
reason in `missing_evidence`.

### 1.4 Score-shape features

These features describe whether the deterministic ranking has a clear winner.

| Field | Type | Use | Definition |
| --- | --- | --- | --- |
| `combined_margin_raw` | float/null | inference | Difference between fused scores of rank 1 and rank 2. |
| `combined_margin_z` | float/null | inference | Margin normalized by historical case/fold dispersion. |
| `tail_gap_z` | float/null | inference | Gap between top candidate and average of ranks 3..K. |
| `entropy_topk` | float/null | inference | Entropy of softmax-normalized fused Top-K scores. |
| `top1_prob_softmax` | float/null | inference | Softmax probability of deterministic Top-1. |
| `candidate_count` | int | inference | Number of nonempty candidates considered. |

The margin-only baseline should use only a subset of this group, while CREDENCE
uses it with agreement, diagnosability, and semantic support features.

### 1.5 Method-agreement features

These features ask whether independent evidence channels point to the same
candidate.

| Field | Type | Use | Definition |
| --- | --- | --- | --- |
| `top1_votes` | int | inference | Number of methods ranking fused Top-1 at rank 1. |
| `weighted_top1_votes` | float | inference | Reliability-weighted version of `top1_votes`. |
| `rrf_support` | float | inference | Reciprocal-rank-fusion support for fused Top-1. |
| `rank_std` | float/null | inference | Standard deviation of fused Top-1 ranks across methods. |
| `topk_jaccard_topo_temporal` | float/null | inference | Jaccard overlap between topology and temporal Top-K. |
| `method_top_ips` | object | inference | Map from method name to its Top-1 IP or null. |
| `method_missing_count` | int | inference | Number of methods without usable output. |

### 1.6 Diagnosability and observability features

These features prevent low-confidence cases from being blindly sent to the LLM
when the real problem is insufficient observation.

| Field | Type | Use | Definition |
| --- | --- | --- | --- |
| `path_coverage` | float/null | inference | Fraction of relevant source-destination paths with usable telemetry. |
| `alarm_device_ratio_topk` | float/null | inference | Fraction of Top-K candidates with local or adjacent alarms. |
| `timestamp_coverage` | float/null | inference | Fraction of required event timestamps present and parseable. |
| `semantic_coverage` | float/null | inference | Fraction of candidates with usable text evidence. |
| `topology_coverage` | float/null | inference | Fraction of candidates mappable to topology entities. |
| `diagnosability_score_raw` | float/null | inference | Uncalibrated completeness score. |
| `diagnosability_bin` | string/null | inference/eval | `low`, `medium`, or `high` based on training-fold thresholds. |
| `missing_evidence` | list[string] | inference/eval | Human-readable missing signal types. |
| `root_visibility_offline` | bool/null | eval only | Offline check using `gt_all_ips`; never used in routing. |

### 1.7 Semantic support and counter-evidence

The goal is not to make the LLM duplicate deterministic scoring. The goal is to
identify when existing semantic evidence supports, conflicts with, or fails to
distinguish deterministic candidates.

| Field | Type | Use | Definition |
| --- | --- | --- | --- |
| `top1_causal_alarm_count` | int | inference | Number of causal/diagnostic alarms attached to fused Top-1. |
| `top1_high_severity_count` | int | inference | Number of high-severity alarms attached to fused Top-1. |
| `top1_noise_recovery_count` | int | inference | Number of recovery/noise alarms that weaken fused Top-1. |
| `top2_causal_alarm_count` | int | inference | Same causal support for rank 2. |
| `top1_counter_candidate_has_stronger_semantic` | bool | inference | Whether a lower-ranked candidate has stronger semantic support. |
| `semantic_conflict_score` | float/null | inference | Normalized conflict between score rank and semantic support rank. |
| `semantic_support_delta` | float/null | inference | Support score of rank 1 minus best alternative. |

### 1.8 Confidence and routing fields

These are the core CREDENCE outputs.

| Field | Type | Use | Description |
| --- | --- | --- | --- |
| `raw_confidence` | float | inference/eval | Uncalibrated model output in [0, 1]. |
| `calibrated_confidence` | float | inference/eval | Calibrated estimate of deterministic Top-1 correctness. |
| `confidence_bin` | string | inference/eval | Stable bin label used for reliability diagrams. |
| `threshold_tau` | float | inference/eval | Selected BYPASS threshold for the fold. |
| `risk_budget_alpha` | float | inference/eval | Target wrong-bypass risk. |
| `cp_upper_bound_at_tau` | float | eval | Conservative error upper bound for cases with `c >= tau`. |
| `llm_value_estimate` | float/null | inference/eval | Estimated net utility of LLM arbitration. |
| `decision` | string | inference/eval | `BYPASS`, `ARBITRATE`, or `ESCALATE`. |
| `decision_reason` | string | inference/eval | Short deterministic reason code. |
| `llm_allowed` | bool | inference/eval | Whether policy permits LLM use for this case. |
| `llm_called` | bool | eval | Whether the experiment actually called the LLM. |

Recommended `decision_reason` values:

| Reason | Meaning |
| --- | --- |
| `high_calibrated_confidence` | `calibrated_confidence >= threshold_tau`; use BYPASS. |
| `low_diagnosability` | Observation completeness below policy threshold; use ESCALATE. |
| `positive_llm_value` | Case is ambiguous but observable; use ARBITRATE. |
| `semantic_conflict` | Deterministic score and semantic evidence disagree; use ARBITRATE if observable. |
| `negative_llm_value` | LLM expected utility is non-positive; use ESCALATE or low-confidence deterministic output. |
| `missing_required_evidence` | Required extraction failed; use ESCALATE. |

### 1.9 Evaluation fields

These fields compare deterministic, LLM, and final routed outputs. They are
computed after labels and LLM results are available.

| Field | Type | Use | Description |
| --- | --- | --- | --- |
| `deterministic_hit_top1` | bool/null | eval | Whether deterministic Top-1 hits `gt_all_ips`. |
| `deterministic_hit_top3` | bool/null | eval | Whether deterministic Top-3 hits `gt_all_ips`. |
| `deterministic_hit_top5` | bool/null | eval | Whether deterministic Top-5 hits `gt_all_ips`. |
| `llm_hit_top1` | bool/null | eval | Whether LLM-reranked Top-1 hits `gt_all_ips`. |
| `llm_hit_top3` | bool/null | eval | Whether LLM-reranked Top-3 hits `gt_all_ips`. |
| `llm_hit_top5` | bool/null | eval | Whether LLM-reranked Top-5 hits `gt_all_ips`. |
| `final_hit_top1` | bool/null | eval | Hit under the routed CREDENCE decision. |
| `final_hit_top3` | bool/null | eval | Top-3 hit under the routed CREDENCE decision. |
| `final_hit_top5` | bool/null | eval | Top-5 hit under the routed CREDENCE decision. |
| `llm_rescue` | bool/null | eval | Deterministic miss, LLM hit. |
| `llm_harm` | bool/null | eval | Deterministic hit, LLM miss. |
| `latency_ms` | int/null | eval | End-to-end latency for the selected path. |
| `tokens` | int/null | eval | LLM token count if called. |
| `prompt_hash` | string/null | eval | Hash of prompt template and system instructions. |

## 2. Secondary artifacts

### 2.1 `risk_coverage.csv`

This table supports the main selective-diagnosis result. Every accuracy number
in the paper should be paired with coverage.

| Column | Description |
| --- | --- |
| `threshold` | Candidate confidence threshold. |
| `coverage` | Fraction of cases with `calibrated_confidence >= threshold`. |
| `bypass_count` | Number of BYPASS cases at this threshold. |
| `bypass_errors` | Number of wrong deterministic Top-1 predictions among BYPASS cases. |
| `empirical_risk` | `bypass_errors / bypass_count`. |
| `cp_upper_bound` | One-sided Clopper-Pearson upper bound on wrong-bypass risk. |
| `alpha` | Target risk budget. |
| `delta` | Confidence level parameter for the upper bound. |
| `selected` | Whether this threshold is the deployed `tau`. |

### 2.2 `calibration_bins.csv`

This table supports reliability diagrams and ECE.

| Column | Description |
| --- | --- |
| `bin_left` | Inclusive left edge of confidence bin. |
| `bin_right` | Exclusive right edge, except final bin. |
| `n` | Number of cases in bin. |
| `mean_confidence` | Mean calibrated confidence in bin. |
| `accuracy` | Empirical deterministic Top-1 accuracy in bin. |
| `ece_component` | Bin contribution to expected calibration error. |
| `split_id` | Fold or repeated split identifier. |

### 2.3 `llm_value.csv`

This table proves that low confidence is not the same as "always call LLM."

| Column | Description |
| --- | --- |
| `bin` | Confidence or diagnosability bin. |
| `n` | Number of cases in bin. |
| `deterministic_hits` | Deterministic Top-1 hits. |
| `llm_hits` | LLM Top-1 hits on the same candidate set. |
| `rescue` | Count of deterministic misses fixed by LLM. |
| `harm` | Count of deterministic hits broken by LLM. |
| `rescue_rate` | `rescue / n`. |
| `harm_rate` | `harm / n`. |
| `net_utility` | Weighted rescue minus harm and cost. |
| `avg_latency_ms` | Average LLM-path latency. |
| `avg_tokens` | Average LLM tokens. |

### 2.4 `diagnosability_frontier.csv`

This table separates ambiguous-but-diagnosable cases from cases that should be
escalated due to missing evidence.

| Column | Description |
| --- | --- |
| `diagnosability_bin` | `low`, `medium`, or `high`. |
| `n` | Number of cases. |
| `top1` | Deterministic Top-1 accuracy. |
| `top3` | Deterministic Top-3 accuracy. |
| `llm_rescue_rate` | Fraction rescued by LLM. |
| `llm_harm_rate` | Fraction harmed by LLM. |
| `escalate_rate` | Fraction routed to ESCALATE. |
| `missing_evidence_top_reason` | Most common missing evidence reason. |

### 2.5 `confidence_manifest.json`

The manifest records reproducibility metadata.

```json
{
  "data_version": "2026-06-27-example-hash",
  "code_version": "git-hash",
  "feature_schema_version": "credence-v1",
  "calibration_method": "crossfit-isotonic-or-beta",
  "risk_bound": "one_sided_clopper_pearson",
  "alpha": 0.05,
  "delta": 0.05,
  "topk": 5,
  "llm_model": "model-name-or-null",
  "prompt_hash": "hash-or-null"
}
```

## 3. Invariants

The following invariants should be enforced in evaluation scripts and reported
as a sanity-check table.

1. Label-only fields must not be used by feature extraction, raw confidence,
   calibrated confidence, or online decision logic.
2. If `decision == "BYPASS"`, then `llm_called == false`.
3. If `decision == "ARBITRATE"`, the LLM may only rerank or annotate the
   deterministic Top-K candidate set unless an explicit ablation is named.
4. If `decision == "ESCALATE"`, the paper must count the case in coverage and
   cost metrics rather than silently dropping it.
5. Every reported Top-K accuracy must include its denominator and coverage.
6. `calibrated_confidence` means estimated correctness of deterministic Top-1,
   not confidence in the final routed result.
7. Threshold `tau` must be selected on calibration folds and evaluated on held
   out folds or repeated cross-fitting outputs.
8. Missing evidence must be represented explicitly rather than imputed as zero
   unless the imputation rule is fixed before test evaluation.

## 4. Missing-value policy

Missing telemetry is a signal, not just a nuisance.

- For bounded ratio features, use null when the denominator is undefined.
- For method rankings, use empty lists and increment `method_missing_count`.
- For raw confidence, the feature extractor should also emit binary missingness
  indicators so the model can learn that absent evidence reduces trust.
- For calibration and plotting, keep missing-feature cases in the denominator.
- If a case cannot be parsed at all, emit a minimal row with
  `extraction_status = "failed"` and route it to ESCALATE.

## 5. Privacy and data-handling requirements

The server may contain production-sensitive identifiers. Paper artifacts should
be exportable without exposing raw logs.

- Hash or pseudonymize IPs in public tables unless the dataset policy allows
  disclosure.
- Do not export raw alarm text by default; export semantic category counts,
  severity counts, hashes, or manually approved excerpts.
- Record feature extraction versions in `confidence_manifest.json`.
- Keep a private-to-public field map so paper figures can be regenerated from
  private artifacts without leaking raw data.

## 6. Minimal server command outputs

For the paper, one successful server run should produce at least:

```text
confidence_cases.jsonl
risk_coverage.csv
calibration_bins.csv
llm_value.csv
diagnosability_frontier.csv
confidence_manifest.json
```

These artifacts are enough to draw the main NSDI figures: risk-coverage,
reliability, cost-accuracy, rescue/harm, diagnosability frontier, and case
studies.
