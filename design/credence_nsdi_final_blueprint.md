# CREDENCE final NSDI/CCF-A blueprint

Date: 2026-06-28

This is the advisor-facing and paper-facing control document for CREDENCE. It
consolidates the design package into one final research plan.

## 1. Final thesis

The paper should not be framed as:

> We add a confidence threshold before LLM reranking.

The paper should be framed as:

> Production RCA needs a calibrated trust control plane. CREDENCE turns
> Pingmesh-triggered root-cause localization into a selective diagnosis problem:
> for each case, it decides whether deterministic evidence is trustworthy enough
> to bypass LLM arbitration, whether semantic arbitration has positive value, or
> whether the observations are too incomplete for safe automatic diagnosis.

The central question is:

> When is asking the LLM unnecessary, helpful, or harmful?

This makes CREDENCE a systems contribution rather than a small heuristic gate.

## 2. Final contribution list

Use this four-part contribution list unless server results force a narrower
story.

### Contribution 1: Evidence-ledger confidence

CREDENCE builds an auditable evidence ledger from:

- deterministic score separation;
- topology/path evidence;
- temporal evidence;
- semantic alarm/log support;
- method agreement;
- missingness and observation completeness.

It estimates:

\[
C(x) \approx P(\mathrm{deterministic\ Top1\ correct}\mid \Phi(x)).
\]

The confidence is about deterministic RCA correctness, not about LLM belief.

### Contribution 2: Risk-controlled BYPASS

CREDENCE selects the largest high-confidence case set whose conservative
wrong-bypass upper bound satisfies a configured risk budget:

\[
\tau^*=
\arg\max_{\tau\in\mathcal{T}} |B(\tau)|
\quad
\text{s.t.}
\quad
U_{CP}(\tau)\le \alpha_B.
\]

This turns "trust the deterministic result" into a measurable coverage-risk
contract.

### Contribution 3: Intervention-aware ARBITRATE

The LLM is modeled as a costly, fallible intervention:

\[
\underline{U}_{LLM}(x)=
(1-C(x))\underline{p}_{rescue}(b)V_r
-C(x)\overline{p}_{harm}(b)V_h
-\lambda_{tok}C_{tok}
-\lambda_{lat}C_{lat}.
\]

CREDENCE calls the LLM only when conservative estimated value is positive, and
constrains the LLM to rerank or explain the deterministic Top-K.

### Contribution 4: Diagnosability-aware ESCALATE

Low confidence is split into two cases:

- evidence conflict but enough observations: ARBITRATE;
- missing/weak observations: ESCALATE.

This prevents the system from sending under-observed cases to the LLM and
mistaking fluent guessing for diagnosis.

## 3. Final algorithm

```text
Algorithm CREDENCE(x)
Input:
  Pingmesh-triggered case x
  deterministic Top-K rankings
  calibrated confidence map g
  selected BYPASS threshold tau_B
  diagnosability threshold tau_O
  LLM utility model U_LLM_lower

1. Build evidence ledger L(x).
2. Extract features Phi(x).
3. Compute raw confidence R(x) = f_theta(Phi(x)).
4. Calibrate confidence C(x) = g(R(x)).
5. If C(x) >= tau_B:
      return BYPASS, deterministic Top-K, L(x), C(x)
6. Compute diagnosability O(x).
7. If O(x) < tau_O:
      return ESCALATE, missing-evidence report, L(x), C(x)
8. Compute conservative LLM utility U_LLM_lower(x).
9. If U_LLM_lower(x) > 0:
      call constrained LLM arbiter over deterministic Top-K
      return ARBITRATE, reranked Top-K, L(x), C(x)
10. Return ESCALATE or low-confidence deterministic Top-K with warning.
```

The ordering matters: high-confidence cases bypass first, under-observed cases
escalate before any LLM call, and only ambiguous-but-observable cases are sent
to the LLM.

## 4. What is mandatory vs optional

### Mandatory core

The paper needs these to claim CREDENCE as the main innovation:

- evidence ledger;
- calibrated deterministic correctness confidence;
- risk-controlled BYPASS threshold;
- BYPASS/ARBITRATE/ESCALATE policy;
- rescue/harm accounting for LLM;
- risk-coverage and reliability results.

### Optional but strong

These can strengthen the paper if time and data permit:

- public-source pretraining with target-domain calibration;
- LLM utility lower bounds by confidence/diagnosability bin;
- distribution-shift guard;
- hierarchical Bayesian source prior;
- source adapter for RCAEval/OpenRCA/LEMMA-RCA;
- time-aware held-out split.

### Do not overbuild before server results

Avoid making these central before validating the simpler core:

- large neural confidence model;
- unconstrained LLM candidate generation;
- complex causal graph learning;
- strong conformal guarantee language;
- too many feature groups without ablation support.

## 5. Literature positioning

The related-work story has four pillars.

