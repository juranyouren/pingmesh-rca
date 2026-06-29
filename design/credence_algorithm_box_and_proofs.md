# CREDENCE algorithm boxes and proof obligations

Date: 2026-06-27

This document turns CREDENCE into proof-ready paper material by writing the
method as explicit algorithms, assumptions, lemmas, and validation checks.

The goal is to make the paper's main innovation defensible:

> CREDENCE is not a heuristic confidence score. It is a calibrated selective
> diagnosis policy with explicit risk, coverage, intervention, and
> diagnosability accounting.

## 1. Objects

For case \(i\):

- \(X_i\): deployable evidence before LLM arbitration.
- \(Y_i\): labeled acceptable root devices.
- \(\pi_i^{det}\): deterministic Top-K ranking.
- \(\hat{y}_i^{det}\): deterministic Top-1.
- \(Z_i=\mathbf{1}[\hat{y}_i^{det}\in Y_i]\): deterministic Top-1 correctness.
- \(\Phi(X_i)\): evidence-ledger features.
- \(R_i=f_\theta(\Phi(X_i))\): raw confidence score.
- \(C_i=g(R_i)\): calibrated confidence.
- \(O_i\): diagnosability score.
- \(A_i\): action in \(\{\mathrm{BYPASS},\mathrm{ARBITRATE},\mathrm{ESCALATE}\}\).

The paper should repeatedly state:

\[
C_i \approx P(Z_i=1\mid \Phi(X_i)).
\]

It is confidence in the deterministic Top-1 answer, not confidence in every
future action or in the LLM.

## 2. Algorithm 1: evidence ledger construction

```text
Input:
  case directory with deterministic rankings, topology/path evidence,
  timestamps, alarms/logs, semantic categories, and optional LLM output

Output:
  evidence ledger L_i and feature vector Phi_i

1. Read deterministic Top-K rankings from topology, temporal, semantic, and
   fused methods.
2. Normalize per-method scores within the candidate set using robust scale
   estimates such as MAD or IQR.
3. Compute score-shape features:
   margin, tail gap, entropy, softmax Top-1 mass.
4. Compute method-agreement features:
   Top-1 votes, RRF support, rank standard deviation, Top-K overlap.
5. Compute diagnosability features:
   path coverage, topology coverage, alarm-device ratio, timestamp coverage,
   semantic coverage, missing-evidence indicators.
6. Compute semantic support and counter-evidence:
   causal alarms, high-severity alarms, recovery/noise-only alarms, stronger
   semantic countercandidate flag.
7. Emit L_i, Phi_i, and missingness indicators.
```

Inference-time fields must exclude labels, root visibility, deterministic hit,
LLM hit, rescue, and harm.

## 3. Algorithm 2: cross-fitted confidence training

```text
Input:
  labeled cases D = {(Phi_i, Z_i)}_{i=1}^n
  repeat count R
  fold count K

Output:
  out-of-fold raw scores R_i, calibrated confidences C_i

for repeat r in 1..R:
  split D into K folds
  for fold k in 1..K:
    train monotone raw confidence model f_{r,k} on D \\ fold_k
    predict raw scores R_i for i in fold_k
aggregate out-of-fold raw scores across repeats
fit calibration map g using only training/calibration folds
emit calibrated confidence C_i = g(R_i)
```

Recommended raw model:

\[
R_i=\sigma(\beta_0+\beta^\top \Phi_i)
\]

with monotonicity constraints:

- evidence agreement, separation, observability, and semantic support should
  increase confidence;
- entropy, rank disagreement, missingness, and counter-evidence should decrease
  confidence.

Recommended calibration hierarchy:

1. binned beta-binomial lower confidence if data is very small;
2. beta calibration if data supports a smooth parametric map;
3. isotonic regression if calibration folds are sufficiently large.

## 4. Algorithm 3: risk-controlled BYPASS selection

```text
Input:
  calibration predictions {(C_i, Z_i)}
  finite threshold grid T
  wrong-bypass budget alpha_B
  confidence level delta
  minimum bypass count b_min

Output:
  selected bypass threshold tau_B or "no safe threshold"

valid_thresholds = []
for tau in T:
  B_tau = {i : C_i >= tau}
  if |B_tau| < b_min:
    continue
  e_tau = sum_{i in B_tau} (1 - Z_i)
  U_tau = one_sided_CP_upper(e_tau, |B_tau|, delta / |T|)
  if U_tau <= alpha_B:
    add (tau, |B_tau|, e_tau, U_tau) to valid_thresholds

if valid_thresholds is empty:
  return "no safe threshold"
else:
  return tau with maximum |B_tau|, breaking ties by smaller U_tau
```

