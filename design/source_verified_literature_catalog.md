# Source-verified literature catalog for CREDENCE

Date: 2026-06-27

This catalog records web-verified source entries that support CREDENCE. It is
not a final bibliography; it is a source-backed map for paper writing.

## 1. Production network diagnosis and monitoring

| Work | Venue/source | Verified URL | Source-backed fact | Relevance to CREDENCE |
| --- | --- | --- | --- | --- |
| Pingmesh: A Large-Scale System for Data Center Network Latency Measurement and Analysis | SIGCOMM 2015 | <https://www.microsoft.com/en-us/research/publication/pingmesh-large-scale-system-data-center-network-latency-measurement-analysis/> | Microsoft describes Pingmesh as a large-scale datacenter latency measurement and analysis system, running for years and collecting large volumes of latency data. | Establishes Pingmesh as a production-grade symptom detector, but not a full root-device confidence engine. |
| Pingmesh paper PDF | SIGCOMM 2015 | <https://conferences.sigcomm.org/sigcomm/2015/pdf/papers/p139.pdf> | The paper frames Pingmesh as a way to know latency between server pairs and aid troubleshooting. | Motivates why Pingmesh-triggered cases still need downstream RCA. |
| NetBouncer: Active Device and Link Failure Localization in Data Center Networks | NSDI 2019 | <https://www.usenix.org/conference/nsdi19/presentation/tan> | USENIX describes NetBouncer as using IP-in-IP probing to localize device/link failures in datacenters. | A strong NSDI system baseline for active localization; CREDENCE differs by calibrating trust in existing evidence rather than probing more paths. |
| NetAssistant: Dialogue Based Network Diagnosis in Data Center Networks | NSDI 2024 | <https://www.usenix.org/conference/nsdi24/presentation/wang-haopei> | USENIX describes an AI-enabled task-oriented dialogue system for network diagnosis, motivated by studying thousands of diagnosis cases. | Provides NSDI-style framing: real diagnosis workflows first, AI system second. |
| 007: Democratically Finding the Cause of Packet Drops | NSDI 2018 | <https://www.usenix.org/conference/nsdi18/presentation/arzani> | USENIX states that network failure symptoms may not directly correlate with where or why they occur. | Supports the paper's opening claim: Pingmesh symptoms and root causes are not the same object. |
| Passive Realtime Datacenter Fault Detection and Localization | NSDI 2017 | <https://www.usenix.org/conference/nsdi17/technical-sessions/presentation/roy> | USENIX describes correlating transport-layer metrics and path information to localize faulty links/switches in a production Facebook datacenter. | Supports path witnesses and partial-observability analysis. |
| Evolution of Aegis: Fault Diagnosis for AI Model Training Service in Production | NSDI 2025 | <https://www.usenix.org/conference/nsdi25/presentation/dong> | USENIX describes a production diagnosis system for AI model training service and its design/evolution. | Shows that production diagnosis evolution and deployment lessons are current NSDI material. |
| Flock: Localizing Root Causes of Performance Problems in Leaf-Spine Networks | SIGCOMM 2023 | <https://dl.acm.org/doi/10.1145/3603269.3604876> and <https://arxiv.org/abs/2305.03348> | The paper targets root-cause localization for performance problems in leaf-spine networks. | Adds a modern SIGCOMM baseline for datacenter performance RCA; CREDENCE focuses on calibrated trust and LLM deferment. |
| Everflow: Scalable Network Telemetry to Debug Large Datacenter Networks | SIGCOMM 2015 | <https://www.microsoft.com/en-us/research/publication/everflow-scalable-network-telemetry-to-debug-large-datacenter-networks/> | Microsoft presents Everflow as scalable telemetry/debugging for large datacenter networks. | Supports the observability side of CREDENCE: missing telemetry should affect diagnosability. |
| IntSight: Diagnosing SLO Violations with In-band Network Telemetry | SIGCOMM 2019 | <https://dl.acm.org/doi/10.1145/3341302.3342096> | ACM records IntSight as diagnosing SLO violations using in-band network telemetry. | Helps position CREDENCE against richer telemetry systems while emphasizing existing-data constraints. |
| NetPoirot: Automating Root-Cause Analysis of Cloud Performance Anomalies | SIGCOMM 2017 | <https://dl.acm.org/doi/10.1145/3098822.3098850> | ACM records NetPoirot as automating RCA for cloud performance anomalies. | Shows cross-signal cloud RCA is established; CREDENCE adds selective risk and LLM intervention accounting. |
| MicroRCA: Root Cause Localization of Performance Issues in Microservices | NOMS 2020 / IEEE | <https://ieeexplore.ieee.org/document/9110353/> | IEEE describes MicroRCA as locating root causes of performance issues in microservices by correlating application performance symptoms and system resource utilization. | Shows graph/correlation RCA is a mature baseline family; CREDENCE asks when such deterministic evidence should be trusted or deferred. |
| CloudRanger: Root Cause Identification for Cloud Native Systems | CCGRID 2018 / IBM Research | <https://research.ibm.com/publications/cloudranger-root-cause-identification-for-cloud-native-systems> and <https://dl.acm.org/doi/10.1109/CCGRID.2018.00076> | IBM Research describes CloudRanger as a system for root-cause identification in cloud native systems based on real incidents from IBM Bluemix. | Useful contrast for causal/random-walk RCA; CREDENCE does not replace rankers, but calibrates action around their output. |

