# INFOCOM-oriented Pingmesh RCA paper redesign

Date: 2026-07-11

## 1. Target and paper thesis

The primary target is IEEE INFOCOM. The paper should therefore be written as a
networking-method paper, not primarily as an LLM system or an operations case
study.

The central thesis is:

> A Pingmesh incident supplies two strong but incomplete conditions: affected
> endpoints and a fault reference time. Root-cause localization should use these
> conditions to focus topology and temporal evidence before any semantic
> reasoning, and should invoke expensive reasoning only when deterministic
> evidence is insufficient.

Recommended working title:

> Incident-Conditioned Spatio-Temporal Root Cause Localization for Multipath
> Data Center Networks

Alternative title that retains the hybrid reasoning contribution:

> Topology-Temporal Evidence Fusion with Selective Reasoning for
> Pingmesh-Triggered Root Cause Localization

The first title is preferred for INFOCOM because it places the networking
problem and algorithm before the LLM component.

## 2. COLA-style narrative structure

The introduction should imitate COLA's argument structure rather than its task:

1. Describe the operational chain: Pingmesh detects an end-to-end anomaly,
   operators retrieve physical topology and device events, and then need to
   identify the faulty physical device.
2. State the engineering phenomenon: ECMP obscures the actual forwarding path;
   one physical fault produces spatially propagated and temporally shifted
   symptoms; symptom devices may emit more alarms than the root device.
3. Group the most relevant existing methods into three categories and explain
   why their ideas are insufficient when applied to this task.
4. State the core insight: a credible device should receive mutually consistent
   support from incident-conditioned topology and temporal evidence.
5. Present three challenges and three corresponding modules.
6. Report the strongest verified result and summarize contributions.

The introduction should not use probing and monitoring systems as a rejected
method category. They may appear only in the background to explain how the
incident is triggered.

## 3. Problem definition

For one incident, the inference-time inputs are:

- Pingmesh source and sink endpoints;
- Pingmesh trigger time and scenario metadata;
- the physical device graph, including device roles and adjacency;
- alarms and logs associated with devices in the incident window.

The output is a Top-K ranking of physical root-cause devices. Ground-truth
labels are used only for offline evaluation.

The task differs from alert aggregation: the target is not a correlated alert
pair or incident cluster, but the physical device that initiated the observed
end-to-end failure.

## 4. Related-work organization

The INFOCOM 2023-2025 main-conference scan changes the emphasis of this
section. Network tomography is not merely background: it is the closest formal
family to the paper's task because it asks how end-to-end path outcomes constrain
internal failed devices under partial observability. The related-work argument
should therefore lead with path/topology-constrained localization, then explain
what event correlation and semantic reasoning contribute after that physical
constraint is established.

### 4.1 Path- and topology-constrained internal failure localization

Representative recent work:

- PROTON, INFOCOM 2023, uses Boolean network tomography and approximate
  failure centrality to guide recovery decisions when network state is partial,
  monitor budget is limited, and routing is uncontrollable.
- D2NeT, INFOCOM 2025, lets distributed monitors greedily select high-utility
  path probes and information exchanges, and tracks failures and restorations
  with approximate Bayesian support.
- FlowTM, INFOCOM 2024, is an adjacent tomography work showing that an
  inaccurate routing matrix can systematically bias inverse inference. It is
  evidence for routing uncertainty, not an RCA baseline.
- Hawkeye and SkeletonHunter show how mechanism-specific provenance or workload
  structure can sharply constrain a production diagnosis space.

How to write the gap:

The transferable principle is that an internal device must explain an observed
end-to-end path outcome. Directly applying network tomography is nevertheless
invalid here: PROTON and D2NeT actively select and repeatedly acquire binary
path observations, whereas post-incident Pingmesh diagnosis has a fixed passive
evidence set. Equal-cost rerouting and gray failures also violate a simple
working/failed path model. Mechanism-specific provenance is unavailable in a
generic Pingmesh incident. The proposed method must therefore estimate passive
support over feasible source-sink path corridors, cross-validate that support
with event time, and expose low-identifiability incidents instead of forcing a
confident answer.

### 4.2 Alert and event correlation

Representative recent work:

- COLA, ICSE-SEIP 2024: correlation mining handles confident alert pairs and an
  LLM reasons about uncertain pairs.
