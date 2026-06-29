# Server handoff runbook for first CREDENCE experiment

Date: 2026-06-28

This runbook is the next-action document after the design package. It is meant
for the first server-side CREDENCE run on the private Pingmesh data.

The design phase should pause here. The next useful evidence is:

```text
confidence_cases.jsonl
risk_coverage.csv
calibration_bins.csv
llm_value.csv
```

No paper claim should be strengthened before these files exist.

Important: keep two result sources separate. Use an always-LLM `res.json` to
measure LLM rescue/harm, and a confidence-gated `res.json` to export CREDENCE
gate features and routed decisions. Otherwise high-confidence BYPASS rows would
contain synthetic deterministic responses and could not support `llm_value.csv`.

## 1. Current local state

Relevant existing code:

| Path | Current role |
| --- | --- |
| `scripts/common.sh` | Central environment variables for server paths, results, skills, model, NPU. |
| `scripts/run_inference.sh` | Runs `SkilledAnalyzer.py`, writes `res.json`, invokes `Score_N`. |
| `Sys/RootCauseAnalyze/confidence_gate.py` | Prototype margin/agreement gate that can bypass LLM. |
| `Sys/RootCauseAnalyze/SkilledAnalyzer.py` | Current skill + LLM RCA pipeline. |
| `Sys/RootCauseAnalyze/evidence_fusion.py` | Structured fused evidence source for confidence features. |
| `Sys/Score/Score_N.py` | Existing Top-K scoring. |
| `tests/test_confidence_gate.py` | Tests current prototype gate behavior. |

Relevant design contracts:

| Path | Use |
| --- | --- |
| `design/credence_nsdi_final_blueprint.md` | Final contribution and claim ladder. |
| `design/credence_feature_schema.md` | Exact `confidence_cases.jsonl` and result artifact schema. |
| `design/credence_algorithm_box_and_proofs.md` | Algorithm boxes and risk-bound logic. |
| `design/server_artifact_acceptance_criteria.md` | Stop/go artifact validity and claim-readiness gates. |

## 2. Environment setup on server

Before running CREDENCE extraction, record the data and code manifest.

```bash
cd /home/sbp/lixinyang/pingmesh
source scripts/common.sh

RUN_ID=$(date +%Y%m%d_%H%M%S)
export CREDENCE_RUN_ID="${RUN_ID}"
export CREDENCE_OUT="${PINGMESH_RESULTS}/credence/${RUN_ID}"
mkdir -p "${CREDENCE_OUT}/manifest"

git rev-parse HEAD > "${CREDENCE_OUT}/manifest/git_commit.txt"
find "${PINGMESH_DATA}" -type f | sort | sha256sum \
  > "${CREDENCE_OUT}/manifest/data_file_list.sha256"
sha256sum "${PINGMESH_WEIGHTS_MANUAL}" "${PINGMESH_WEIGHTS_LLM}" \
  > "${CREDENCE_OUT}/manifest/weights.sha256"
env | grep -E '^(PINGMESH|CREDENCE)_' | sort \
  > "${CREDENCE_OUT}/manifest/env.txt"
```

If any command fails, stop and fix paths before producing paper artifacts.

## 3. Phase 0: reproduce current baseline

Goal: confirm the server environment still reproduces the current deterministic
and LLM baseline before adding CREDENCE extraction. This first pass keeps LLM
reranking enabled for every case so LLM rescue/harm can be measured.

```bash
PINGMESH_CONFIDENCE_GATE=0 \
./scripts/run_inference.sh "credence_always_llm_${CREDENCE_RUN_ID}" "1 2"
```

Expected files:

```text
${PINGMESH_RESULTS}/credence_always_llm_${CREDENCE_RUN_ID}/res.json
${PINGMESH_RESULTS}/credence_always_llm_${CREDENCE_RUN_ID}/sum.json or printed Score_N metrics
```

Then run the confidence-gated pass:

```bash
PINGMESH_CONFIDENCE_GATE=1 \
./scripts/run_inference.sh "credence_gated_${CREDENCE_RUN_ID}" "1 2"
```

The always-LLM pass is the source for LLM outcome columns. The gated pass is
the source for CREDENCE confidence features and routed final decisions.

Minimum sanity check:

- Top-1 for deterministic skill evaluation should be near the previously
  observed topo+temporal result.
- LLM reranking should not be assumed better; record its rescue/harm later.
- If results differ sharply, do not continue until data path, weights, and
  code commit are checked.