The "no safe threshold" outcome is important. If the server data is too small
or the confidence model is weak, CREDENCE should report that no statistically
defensible BYPASS region exists under the chosen risk budget.

## 5. Algorithm 4: serving-time triage

```text
Input:
  new case x
  trained feature extractor Phi
  confidence model f
  calibration map g
  selected threshold tau_B
  diagnosability threshold tau_O
  conservative LLM utility model U_LLM_lower

Output:
  decision, ranking, confidence report, evidence ledger

1. Build evidence ledger L(x) and features Phi(x).
2. Compute raw confidence R(x) = f(Phi(x)).
3. Compute calibrated confidence C(x) = g(R(x)).
4. Compute diagnosability O(x).
5. If tau_B exists and C(x) >= tau_B:
      return BYPASS, deterministic Top-K, C(x), L(x)
6. If O(x) < tau_O:
      return ESCALATE, missing-evidence report, C(x), L(x)
7. Compute lower-bound LLM utility U_LLM_lower(x).
8. If U_LLM_lower(x) > 0:
      call LLM constrained to deterministic Top-K
      return ARBITRATE, LLM-reranked Top-K, C(x), L(x)
9. Return ESCALATE or low-confidence deterministic Top-K with warning.
```

The LLM is never allowed to invent an arbitrary candidate outside Top-K in the
main system result. An unconstrained LLM can be an ablation.

## 6. Lemma 1: calibration meaning

Suppose \(g\) is fit on calibration predictions \((R_i,Z_i)\). For a confidence
bin \(b\), let \(n_b\) be the number of calibration cases and \(h_b\) the number
of deterministic Top-1 hits. A conservative binned confidence can be:

\[
C_i =
\mathrm{BetaQuantile}_{\eta}
\left(h_b+a_0,\ n_b-h_b+b_0\right),
\quad i\in b.
\]

Then \(C_i\) is a lower credible/confidence-style estimate of deterministic
correctness in that bin, depending on whether the paper presents it as Bayesian
beta-binomial smoothing or frequentist lower confidence accounting.

Paper guidance:

- Use "calibrated lower estimate" if using beta-binomial bins.
- Use "calibrated probability estimate" only after reliability diagrams show
  that confidence tracks empirical correctness.
- Avoid saying "guaranteed probability" unless the exact statistical guarantee
  is written beside the claim.

## 7. Lemma 2: simultaneous BYPASS risk bound

For threshold \(\tau\), let:

\[
B(\tau)=\{i:C_i\ge \tau\},
\quad
n_\tau=|B(\tau)|,
\quad
e_\tau=\sum_{i\in B(\tau)}(1-Z_i).
\]

Define:

\[
U(\tau)=
\mathrm{BetaInv}
\left(1-\frac{\delta}{|\mathcal{T}|};
e_\tau+1,\ n_\tau-e_\tau
\right).
\]

For a fixed finite threshold family \(\mathcal{T}\), with probability at least
\(1-\delta\), all thresholds satisfy their one-sided binomial upper bounds
simultaneously. Therefore selecting any threshold whose \(U(\tau)\le \alpha_B\)
inherits the calibration-set upper-risk certificate.

Proof sketch:

1. For fixed \(\tau\), Clopper-Pearson gives one-sided coverage for the
   Bernoulli error rate among selected cases.
2. Assign failure probability \(\delta/|\mathcal{T}|\) to each threshold.
3. A union bound gives simultaneous validity over the fixed threshold grid.
4. The selected threshold is a data-dependent member of this simultaneously
   valid set, so it inherits the bound.

The proof requires the threshold grid to be fixed before inspecting test
performance. Threshold candidates can be quantiles of calibration confidences
if the quantile rule is fixed in the protocol.

## 8. Sample-size sanity table

This table shows why the paper must be cautious with small data. It assumes:

- zero wrong BYPASS cases in the calibration selected set;
- \(\delta=0.05\);
- \(|\mathcal{T}|=20\) tested thresholds;
- one-sided Clopper-Pearson plus Bonferroni.

With \(e=0\), the upper bound is:

\[
U = 1-\left(\frac{\delta}{|\mathcal{T}|}\right)^{1/n}.
\]

