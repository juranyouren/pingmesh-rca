# Paper-ready CREDENCE method section and figure plan

Date: 2026-06-28

This document converts the CREDENCE design package into a write-ready NSDI
method section. It is intentionally different from the mathematical appendix:
the appendix proves the machinery; this note tells the paper how to present the
machinery so reviewers see a systems contribution rather than a clever
threshold.

## 1. Method-section thesis

Use this sentence as the first paragraph of the design section:

> CREDENCE is a calibrated trust control plane for Pingmesh-triggered RCA. Given
> a case, it constructs an evidence ledger, estimates the probability that the
> deterministic Top-1 root-cause candidate is correct, selects high-confidence
> BYPASS decisions under an explicit wrong-bypass risk budget, and sends only
> ambiguous-but-diagnosable cases to a constrained LLM arbiter.

The section should make three ideas unavoidable:

1. Confidence is an action variable, not a score decoration.
2. The LLM is an intervention with rescue, harm, and cost.
3. Low confidence has two meanings: ambiguity and non-diagnosability.

## 2. NSDI organization pattern

The related NSDI systems papers tend to earn trust through this structure:

| Pattern | Example anchor | How CREDENCE should imitate it |
| --- | --- | --- |
| Start from production pain, not an algorithm. | 007 and NetBouncer frame diagnosis as hard because symptoms and faults are misaligned at datacenter scale. | Open with Pingmesh symptoms, candidate ambiguity, and LLM harm rather than calibration math. |
| Use observations to justify design goals. | NetAssistant and Aegis first study real operational cases before presenting the system. | Put server observations before or just ahead of the design goals once data is available. |
| Keep the system architecture simple. | NetBouncer explains a complete localization framework with concrete components. | Show CREDENCE as ledger -> confidence -> BYPASS/ARBITRATE/ESCALATE, not as a pile of features. |
| Evaluate with deployment-relevant metrics. | Aegis reports diagnosis time and restart/performance effects, not just model accuracy. | Report LLM call rate, harm avoided, risk-coverage, and diagnosability, not only Top-1. |
| State deployment limits plainly. | Production diagnosis papers usually discuss inconsistency, missing data, and operational constraints. | Say that no safe threshold is a valid outcome under strict risk budgets. |

Source anchors already recorded in `source_verified_literature_catalog.md`:

- 007, NSDI 2018: symptoms may not correlate with where or why failures occur.
- NetBouncer, NSDI 2019: datacenter localization must work amid millions of
  servers and many devices.
- NetAssistant, NSDI 2024: diagnosis workflows can be AI-assisted but must be
  reliable and trustworthy.
- Aegis, NSDI 2025: production diagnosis papers can center evolution,
  deployability, and operational impact.

## 3. Section 5 outline

### 5.1 Overview

Goal: show the control plane in one pass.

Write:

> CREDENCE runs after deterministic RCA has produced a Top-K candidate list and
> before any LLM reranking. It does not ask the LLM to discover arbitrary new
> devices. Instead, it decides whether existing deterministic evidence is
> already trustworthy, whether semantic arbitration is likely to help, or
> whether available observations are too incomplete for safe automation.

Pipeline:

```text
Pingmesh case
  -> deterministic candidate rankings
  -> evidence ledger L(x)
  -> raw trust score R(x)
  -> calibrated confidence C(x)
  -> BYPASS / ARBITRATE / ESCALATE
```

### 5.2 Evidence ledger

Goal: make the features auditable.

Define \(L(x)\) as a typed record with:

- score-shape evidence: margin, tail gap, Top-K entropy;
- topology evidence: path coverage, candidate role, path witness count;
- temporal evidence: event ordering, timestamp coverage, burst alignment;
- semantic evidence: alarm/log support, severity, causal keywords;
- method agreement: Top-1 votes, reciprocal-rank support, rank dispersion;
- missingness: absent path/alarm/time/semantic/topology groups;
- counter-evidence: stronger alternative candidates, recovery-only alarms,
  missing witnesses for the proposed root.

Key wording:

> The ledger is both a feature source and an operator artifact. Every confidence
> decision can be traced to evidence entries rather than a free-form LLM
> explanation.

### 5.3 Raw evidence-trust score

Goal: define a compact, interpretable model.

Let \(a(x)\) be the deterministic Top-1 candidate and
\(Z=\mathbf{1}[a(x)\in Y]\). CREDENCE estimates:

\[
C(x)\approx P(Z=1\mid \Phi(x)).
\]

The raw score is:

\[
R(x)=\sigma(\beta_0+\beta^\top\Phi(x)).
\]

Use monotone sign constraints:

```text
positive: margin, tail gap, agreement, reciprocal-rank support,
          diagnosability, semantic support
negative: entropy, rank dispersion, missingness, counter-evidence
```