## 2. LLM-assisted RCA and operations

| Work | Venue/source | Verified URL | Source-backed fact | Relevance to CREDENCE |
| --- | --- | --- | --- | --- |
| Towards LLM-Based Failure Localization in Production-Scale Networks / BiAn | SIGCOMM 2025 | <https://dl.acm.org/doi/10.1145/3718958.3750505> | ACM page reports extensive evaluations using 17 months of real cases, with accurate and fast failure localization. | Closest LLM-network RCA comparison; CREDENCE's novelty is deciding when LLM localization should be bypassed or invoked. |
| BiAn PDF mirror | SIGCOMM 2025 | <https://ennanzhai.github.io/pub/sigcomm25-bian.pdf> | The PDF describes BiAn as an LLM-based framework for operator-assisted incident investigation and error-device ranking. | Useful for detailed related-work reading and positioning. |
| TAMO: Fine-Grained RCA via Tool-Assisted LLM Agent | arXiv 2025 | <https://arxiv.org/abs/2504.20462> | arXiv abstract says TAMO uses tool-assisted LLM agents and multi-modal observation data for fine-grained RCA, addressing dynamic dependencies and context-window limitations. | Supports the claim that tools help LLM RCA, but CREDENCE focuses on whether to call the LLM. |
| RCAgent: Cloud Root Cause Analysis by Autonomous Agents with Tool-Augmented LLMs | ACM 2024 | <https://dl.acm.org/doi/10.1145/3627673.3680016> and <https://arxiv.org/abs/2310.16340> | ACM describes RCAgent as a tool-augmented LLM autonomous agent framework for practical and privacy-aware industrial RCA. | Shows the agentic-RCA direction is active; CREDENCE adds an outer trust/risk controller that can bypass or constrain such agents. |
| RCACopilot: Automatic Root Cause Analysis via Large Language Models for Cloud Incidents | arXiv 2023 | <https://arxiv.org/abs/2305.15778> | The paper introduces an LLM-powered on-call system for cloud incidents and reports evaluation on a year of real Microsoft incidents. | Strong LLM-RCA systems comparison; CREDENCE's evaluation should report when LLM-style reasoning rescues, harms, or should be avoided. |
| Exploring LLM-Based Agents for Root Cause Analysis | ACM 2024 | <https://dl.acm.org/doi/10.1145/3663529.3663841> | ACM describes an empirical evaluation of a ReAct agent with retrieval tools on out-of-distribution production incidents. | Supports the need to evaluate agent RCA under realistic distribution shift and not assume all low-confidence cases should be given to agents. |
| Stalled, Biased, and Confused: Reasoning Failures in LLMs for Cloud-Based RCA | arXiv 2026 | <https://arxiv.org/abs/2601.22208> | arXiv abstract reports a controlled empirical evaluation of LLM reasoning in RCA and a taxonomy of reasoning failures. | Strong support for do-no-harm routing and not trusting LLM reranking blindly. |
| PACE-LM: Calibrated Confidence Estimation with GPT-4 in Cloud Incident RCA | arXiv 2023 | <https://arxiv.org/abs/2309.05833> | arXiv abstract states the method produces calibrated confidence estimates for predicted root causes. | Directly adjacent confidence-estimation work; CREDENCE differs by using topology/temporal evidence ledgers and routing decisions. |
| Confidence Estimation by LLMs for Effective RCA | ACM 2024 | <https://dl.acm.org/doi/10.1145/3663529.3663858> | ACM page describes assigning reliable confidence scores to root-cause recommendations to help on-call engineers. | Establishes that confidence for RCA recommendations is an active research topic. |