## 4. Phase 1: export `confidence_cases.jsonl`

Goal: add an extraction script that reads current per-case outputs and emits
one row per case following `design/credence_feature_schema.md`.

Suggested script:

```text
Sys/Score/export_confidence_cases.py
```

Suggested command:

```bash
python Sys/Score/export_confidence_cases.py \
  --res "${PINGMESH_RESULTS}/credence_gated_${CREDENCE_RUN_ID}/res.json" \
  --llm-res "${PINGMESH_RESULTS}/credence_always_llm_${CREDENCE_RUN_ID}/res.json" \
  --out "${CREDENCE_OUT}/confidence_cases.jsonl" \
  --data-version "${CREDENCE_RUN_ID}"
```

### 4.1 Minimum fields for first run

The first version does not need every fancy feature. It must emit enough for
risk-coverage and calibration.

Required metadata:

```text
case_id
case_dir
data_version
split_id
extraction_status
```

Required deterministic ranking fields:

```text
deterministic_topk
topology_ranking
temporal_ranking
fused_ranking
method_top_ips
```

Required score-shape features:

```text
combined_margin_raw
combined_margin_z
tail_gap_z
entropy_topk
top1_prob_softmax
candidate_count
```

Required agreement features:

```text
top1_votes
rrf_support
rank_std
method_missing_count
```

Required diagnosability features:

```text
path_coverage
alarm_device_ratio_topk
timestamp_coverage
semantic_coverage
topology_coverage
missing_evidence
```

Required labels/evaluation fields:

```text
gt_all_ips
deterministic_hit_top1
deterministic_hit_top3
deterministic_hit_top5
llm_hit_top1
llm_hit_top3
llm_hit_top5
llm_rescue
llm_harm
```

Inference fields must not use:

```text
gt_all_ips
deterministic_hit_top*
llm_hit_top*
llm_rescue
llm_harm
root_visible
root_has_alarm
```

### 4.2 Extraction acceptance checks

After export:

```bash
wc -l "${CREDENCE_OUT}/confidence_cases.jsonl"
python -m json.tool "$(head -n 1 "${CREDENCE_OUT}/confidence_cases.jsonl")"
```

If `python -m json.tool` cannot consume inline text on the server, use a small
Python snippet to parse the first line.

Acceptance:

- row count equals number of labeled cases intended for evaluation;
- no required field is globally missing;
- `deterministic_hit_top1` matches current `Score_N` aggregate within rounding;
- at least `combined_margin_raw`, `top1_votes`, and `entropy_topk` are non-null
  for most successfully extracted cases;
- all failed cases are emitted with `extraction_status = "failed"` rather than
  silently dropped.

## 5. Phase 2: fit target-only CREDENCE

Goal: before using public source pretraining, check whether internal data alone
already supports a usable confidence frontier.

Suggested script:

```text
Sys/Score/calibrate_confidence.py
```

Suggested command:

```bash
python Sys/Score/calibrate_confidence.py \
  --cases "${CREDENCE_OUT}/confidence_cases.jsonl" \
  --out-dir "${CREDENCE_OUT}" \
  --method target_only \
  --folds 5 \
  --repeats 20 \
  --risk-budgets 0.02 0.05 0.10 0.15 \
  --delta 0.05 \
  --top-k 5
```

Minimum model:

- monotone logistic or low-dimensional logistic raw score;
- binned beta-binomial or beta calibration;
- Clopper-Pearson upper bound over fixed threshold grid.

Do not start with a large neural model.

Expected files:

```text
confidence_calibration.json
risk_coverage.csv
calibration_bins.csv
paired_case_outcomes.csv
bootstrap_intervals.csv
```

## 6. Phase 3: evaluate LLM intervention value

Goal: quantify whether LLM reranking rescues, harms, or wastes cost in each
confidence/diagnosability region.

Suggested script:

```text
Sys/Score/evaluate_llm_value.py
```

Suggested command:

```bash
python Sys/Score/evaluate_llm_value.py \
  --cases "${CREDENCE_OUT}/confidence_cases.jsonl" \
  --calibration "${CREDENCE_OUT}/confidence_calibration.json" \
  --out "${CREDENCE_OUT}/llm_value.csv"
```

Required table columns:

```text
bin
n
deterministic_hits
llm_hits
rescue
harm
rescue_rate
harm_rate
net_utility
avg_latency_ms
avg_tokens
```

The first paper-relevant question:

> Do high-confidence deterministic cases have low rescue and nonzero harm under
> always-LLM reranking?