Paper wording:

> We deliberately use a low-dimensional monotone scorer. This keeps the model
> learnable with limited production labels and makes each feature-group ablation
> correspond to an operational hypothesis.

If public pretraining is used:

\[
R(x)=f_{\theta_s}(\Phi(x))
\]

is learned from source RCA datasets, while \(g_t\) and \(\tau_t\) are still
selected on Pingmesh calibration folds.

### 5.4 Calibration

Goal: distinguish raw score from probability.

Write:

> A large deterministic margin is not a probability. CREDENCE converts raw
> trust scores into calibrated confidence using held-out Pingmesh calibration
> cases.

Preferred methods:

1. binned beta-binomial lower confidence for small data;
2. beta calibration for smoother probability maps;
3. isotonic regression only if calibration folds are large enough.

For a bin \(b\):

\[
C(x)=Q_q(\mathrm{Beta}(h_b+a_0,\ n_b-h_b+b_0)).
\]

This says:

> Confidence is a conservative lower estimate of deterministic correctness in
> similar evidence states.

### 5.5 Risk-controlled BYPASS

Goal: turn confidence into a production contract.

For threshold \(\tau\):

\[
B(\tau)=\{x:C(x)\ge \tau,\ O(x)\ge\tau_O\}.
\]

Coverage:

\[
\mathrm{cov}(\tau)=|B(\tau)|/n.
\]

Wrong-bypass risk:

\[
\widehat{\rho}(\tau)
=
\frac{1}{|B(\tau)|}\sum_{x_i\in B(\tau)}(1-Z_i).
\]

Conservative upper bound:

\[
U_{CP}(\tau)
=
\mathrm{BetaInv}
\left(1-\delta/|\mathcal{T}|;\ e_\tau+1,\ n_\tau-e_\tau\right).
\]

Select:

\[
\tau_B^*
=
\arg\max_{\tau\in\mathcal{T}} |B(\tau)|
\quad
\text{s.t.}
\quad
U_{CP}(\tau)\le \alpha_B.
\]

Reviewer-safe wording:

> This is a finite-sample calibration-set certificate over a fixed threshold
> family. We report held-out risk-coverage curves and do not claim universal
> correctness for future incidents without distributional assumptions.

### 5.6 LLM arbitration as an intervention

Goal: prevent "LLM as magic fallback."

Define rescue and harm:

\[
\mathrm{Rescue}=\mathbf{1}[\hat{y}_{det}\notin Y
\land \hat{y}_{LLM}\in Y],
\]

\[
\mathrm{Harm}=\mathbf{1}[\hat{y}_{det}\in Y
\land \hat{y}_{LLM}\notin Y].
\]

Conservative utility:

\[
\underline{U}_{LLM}(x)
=
(1-C(x))\underline{p}_{rescue}(b)V_r
-C(x)\overline{p}_{harm}(b)V_h
-\lambda_{tok}c_{tok}
-\lambda_{lat}c_{lat}.
\]

Call the LLM only if:

```text
O(x) >= tau_O and lower_U_LLM(x) > 0
```

Constrain the LLM:

- rerank deterministic Top-K only;
- cite ledger evidence;
- emit no new device/IP unless explicitly running a separate discovery mode;
- log token, latency, and output parser status.

### 5.7 Diagnosability-aware ESCALATE

Goal: make low confidence more nuanced.

Define:

\[
O(x)=
\mathrm{mean\_non\_null}[
O_{path},O_{alarm},O_{time},O_{semantic},O_{topology}
].
\]

Decision:

```text
if C(x) >= tau_B:
    BYPASS
elif O(x) < tau_O:
    ESCALATE
elif lower_U_LLM(x) > 0:
    ARBITRATE
else:
    ESCALATE or low-confidence deterministic output with warning
```

Paper wording:

> ESCALATE is not an error bucket. It is CREDENCE's way of saying that the
> available observations cannot support a reliable automatic diagnosis, whether
> deterministic or LLM-based.

### 5.8 Serving-time algorithm

Use this compact algorithm in the paper:

```text
Algorithm 1: CREDENCE serving-time triage
Input: case x, deterministic rankings R_m, calibration map g,
       bypass threshold tau_B, diagnosability threshold tau_O
Output: action in {BYPASS, ARBITRATE, ESCALATE}

1  L(x) <- BuildEvidenceLedger(x, {R_m})
2  Phi(x) <- ExtractLedgerFeatures(L(x))
3  R(x) <- RawTrustScore(Phi(x))
4  C(x) <- g(R(x))
5  O(x) <- Diagnosability(L(x))
6  if C(x) >= tau_B and O(x) >= tau_O:
7      return BYPASS(det_topK, C(x), L(x))
8  if O(x) < tau_O:
9      return ESCALATE(missing_evidence(L(x)), C(x), L(x))
10 U(x) <- ConservativeLLMUtility(C(x), L(x))
11 if U(x) > 0:
12     return ARBITRATE(constrained_llm(det_topK, L(x)), C(x), L(x))
13 return ESCALATE(low_confidence_report, C(x), L(x))
```