## 3. LLM routing, cascades, and confidence-triggered reasoning

| Work | Venue/source | Verified URL | Source-backed fact | Relevance to CREDENCE |
| --- | --- | --- | --- | --- |
| FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance | arXiv 2023 | <https://arxiv.org/abs/2305.05176> | The paper studies LLM cascades for reducing cost while maintaining task quality. | Motivates cost-aware routing, but CREDENCE routes between deterministic RCA, constrained LLM arbitration, and escalation. |
| RouteLLM: Learning to Route LLMs with Preference Data | arXiv 2024 | <https://arxiv.org/abs/2406.18665> | The paper studies learning routers between cheaper and stronger LLMs using preference data. | Useful contrast: CREDENCE routes based on production network evidence, not only prompt/model preference. |
| Dynamic LLM Routing Survey | arXiv 2026 | <https://arxiv.org/abs/2605.18796> | The survey frames dynamic LLM routing as selecting models or reasoning paths adaptively. | Shows routing is a current LLM-systems topic; CREDENCE adapts routing to RCA risk, harm, and diagnosability. |

## 4. Selective prediction, calibration, and risk control

| Work | Venue/source | Verified URL | Source-backed fact | Relevance to CREDENCE |
| --- | --- | --- | --- | --- |
| Selective Classification for Deep Neural Networks | arXiv 2017 | <https://arxiv.org/abs/1705.08500> | The abstract frames selective classification as trading coverage for prediction performance and allowing a desired risk level. | Direct foundation for CREDENCE's BYPASS coverage vs wrong-bypass risk. |
| On Calibration of Modern Neural Networks | ICML 2017 / arXiv | <https://arxiv.org/abs/1706.04599> | The abstract defines confidence calibration as probability estimates representative of true correctness likelihood. | Justifies why score margins cannot be called confidence until calibrated. |
| A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification | arXiv 2021 | <https://arxiv.org/abs/2107.07511> | The abstract presents conformal prediction as a user-friendly paradigm for statistically rigorous uncertainty sets under weak assumptions. | Provides accessible formal language for split calibration and uncertainty. |
| Conformal Risk Control | arXiv 2022 / Google Research | <https://arxiv.org/abs/2208.02814> and <https://research.google/pubs/conformal-risk-control/> | The abstract says it extends conformal prediction to control expected values of monotone loss functions. | Inspires the risk-budgeted bypass threshold. |
| Learn then Test: Calibrating Predictive Algorithms to Achieve Risk Control | arXiv 2021 / AoAS | <https://arxiv.org/abs/2110.01052> | The abstract describes calibrating predictive algorithms to satisfy explicit finite-sample statistical guarantees via risk control. | Supports threshold-grid testing and explicit risk-control framing. |
| Learning to Defer / consistent estimators for deferral | PMLR 2020 | <https://proceedings.mlr.press/v119/mozannar20b.html> | This line of work studies predictors that can either predict or defer to a downstream expert. | Models the LLM as an expensive expert/arbiter rather than the default ranker. |
| Beta Calibration | AISTATS/PMLR 2017 | <https://proceedings.mlr.press/v54/kull17a.html> | PMLR describes beta calibration as a well-founded and easily implemented improvement on logistic calibration for binary classifiers. | Gives CREDENCE a small-data-friendly alternative to isotonic calibration. |
| Venn-Abers Predictors | UAI/arXiv 2014 | <https://arxiv.org/abs/1211.0025> | arXiv describes Venn-Abers predictors as a class of Venn predictors based on isotonic regression. | Supports calibrated probability estimation as a serious methodological lineage. |
| Distribution-Free, Risk-Controlling Prediction Sets | JACM/arXiv 2021 | <https://arxiv.org/abs/2101.02703> and <https://dl.acm.org/doi/10.1145/3478535> | The arXiv abstract states that prediction sets can control expected loss on future test points at a user-specified level using a holdout set. | Provides a stronger risk-control analogy for CREDENCE's wrong-bypass budget. |
| Deep Gamblers | NeurIPS/arXiv 2019 | <https://arxiv.org/abs/1907.00208> | The abstract frames selective classification as supervised learning with a rejection option and target coverage. | Useful contrast for abstention: CREDENCE abstains/escalates based on evidence diagnosability, not only model disconfidence. |