If yes, CREDENCE's do-no-harm story is strong.

## 7. Phase 4: generate diagnosability frontier

Goal: prove ESCALATE is not hiding failures; it is detecting observation
insufficiency.

Suggested script:

```text
Sys/Score/evaluate_diagnosability.py
```

Suggested command:

```bash
python Sys/Score/evaluate_diagnosability.py \
  --cases "${CREDENCE_OUT}/confidence_cases.jsonl" \
  --out "${CREDENCE_OUT}/diagnosability_frontier.csv"
```

Required columns:

```text
diagnosability_bin
n
top1
top3
llm_rescue_rate
llm_harm_rate
escalate_rate
missing_evidence_top_reason
```

If low-diagnosability cases have poor deterministic accuracy and poor LLM
rescue, ESCALATE becomes a strong systems insight.

## 8. Phase 5: first claim decision

After Phases 1-4, decide which claim ladder level is supported.

| Evidence pattern | Claim level |
| --- | --- |
| Non-trivial BYPASS coverage under CP bound, LLM calls reduced, no accuracy loss | Level 1 strong CREDENCE claim. |
| Confidence calibrates and risk-coverage is useful, but LLM value is mixed | Level 2 calibrated risk frontier claim. |
| Calibration weak but analysis exposes margin/LLM failure modes | Level 3 auditable evaluation framework claim. |
| No safe threshold and diagnosability dominates | Level 4 negative systems lesson. |

Do not decide the paper's final claim before seeing these artifacts.

## 9. Phase 6: optional source-pretraining

Only start public-source pretraining if target-only CREDENCE is unstable or too
data-limited.

Implementation order:

1. implement `RCAEvalAdapter` first;
2. emit `source_confidence_cases.jsonl`;
3. train source-only raw confidence model;
4. evaluate zero-shot confidence ordering on Pingmesh;
5. target-calibrate with Pingmesh folds;
6. compare target-only vs source-pretrained target-calibrated CREDENCE.

Do not use public data to select Pingmesh BYPASS threshold.

## 10. Required manifest for any paper number

Every number in the paper should be traceable to:

```text
git_commit.txt
data_file_list.sha256
weights.sha256
env.txt
confidence_manifest.json
statistical_summary.json
```

If a result cannot be traced to a manifest, do not cite it.

## 11. Stop/go criteria

### Stop and fix extraction if:

- `confidence_cases.jsonl` row count does not match expected case count;
- labels are missing for many supposedly labeled cases;
- deterministic Top-1 from rows does not match `Score_N`;
- many score-shape fields are null;
- label-only fields appear in inference feature columns.

### Stop and lower claims if:

- no threshold satisfies even \(\alpha_B=0.15\);
- ECE/Brier is worse than raw margin after calibration;
- CREDENCE and margin gate are indistinguishable on risk-coverage;
- LLM rescue/harm is too sparse to estimate.

### Continue to paper figures if:

- at least one risk budget yields non-trivial BYPASS coverage;
- calibrated confidence improves over raw margin;
- LLM harm/rescue is measurable by confidence or decision bin;
- diagnosability bins stratify success or failure.

## 12. First-run report template

After the server run, write a short report:

```text
Run ID:
Git commit:
Data hash:
Cases:
Labeled cases:
Cases with LLM output:

Deterministic Top-1/3/5:
Always LLM Top-1/3/5:

Best CREDENCE threshold at alpha=0.05:
  coverage:
  bypass_count:
  bypass_errors:
  empirical_risk:
  cp_upper_bound:

Calibration:
  ECE:
  Brier:
  AUROC correctness:

LLM value:
  BYPASS harm avoided:
  ARBITRATE rescue:
  ARBITRATE harm:

Diagnosability:
  low-bin n/top1/llm_rescue:
  high-bin n/top1/llm_rescue:

Claim ladder level supported:
Next action:
```

This report should be added under `design/server_run_notes/` or copied into a
future experiment-results directory after the server run.

## 13. Implementation caution

The current `Sys/RootCauseAnalyze/confidence_gate.py` is a prototype baseline.
Keep it as `margin_gate` for comparison. Do not overwrite it with full CREDENCE
until:

1. `confidence_cases.jsonl` exists;
2. target calibration has been evaluated;
3. a selected threshold is stored in `confidence_calibration.json`;
4. the old gate remains available as a baseline.

The paper needs the simple gate as a foil. It is not a failure that it exists;
it is the baseline that makes CREDENCE look principled.