| Bypassed calibration cases \(n\) | Upper risk bound with zero errors |
| ---: | ---: |
| 10 | 0.451 |
| 15 | 0.329 |
| 20 | 0.259 |
| 30 | 0.181 |
| 50 | 0.113 |
| 60 | 0.095 |
| 80 | 0.072 |
| 100 | 0.058 |
| 120 | 0.049 |
| 150 | 0.039 |
| 200 | 0.030 |
| 300 | 0.020 |

Interpretation:

- If the selected BYPASS set has only 20 calibration cases, zero errors still
  does not justify a 5% wrong-bypass claim.
- To claim a 5% conservative upper bound under this setting with zero errors,
  the selected BYPASS set needs roughly 120 calibration cases.
- If the server dataset has around 150 total cases, the paper should report
  repeated cross-fitting and confidence intervals, but it should avoid strong
  universal claims.

This table is a useful defense against reviewer skepticism. It shows that the
paper understands what small-data risk control can and cannot prove.

## 9. Lemma 3: LLM utility lower bound

Let \(b_i\) be an arbitration bin based on confidence, semantic conflict,
method disagreement, and diagnosability. Estimate:

\[
\underline{p}_r(b_i)\le P(\mathrm{rescue}\mid b_i),
\]

\[
\overline{p}_h(b_i)\ge P(\mathrm{harm}\mid b_i).
\]

Define lower-bound utility:

\[
\underline{U}_{LLM}(i)=
(1-C_i)\underline{p}_r(b_i)V_r
-C_i\overline{p}_h(b_i)V_h
-\lambda_{tok}C_{tok}(i)
-\lambda_{lat}C_{lat}(i).
\]

If \(\underline{U}_{LLM}(i)>0\), then the LLM has positive estimated value even
under conservative rescue/harm accounting. If it is non-positive, the paper can
argue that calling the LLM is not justified by available evidence.

This lemma is not a finite-sample theorem unless the lower/upper bounds are
constructed with a specified confidence procedure. It is still valuable because
it turns LLM usage into an auditable decision rather than a default behavior.

## 10. Failure modes and required responses

| Failure mode | What it means | Paper response |
| --- | --- | --- |
| No safe \(\tau_B\) exists | Confidence cannot support risk-controlled bypass. | Present CREDENCE as diagnostic analysis; lower claims; improve features. |
| Calibration curve is poor | Raw evidence model does not predict correctness. | Add ablation and feature analysis; avoid probability language. |
| Margin-only matches full CREDENCE | Fancy feature groups do not add predictive value. | Reframe CREDENCE as formalizing a simple deployable rule; keep risk-control contribution. |
| LLM rescue and harm both low | LLM reranking is not useful on these cases. | CREDENCE becomes a cost-saving do-no-harm gate. |
| LLM helps even high-confidence cases | Deterministic confidence is missing useful semantic evidence. | Add semantic features or revise BYPASS threshold; report honestly. |
| ESCALATE dominates | Existing data lacks enough evidence for automatic RCA. | Make diagnosability frontier central and propose recollection instrumentation. |

## 11. Reviewer-ready claims

Strong claim, if server results support it:

> CREDENCE bypasses a substantial fraction of Pingmesh-triggered RCA cases while
> keeping a conservative upper bound on wrong-bypass risk below the configured
> budget, and routes LLM arbitration toward bins with positive rescue/harm
> tradeoff.

Moderate claim, if data is small but patterns are clear:

> CREDENCE exposes a calibrated risk-coverage frontier for deterministic RCA
> and shows that low-confidence cases split into LLM-beneficial ambiguity and
> low-diagnosability cases that should be escalated.

Fallback claim, if the full model is weak:

> CREDENCE provides an auditable evaluation framework for when to trust,
> arbitrate, or escalate Pingmesh RCA outputs, revealing the limits of both
> margin gates and always-on LLM reranking.

## 12. Sources to cite for this section

- Beta calibration: <https://proceedings.mlr.press/v54/kull17a.html>
- Venn-Abers predictors: <https://arxiv.org/abs/1211.0025>
- Distribution-free risk-controlling prediction sets:
  <https://arxiv.org/abs/2101.02703>
- Selective Classification for Deep Neural Networks:
  <https://arxiv.org/abs/1705.08500>
- Learn then Test: <https://arxiv.org/abs/2110.01052>
- Conformal Risk Control: <https://arxiv.org/abs/2208.02814>
- Deep Gamblers: <https://arxiv.org/abs/1907.00208>

The paper should cite these as mathematical inspiration, not as direct prior
solutions to network RCA.