- SkyNet, SIGCOMM 2025: groups heterogeneous network alerts by time and location,
  constructs a hierarchical alert tree, and filters insignificant alerts.
- NetEventCause, TNNLS 2025: learns event excitation and propagation from
  historical alarm sequences without an explicit topology.

How to write the gap:

These methods provide useful ideas for reducing event volume and modeling event
dependence. However, if their outputs are directly converted into device
rankings, devices producing many derivative alarms can outrank a quiet root
device. Event co-occurrence or excitation also does not establish that a device
lies on a feasible source-sink propagation path. Finally, rare and unseen faults
provide limited historical support. Therefore, event correlation must be
constrained by the physical network and the current incident conditions.

### 4.3 Causal-graph and LLM-assisted root-cause analysis

Representative recent work:

- NRCAC, INFOCOM 2025, combines non-intrusive eBPF collection with a
  domain-knowledge-constrained causal-graph search for provider-side
  microservice RCA.
- RCACopilot, EuroSys 2024: collects diagnostic information and predicts cloud
  incident root-cause categories with an LLM.
- BiAn, SIGCOMM 2025: summarizes monitor data, performs device-level analysis,
  integrates topology and timeline pipelines, and ranks error devices.
- TAMO, 2025: gives an LLM specialized tools and time-aligned multimodal
  observations for cloud-native RCA.

How to write the gap:

These systems show that LLMs are useful for semantic evidence organization and
operator-facing explanations. Directly asking an LLM to process every device
and all raw telemetry is nevertheless expensive and sensitive to prompt length,
evidence ordering, and reasoning instability. In this project, unrestricted LLM
reranking does not improve the deterministic Top-1 result. The LLM should
therefore arbitrate only deterministic conflicts rather than serve as the main
ranker. NRCAC's causal-graph pruning also cannot be transplanted without an
equivalent set of host- or service-level causal variables: physical switch
alarms that share a hidden fault parent can create spurious correlations, while
unknown ECMP paths make edge direction underidentified.

## 5. Module 1: incident-conditioned path-temporal localization

Use the technical mechanism name:

> Incident-Conditioned Path-Temporal Localization (ICPTL)

The new name is more defensible for INFOCOM. "Path" states the physical
constraint supplied by a Pingmesh source-sink incident, while "localization"
matches the paper's output. "Spatio-temporal focusing" is too generic and does
not distinguish the method from arbitrary graph-score fusion.

### 5.1 Inputs and output

Inputs are the physical graph, source and sink endpoints, incident time, and
device events. The output is a device-level Top-K candidate set plus separate
topology and temporal evidence for every candidate.

### 5.2 Current mechanism that can be claimed

The current implementation contains three concrete operations and should be
described as a baseline version of ICPTL:

1. Alarm-aware personalized propagation on the directed physical topology.
2. Temporal ranking using burst, first-occurrence, and event-density signals.
3. Score-level fusion of the independently normalized topology and temporal
   rankings.

The verified 159-case result supports complementarity: topology alone obtains
50.31% Top-1, temporal alone 62.89%, and their fusion 76.10%.

### 5.3 Required strengthening for an INFOCOM submission

The current implementation is still close to a weighted heuristic. Packaging
alone is not enough for INFOCOM. The method should be strengthened in four ways:

1. Incident-conditioned feasible-path support. Replace the weak endpoint bonus
   with a source-sink path corridor or path-incidence prior over feasible ECMP
   alternatives. Do not claim reconstruction of the actual forwarding path.
2. Role- and degree-normalized propagation. Correct the central-node bias of
   Clos fabrics by normalizing evidence according to device role and local
   degree.
3. Volume-robust temporal evidence. Deduplicate repeated alarms and model
   relative onset differences so that a high-volume symptom device cannot win
   only by event count.
4. Reliability-aware fusion. Use observable case properties or calibrated
   ranker confidence to combine topology and temporal evidence, rather than a
   fixed equal-weight average.

The module should also output a diagnosability state. If the fixed passive
observations do not distinguish multiple devices that cover the same feasible
paths, the correct system behavior is to lower confidence or abstain. This is
the passive analogue of identifiability in network tomography and provides a
principled input to selective reasoning.

The paper must clearly distinguish the implemented method from future
enhancements. It must not claim causal path reconstruction unless the algorithm
actually estimates and evaluates a propagation path.