| Literature | What it gives | Why CREDENCE is different |
| --- | --- | --- |
| Production network diagnosis | Pingmesh, 007, NetBouncer, Flock, Everflow, IntSight, NetPoirot show RCA and telemetry are real systems problems. | They localize or collect evidence; they do not calibrate per-case trust or decide LLM intervention. |
| LLM-assisted RCA | BiAn, TAMO, PACE-LM, OpenRCA-style work show LLMs can help RCA. | They ask how to use LLMs; CREDENCE asks when not to use them. |
| LLM routing/cascades | FrugalGPT, RouteLLM, dynamic routing show cost-aware routing matters. | They route prompts/models, not topology-aware RCA evidence states. |
| Selective prediction/calibration | Selective classification, calibration, conformal risk control, Learn-then-Test, learning-to-defer provide risk/coverage language. | CREDENCE adapts these ideas to RCA ranking, evidence ledgers, LLM harm, and diagnosability. |

The novelty is the join, not any single ingredient.

## 6. Evaluation: primary endpoints

Predeclare these three primary endpoints:

1. **Risk-controlled BYPASS coverage**
   - Main number: maximum coverage satisfying \(U_{CP}\le\alpha_B\).
   - Compare CREDENCE vs margin gate, entropy gate, agreement gate, no-calibration.

2. **LLM call reduction under non-inferior Top-K**
   - Main number: LLM call-rate reduction vs always-LLM.
   - Accuracy must stay within predeclared non-inferiority margin.

3. **LLM harm avoided**
   - Main number: high-confidence deterministic hits that always-LLM would
     break but CREDENCE bypasses.

Secondary endpoints:

- ECE/Brier/reliability;
- AURC/AUROC;
- rescue/harm in ARBITRATE;
- diagnosability frontier;
- latency/tokens saved;
- source-pretraining gains.

## 7. Minimum result pattern for a strong paper

The paper is strong if at least two of these hold:

| Pattern | Evidence |
| --- | --- |
| Risk control | Non-trivial BYPASS coverage under conservative wrong-bypass bound. |
| Cost saving | Large LLM call reduction with non-inferior Top-1/Top-3. |
| Do-no-harm | Always-LLM harms high-confidence cases; CREDENCE avoids those calls. |
| Better routing | ARBITRATE has better rescue/harm ratio than random or margin routing. |
| Diagnosability insight | Observation completeness strongly stratifies RCA success. |
| Transfer gain | Source-pretrained target-calibrated CREDENCE improves coverage or AURC over target-only. |

If only one pattern holds, reduce the paper claim. If none hold, CREDENCE should
be reframed as a negative systems lesson about current telemetry insufficiency.

## 8. Baseline matrix

| Baseline | Purpose |
| --- | --- |
| Always deterministic | Shows value of any LLM intervention. |
| Always LLM rerank | Shows cost and harm of unconditional LLM use. |
| Margin gate | Tests whether CREDENCE is just a score-gap threshold. |
| Entropy gate | Tests whether uncertainty shape alone is enough. |
| Agreement gate | Tests whether method voting alone is enough. |
| No calibration | Tests whether raw confidence is enough. |
| No diagnosability | Tests whether ESCALATE is meaningful. |
| No semantic conflict | Tests whether ARBITRATE routing needs semantic evidence. |
| Target-only CREDENCE | Tests small internal-data-only version. |
| Source-only zero-shot | Transfer baseline; no risk-control claim. |
| Source-pretrained target-calibrated CREDENCE | Main transfer-enhanced variant. |

## 9. Required artifacts

Server-side experiments should emit:

```text
confidence_cases.jsonl
risk_coverage.csv
calibration_bins.csv
llm_value.csv
diagnosability_frontier.csv
paired_case_outcomes.csv
bootstrap_intervals.csv
calibration_diagnostics.csv
sensitivity_sweep.csv
confidence_manifest.json
```

If transfer pretraining is used, also emit:

```text
source_confidence_cases.jsonl
source_dataset_manifest.json
source_to_target_feature_map.json
transfer_split_manifest.json
transfer_results.csv
```

These artifacts are more important than any one table because they make the
paper reproducible inside the private data environment.

## 10. Statistical rules

Use case-level paired evaluation:

- bootstrap case IDs, not repeat rows;
- report paired confidence intervals;
- report McNemar discordant counts for Top-1 comparisons;
- report Clopper-Pearson upper bound for BYPASS risk;
- report all denominators;
- predeclare risk budgets and primary endpoints;
- treat ablations as explanatory unless corrected for multiple comparisons.

Do not say "same accuracy" without a non-inferiority margin and interval.

## 11. Transfer-pretraining rule

Use the phrase:

> Source-pretrained, target-calibrated CREDENCE.

Never claim:

> Public data proves Pingmesh risk.

The correct math is:

\[
R(x)=f_{\theta_s}(\Phi(x))
\]