## 4.1 Domain adaptation and covariate shift

| Work | Venue/source | Verified URL | Source-backed fact | Relevance to CREDENCE |
| --- | --- | --- | --- | --- |
| A Theory of Learning from Different Domains | Machine Learning 2010 | <https://doi.org/10.1007/s10994-009-5152-4> | The paper develops theory for learning when training and test distributions differ across domains. | Supports the claim that public RCA source data should not be treated as target-domain evidence without Pingmesh calibration. |
| Conformal Prediction Under Covariate Shift | NeurIPS/arXiv 2019 | <https://arxiv.org/abs/1904.06019> | The paper studies conformal prediction when training and test covariate distributions differ. | Useful background for domain-shift-aware calibration, while CREDENCE keeps the main certificate target-domain. |
| A PAC-Bayesian Approach for Domain Adaptation with Specialization to Linear Classifiers | ICML/arXiv 2013/2015 | <https://arxiv.org/abs/1506.04562> | The work frames domain adaptation through PAC-Bayesian generalization ideas. | Motivates the optional hierarchical/PAC-Bayesian source-prior variant for small Pingmesh data. |

## 5. Public RCA datasets for transfer pretraining

| Work | Venue/source | Verified URL | Source-backed fact | Relevance to CREDENCE |
| --- | --- | --- | --- | --- |
| RCAEval | GitHub / Zenodo / benchmark papers | <https://github.com/phamquiluan/RCAEval> and <https://zenodo.org/records/14590730> | The project describes RCAEval as an open-source benchmark with nine datasets, 735 real failure cases, and reproducible RCA baselines for microservice systems. | Best candidate source dataset for pretraining confidence on method-case correctness and multi-source RCA evidence. |
| OpenRCA | ICLR 2025 / Microsoft GitHub | <https://github.com/microsoft/OpenRCA> and <https://microsoft.github.io/OpenRCA/> | The repository describes a benchmark for assessing LLM root-cause analysis over telemetry including KPI time series, dependency trace graphs, and semi-structured log text. | Useful for LLM-intervention and semantic/noisy-telemetry confidence features, but target calibration must remain Pingmesh-specific. |
| LEMMA-RCA | arXiv 2024 / project page | <https://lemma-rca.github.io/> and <https://arxiv.org/abs/2406.05375> | The project describes a multi-modal, multi-domain RCA dataset collection spanning IT operations and OT operations with real system faults. | Candidate source corpus for domain-invariant evidence coverage, missingness, and multi-modal RCA difficulty. |
| Aiops-Dataset | GitHub dataset | <https://github.com/bbyldebb/Aiops-Dataset> | The repository describes replayed real system failures in a microservice e-commerce system, with logs, metrics, traces, and labeled root causes. | Candidate additional source data if download/licensing is workable. |
| Root Cause Analysis for Wireless Network Faults Localization | ICASSP 2022 challenge | <https://signalprocessingsociety.org/publications-resources/data-challenges/root-cause-analysis-wireless-network-faults-localization> | IEEE Signal Processing Society hosts a data challenge for wireless network fault localization. | A more network-like source dataset than microservices, but wireless faults differ from Pingmesh datacenter RCA. |

These datasets should be used for source pretraining, representation learning,
or transfer baselines. They should not be used to certify Pingmesh BYPASS risk
without target-domain calibration.