## 6. Module 2: evidence canonicalization, not accuracy enhancement

The architecture-level name Semantic Evidence Compression Layer (SECL) can be
retained, but its contribution should be defined as evidence budgeting and
canonicalization.

The current small-model summarizer is unlikely to improve localization accuracy
for two structural reasons:

- each device is summarized independently, so the model lacks cross-device
  context needed to distinguish a root cause from a downstream symptom;
- its input already contains a compact list of alarm names and topology fields,
  but omits much of the detailed alarm description that carries physical-link
  and port-state evidence.

Preferred design:

1. Canonicalize and deduplicate alarm types.
2. Preserve the earliest event, highest-severity event, physical-link-down
   descriptions, interface identifiers, and original timestamps.
3. Attach provenance so every compressed item can be traced back to raw data.
4. Enforce a deterministic per-device and per-case evidence budget.
5. Use the small model only as an optional textual renderer, not as a root-cause
   judge.

SECL should be evaluated by compression ratio, retained key-evidence recall,
token count, latency, and non-inferiority of Top-K accuracy. An accuracy increase
is welcome but is not required for the module's claim.

## 7. Module 3: selective root-cause reasoning

The Selective Root Cause Localization Layer (SRCL) receives the ICPTL rankings
and their evidence states. It routes cases as follows:

- consistent high-confidence evidence: accept the deterministic result;
- topology-temporal conflict or small Top-1 margin: invoke LLM arbitration;
- insufficient evidence from both views: abstain and request operator review.

This module should be evaluated as a selective prediction problem. Report:

- automatic coverage;
- selective Top-1 risk or error rate;
- LLM invocation rate;
- operator-review rate;
- end-to-end latency and token cost;
- accuracy relative to deterministic-only and full-LLM baselines.

The gate must be calibrated on a training/validation split and evaluated on a
held-out test split. Thresholds chosen directly on all 159 cases would weaken
the credibility of the result.

## 8. Proposed Introduction paragraph sequence

Paragraph 1: Explain the reliability importance of data center networks and the
Pingmesh-triggered incident workflow.

Paragraph 2: Describe the concrete engineering phenomenon: endpoints are known,
but ECMP hides the traversed path; faults propagate across Clos devices; alarm
onsets drift; symptom devices can be noisier than the root.

Paragraph 3: Discuss path/topology-constrained localization first. Explain that
network tomography gives the closest formulation, but requires active repeated
binary probes that are unavailable and unreliable for post-incident ECMP/gray
failure diagnosis.

Paragraph 4: Discuss alert/event correlation methods and state why correlation
does not yield a physical root device for this incident without feasible-path
support.

Paragraph 5: Discuss LLM RCA and state why unrestricted semantic reasoning is
too expensive and unstable for full-case device ranking.

Paragraph 6: State the core insight: root devices should explain feasible paths
affected by the current endpoints and receive consistent volume-robust temporal
support, while semantic reasoning should be reserved for unresolved conflicts.

Paragraph 7: Present the three challenges: path-temporal localization, evidence
budgeting, and timely trustworthy decision-making.

Paragraph 8: Introduce ICPTL, SECL, and SRCL in one-to-one correspondence
with the challenges.

Paragraph 9: Summarize the production dataset and verified main result without
overclaiming generality.

Paragraph 10: List contributions.

## 9. INFOCOM-oriented contribution statements

1. We formulate Pingmesh-triggered diagnosis as incident-conditioned physical
   device ranking in multipath data center networks, exposing why event volume
   and physical centrality are unreliable root-cause indicators.
2. We propose ICPTL, a deterministic localization method that combines
   incident-conditioned feasible-path support with volume-robust temporal
   evidence and exposes low-diagnosability incidents.
3. We design selective reasoning that accepts consistent deterministic results,
   invokes semantic arbitration only for conflicts, and abstains on
   low-diagnosability incidents.
4. We evaluate the method on production incidents with component ablations,
   held-out calibration, baseline comparison, sensitivity analysis, and
   efficiency measurements.

Contribution 2 must be updated to match the final implemented algorithm. The
current code does not yet fully support the endpoint-conditioned and
volume-robust wording.

## 10. Required evaluation matrix

Core baselines:

- alarm-count or Hot Device ranking;
- topology-only personalized PageRank;
- temporal-only ranking;
- event-correlation or NetEventCause-style baseline;
- fixed topology-temporal fusion;
- BiAn-style full LLM reranking;
- proposed selective pipeline.

Ablations:

- remove feasible-path/endpoint conditioning;
- remove role/degree normalization;
- remove temporal deduplication;
- remove relative onset;
- fixed versus reliability-aware fusion;
- deterministic evidence compiler versus small-model summary;
- no gate versus full LLM versus selective LLM.

Robustness and statistical analysis:

- parameter sensitivity for PageRank alpha, time window, Top-K, and gate
  thresholds;
- bootstrap confidence intervals for Top-1/Top-3/Top-5;
- breakdown by topology size, alarm volume, device role, and failure type;
- chronological or grouped train/validation/test split to prevent case leakage;
- an external or synthetic validation set if production data cannot be shared.

## 11. Venue assessment

INFOCOM is a CCF-A networking conference and explicitly includes data center
networking, network management, measurement and analysis, and reliability. The
topic is in scope.

The closest alternatives remain:

- CoNEXT, CCF B: suitable if the contribution remains a practical networking
  system with moderate algorithmic novelty;
- Computer Networks, CCF B journal: suitable for a longer evaluation and a
  complete engineering treatment;
- IEEE/ACM Transactions on Networking, CCF A journal: appropriate only after
  stronger algorithmic analysis and broader validation.

As of 2026-07-11, an authoritative INFOCOM 2027 call and deadline were not found
in the searched official pages. Do not put an unverified deadline into the work
plan.

## 12. Claims to avoid

- Do not call monitoring or probing systems inadequate simply because they solve
  a different task.
- Do not equate correlation with causality.
- Do not describe the current PageRank heuristic as causal propagation.
- Do not claim that small-model summarization improves accuracy without a
  controlled result.
- Do not use the historical 143-case result affected by the earlier leakage
  issue as evidence for the current method.
- Do not claim generality beyond the evaluated production environment without
  an external or synthetic validation.

## 13. Core references to verify in the bibliography

- Arrigoni et al. Tomography-based Progressive Network Recovery and Critical
  Service Restoration after Massive Failures. INFOCOM 2023.
  DOI: 10.1109/INFOCOM53939.2023.10228861.
- Qiao et al. Routing-Oblivious Network Tomography with Flow-Based Generative
  Model. INFOCOM 2024. DOI: 10.1109/INFOCOM52122.2024.10621139.
- Trombetti et al. Distributed Network Tomography for Failure Localization.
  INFOCOM 2025. DOI: 10.1109/INFOCOM55648.2025.11044548.
- Zhai et al. NRCAC: Non-Intrusive Microservice Root Cause Analysis Framework
  for Cloud Providers. INFOCOM 2025.
  DOI: 10.1109/INFOCOM55648.2025.11044716.

- Kuang et al. Knowledge-aware Alert Aggregation in Large-scale Cloud Systems:
  a Hybrid Approach. ICSE-SEIP 2024. DOI: 10.1145/3639477.3639745.
- Chen et al. Automatic Root Cause Analysis via Large Language Models for Cloud
  Incidents. EuroSys 2024. DOI: 10.1145/3627703.3629553.
- Wang et al. Towards LLM-Based Failure Localization in Production-Scale
  Networks. SIGCOMM 2025. DOI: 10.1145/3718958.3750505.
- Yang et al. SkyNet: Analyzing Alert Flooding from Severe Network Failures in
  Large Cloud Infrastructures. SIGCOMM 2025. DOI: 10.1145/3718958.3750536.
- Wang et al. Hawkeye: Diagnosing RDMA Network Performance Anomalies with PFC
  Provenance. SIGCOMM 2025. DOI: 10.1145/3718958.3750490.
- Liu et al. SkeletonHunter: Diagnosing and Localizing Network Failures in
  Containerized Large Model Training. SIGCOMM 2025.
  DOI: 10.1145/3718958.3750513.
- Dong et al. Evolution of Aegis: Fault Diagnosis for AI Model Training Service
  in Production. NSDI 2025, pages 865-881.
- Yuan et al. NetEventCause: Event-Driven Root Cause Analysis for Large Network
  System Without Topology. TNNLS 2025. DOI: 10.1109/TNNLS.2025.3574316.