learned from public source datasets, followed by:

\[
C_t(x)=g_t(R(x))
\]

calibrated on Pingmesh target folds, and:

\[
\tau_t^*=\arg\max_\tau |B_t(\tau)|
\quad
\text{s.t.}
\quad
U_t(\tau)\le\alpha_B.
\]

Public data improves representation. Pingmesh data certifies risk.

## 12. Paper figures

The paper should prioritize these figures:

1. **System architecture**
   - Evidence ledger -> calibrated confidence -> BYPASS/ARBITRATE/ESCALATE.

2. **Risk-coverage curve**
   - CREDENCE vs margin/entropy/agreement/no-calibration.

3. **Reliability diagram**
   - Raw margin vs raw CREDENCE vs calibrated CREDENCE.

4. **LLM rescue/harm by action**
   - BYPASS, ARBITRATE, ESCALATE bins.

5. **Cost-accuracy frontier**
   - Top-K vs LLM invocation rate.

6. **Diagnosability frontier**
   - RCA success and LLM rescue by observation completeness.

7. **Transfer gain**
   - Target-only vs source-pretrained target-calibrated CREDENCE.

## 13. Claim ladder

Use the strongest claim supported by data.

### Level 1: strongest

> CREDENCE achieves risk-controlled LLM bypass and reduces LLM calls while
> maintaining non-inferior RCA accuracy, with measurable avoidance of
> high-confidence LLM harm.

Requires:

- non-trivial BYPASS coverage under CP bound;
- LLM call reduction;
- non-inferior Top-K;
- harm avoided.

### Level 2: solid

> CREDENCE exposes a calibrated risk-coverage frontier and identifies where LLM
> arbitration is beneficial versus harmful or unjustified.

Requires:

- calibrated confidence;
- useful risk-coverage curve;
- rescue/harm stratification.

### Level 3: modest

> CREDENCE provides an auditable framework for evaluating trust, LLM
> arbitration, and diagnosability in Pingmesh RCA, revealing limits of simple
> margin gates and always-on LLM reranking.

Use if:

- data is too small for tight risk bounds;
- source pretraining helps weakly;
- LLM effect is mixed.

### Level 4: negative but useful

> Current Pingmesh evidence is insufficient for safe automatic bypass under
> strict risk budgets; CREDENCE quantifies this gap and motivates additional
> telemetry or labeling.

Use if:

- no safe threshold exists;
- diagnosability dominates.

## 14. What not to claim

Do not claim:

- CREDENCE guarantees future correctness.
- Public source data certifies Pingmesh risk.
- Every low-confidence case should go to the LLM.
- LLM is generally better than deterministic RCA.
- ESCALATE cases can be dropped from denominators.
- A calibrated number is meaningful without reliability evidence.
- More features automatically make the method stronger.

## 15. Exact introduction paragraph

Draft:

> LLMs are increasingly used for operational diagnosis, but production network
> RCA has a more basic control problem: when should an automated system trust
> existing deterministic evidence, when should it ask an LLM to arbitrate
> ambiguous candidates, and when are the observations too incomplete for safe
> automatic diagnosis? We answer this question with CREDENCE, a calibrated
> evidence-deferment framework for Pingmesh-triggered RCA. CREDENCE constructs
> an evidence ledger from topology, temporal, semantic, and observability
> signals; calibrates the probability that deterministic Top-1 is correct;
> selects BYPASS decisions under a conservative wrong-diagnosis risk budget; and
> invokes LLM arbitration only when its estimated rescue value exceeds expected
> harm and cost.

## 16. Exact contribution paragraph

Draft:

> This paper makes three contributions. First, it formulates Pingmesh RCA as a
> selective diagnosis problem and introduces an evidence ledger that makes
> deterministic RCA trust auditable. Second, it designs CREDENCE, a calibrated
> confidence and routing policy that selects high-confidence BYPASS regions
> under explicit wrong-bypass risk budgets while separating low-confidence
> cases into ARBITRATE and ESCALATE. Third, it evaluates LLM reranking as a
> measurable intervention, reporting rescue, harm, latency, and token cost
> under paired case-level statistical analysis.

If transfer pretraining works, add:

> Finally, we show that public RCA datasets can pretrain domain-invariant
> evidence-trust features, while Pingmesh target calibration remains
> responsible for all production risk claims.

## 17. Final next action

The design is now ready for server-side implementation planning. The next
technical milestone should be:

1. extract `confidence_cases.jsonl` on the server;
2. compute deterministic correctness labels;
3. fit target-only CREDENCE with repeated cross-fitting;
4. generate `risk_coverage.csv`, `calibration_bins.csv`, and `llm_value.csv`;
5. decide whether public-source pretraining is needed based on target-only
   stability.

Do not spend more paper-design effort before seeing at least the first
`confidence_cases.jsonl` and risk-coverage curve.