## 6. Statistical validation and paired evaluation

| Work | Venue/source | Verified URL | Source-backed fact | Relevance to CREDENCE |
| --- | --- | --- | --- | --- |
| McNemar's test | Psychometrika 1947 / DOI | <https://doi.org/10.1007/BF02295996> | Classic paired test for correlated proportions from the same subjects/items. | Useful for reporting discordant Top-1 outcomes between CREDENCE and baselines. |
| The Use of Confidence or Fiducial Limits Illustrated in the Case of the Binomial | Biometrika 1934 / DOI | <https://doi.org/10.1093/biomet/26.4.404> | Clopper and Pearson introduced exact confidence limits for the binomial case. | Supports conservative wrong-bypass upper bounds for selected BYPASS sets. |
| Comparing Areas under Correlated ROC Curves | Biometrics 1988 / JSTOR DOI | <https://doi.org/10.2307/2531595> | DeLong et al. provide a nonparametric approach for comparing correlated ROC areas. | Optional formal comparison for AUROC of confidence scores on the same cases. |
| An Introduction to the Bootstrap | Chapman and Hall / CRC | <https://doi.org/10.1201/9780429246593> | Efron and Tibshirani's book is a standard reference on bootstrap confidence intervals. | Supports paired bootstrap intervals over Pingmesh cases. |
| A Study of Cross-Validation and Bootstrap for Accuracy Estimation and Model Selection | IJCAI 1995 | <https://www.ijcai.org/Proceedings/95-2/Papers/016.pdf> | Kohavi compares cross-validation and bootstrap methods for accuracy estimation and model selection. | Supports repeated cross-fitting and caution around model selection on small datasets. |
| Empirical Bernstein Bounds and Sample Variance Penalization | COLT/arXiv 2009 | <https://arxiv.org/abs/0907.3740> | Maurer and Pontil study empirical Bernstein bounds that incorporate sample variance. | Optional robustness reference for bounded loss summaries when variance is informative. |
| Time-uniform, nonparametric, nonasymptotic confidence sequences | Annals of Statistics/arXiv 2021 | <https://arxiv.org/abs/1810.08240> | The paper develops confidence sequences valid uniformly over time under broad conditions. | Optional future extension for monitoring CREDENCE risk as more Pingmesh cases arrive. |
| Controlling the False Discovery Rate | JRSS B 1995 / DOI | <https://doi.org/10.1111/j.2517-6161.1995.tb02031.x> | Benjamini and Hochberg introduce false discovery rate control for multiple testing. | Supports treating many ablation p-values as secondary or applying multiplicity control. |

These statistical sources are not RCA contributions. They support the empirical
discipline needed to make CREDENCE's small-data evaluation credible.

## 7. How these sources support the CREDENCE claim

The source-backed argument is:

1. Production network diagnosis papers show that datacenter RCA is a deployable
   systems problem, not merely an offline ML benchmark.
2. Pingmesh and packet/path diagnosis papers show that symptoms, paths, and root
   causes can be misaligned.
3. LLM-RCA papers show that semantic reasoning can help but is costly,
   unreliable, or prone to reasoning failures.
4. Calibration and selective-prediction papers show how to turn confidence into
   a measurable risk-coverage contract.
5. Generic LLM-routing papers show that cost-aware routing is important, but
   they do not address topology-aware RCA confidence or diagnosability.
6. Public RCA datasets make source pretraining feasible, but they also motivate
   the need for target-domain calibration before making Pingmesh risk claims.
7. Paired statistical evaluation prevents the paper from overstating gains on a
   small internal case set.
8. CREDENCE's novelty is the join: a production network RCA control plane that
   uses evidence-ledger features and calibration data to decide BYPASS,
   ARBITRATE, or ESCALATE per case.

## 8. Citation hygiene

When drafting the final paper:

- Prefer official USENIX/ACM/arXiv/Google Research pages over secondary blogs.
- For each source-backed claim, cite the source that actually supports it.
- Avoid claiming conformal-style future guarantees unless the calibration split,
  threshold family, and exchangeability assumption are explicit.
- Treat 2026 arXiv/FORGE work as recent LLM-RCA evidence, not as established
  network-systems precedent.