## 4. Figure plan

### Figure 1: CREDENCE architecture

Purpose:

- establish CREDENCE as a system/control plane;
- show that LLM is one branch, not the center.

Layout:

```text
Pingmesh case -> deterministic rankers -> evidence ledger
        -> calibrated confidence -> risk gate -> BYPASS
                                -> diagnosability gate -> ESCALATE
                                -> utility gate -> ARBITRATE -> constrained LLM
```

Artifact source:

- `confidence_cases.jsonl` for evidence fields;
- `confidence_calibration.json` for \(g\), \(\tau_B\), \(\tau_O\);
- `llm_value.csv` for utility bins.

Caption claim:

> CREDENCE turns RCA confidence into a routing decision among trust, semantic
> arbitration, and escalation.

### Figure 2: Evidence ledger example

Purpose:

- prove auditability;
- make the method tangible for operators.

Rows:

| Evidence group | Example fields | Support for Top-1 | Counter-evidence | Missingness |
| --- | --- | --- | --- | --- |
| Topology | path witnesses, candidate role | yes/no | alt path candidate | missing path |
| Temporal | alarm before symptom | yes/no | recovery-only | bad timestamp |
| Semantic | causal alarm, severity | yes/no | noisy alarm | no taxonomy |
| Agreement | votes, RRF | yes/no | disagreement | missing method |

Artifact source:

- one anonymized case from `confidence_cases.jsonl`;
- hash or pseudonymize device IDs.

### Figure 3: Risk-coverage frontier

Purpose:

- primary algorithm evidence.

Curves:

- CREDENCE;
- margin gate;
- entropy gate;
- agreement gate;
- no calibration;
- source-pretrained target-calibrated variant if available.

X-axis:

```text
BYPASS coverage
```

Y-axis:

```text
wrong-bypass risk upper bound U_CP
```

Mark:

- \(\alpha_B=0.05\) and/or \(\alpha_B=0.10\);
- selected operating point.

Artifact source:

- `risk_coverage.csv`.

Caption claim:

> CREDENCE selects the largest BYPASS region satisfying the same conservative
> risk budget.

### Figure 4: Reliability diagram

Purpose:

- show calibrated confidence is meaningful.

Curves:

- raw margin;
- raw CREDENCE score;
- calibrated CREDENCE confidence.

Artifact source:

- `calibration_bins.csv`;
- `confidence_calibration.json`.

Caption claim:

> Calibration turns evidence-trust scores into empirical correctness estimates.

### Figure 5: LLM rescue and harm by CREDENCE action

Purpose:

- justify "when not to ask the LLM."

Bars:

```text
action: BYPASS, ARBITRATE, ESCALATE
metrics: rescue rate, harm rate, net rescue, count
```

Artifact source:

- `llm_value.csv`;
- `paired_case_outcomes.csv`.

Caption claim:

> CREDENCE concentrates LLM calls where rescue outweighs harm and avoids calls
> on high-confidence deterministic hits.

### Figure 6: Diagnosability frontier

Purpose:

- establish ESCALATE as a real systems insight.

X-axis:

```text
diagnosability bin
```

Y-axis:

```text
deterministic Top-1/Top-3, LLM rescue, missing-evidence rate
```

Artifact source:

- `diagnosability_frontier.csv`.

Caption claim:

> Observation completeness stratifies both deterministic success and LLM value.

### Figure 7: Transfer-pretraining gain

Purpose:

- answer the small-data critique if public data helps.

Panels:

1. AUROC/AURC for deterministic correctness.
2. BYPASS coverage at fixed \(U_{CP}\).
3. ECE/Brier after target calibration.

Methods:

- target-only CREDENCE;
- source-only zero-shot;
- source-pretrained target-calibrated CREDENCE.

Artifact source:

- `transfer_results.csv`;
- `target_crossfit_splits.json`.

Caption claim:

> Public RCA data improves confidence ordering, while Pingmesh calibration
> remains responsible for the risk certificate.

## 5. Table plan

### Table 1: Dataset and evidence availability

Columns:

```text
cases
labels with primary root
median candidates
median alarms
path coverage
timestamp coverage
semantic coverage
LLM outputs available
```

Purpose:

- make small data honest;
- explain diagnosability.

Artifact:

- `confidence_extraction_summary.json`;
- `confidence_cases.jsonl`.

### Table 2: Main RCA and routing result

Columns:

```text
method
Top-1
Top-3
Top-5
MRR
LLM call rate
BYPASS coverage
wrong-bypass empirical risk
CP upper bound
latency
tokens
```

Rows:

- deterministic only;
- always LLM;
- margin gate;
- entropy gate;
- agreement gate;
- target-only CREDENCE;
- source-pretrained target-calibrated CREDENCE if available.

Purpose:

- main paper table.

### Table 3: Calibration quality

Columns:

```text
model
ECE
Brier
AUROC correctness
AURC
selected tau_B
selected bypass count
```

Purpose:

- show CREDENCE is not just a margin gate.

### Table 4: Ablation

Rows:

- full CREDENCE;
- no calibration;
- margin-only;
- no agreement;
- no semantic support/conflict;
- no diagnosability;
- no source pretraining.

Columns:

```text
coverage at alpha_B
CP upper bound
Top-3
LLM call rate
rescue/harm net
```

Purpose:

- defend each feature group.

### Table 5: Failure taxonomy

Rows:

- insufficient topology/path evidence;
- missing or unparseable timestamps;
- alarm storm / noisy semantic evidence;
- multiple plausible roots;
- LLM output parser failure;
- label ambiguity.

Columns:

```text
cases
percent
dominant action
recommended future telemetry
```

Purpose:

- make negative results publishable if risk-controlled bypass is weak.

## 6. Artifact-to-claim map

| Claim | Required artifact | Minimum evidence |
| --- | --- | --- |
| CREDENCE confidence is calibrated. | `calibration_bins.csv`, `confidence_calibration.json` | reliability diagram, ECE/Brier, bin denominators |
| CREDENCE controls BYPASS risk. | `risk_coverage.csv` | selected threshold with CP upper bound below \(\alpha_B\) |
| CREDENCE reduces LLM calls. | `paired_case_outcomes.csv` | lower call rate than always-LLM under non-inferior Top-K |
| CREDENCE avoids LLM harm. | `llm_value.csv` | high-confidence deterministic hits that LLM would break |
| ESCALATE is meaningful. | `diagnosability_frontier.csv` | low observability linked to weak deterministic and LLM performance |
| Public pretraining helps. | `transfer_results.csv` | better AURC/coverage than target-only after target calibration |

No artifact, no claim. This rule should be used aggressively during writing.

## 7. Exact paper wording snippets

### Design goal paragraph

> CREDENCE has three design goals. First, it must estimate trust in the
> deterministic diagnosis rather than trust in a language model explanation.
> Second, it must treat LLM reranking as a fallible intervention that can rescue
> a miss but can also harm a correct deterministic result. Third, it must detect
> cases where the available telemetry is too incomplete for either deterministic
> or LLM-based automation.

### Calibration paragraph

> We separate scoring from calibration. The raw scorer orders cases by evidence
> strength; the calibration map converts this ordering into a target-domain
> estimate of deterministic correctness. This distinction is essential because
> a large score gap may be reliable in one evidence regime and misleading in
> another.

### Risk paragraph

> CREDENCE's BYPASS decision is selected by a risk-coverage contract. For each
> threshold, we compute the set of cases that would bypass the LLM and the
> number of deterministic errors in that set. We then select the largest set
> whose one-sided Clopper-Pearson upper bound is below the configured
> wrong-bypass budget.

### LLM paragraph

> The LLM is not the default fallback for all low-confidence cases. CREDENCE
> calls it only when the evidence is sufficiently observable and the conservative
> rescue estimate exceeds expected harm and cost. Otherwise, the case is
> escalated with a missing-evidence report.

### Transfer paragraph

> Public RCA datasets are used only to pretrain domain-invariant evidence-trust
> features. Pingmesh calibration folds select the probability map and the BYPASS
> threshold. Thus source data may improve confidence ordering, but all
> deployable risk claims remain target-domain.

## 8. Writing checklist before submission

- Every numeric claim points to an artifact file.
- Every table includes denominators.
- Every calibration statement reports bin counts or confidence intervals.
- BYPASS risk claims distinguish calibration-set certificate from held-out
  empirical risk.
- Source-only zero-shot is labeled as transfer baseline, not main method.
- ESCALATE cases remain in denominators.
- Always-LLM harm is reported alongside LLM rescue.
- The paper never says "LLM improves RCA" without specifying the bin/action.
- If no safe threshold exists, the claim ladder is lowered rather than hidden.

## 9. Where this fits in the design package

- Use `credence_nsdi_final_blueprint.md` for advisor-level strategy.
- Use this document for Section 5 and the figure/table plan.
- Use `credence_algorithm_box_and_proofs.md` for proofs and equations.
- Use `server_handoff_runbook.md` for server-side execution.
- Use `server_artifact_acceptance_criteria.md` for artifact and evaluation
  acceptance gates.
