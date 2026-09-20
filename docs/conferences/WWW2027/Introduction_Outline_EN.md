# Introduction Outline — English

Date: 2026-09-16. Status: six-part outline for drafting. See the [latest-scheme synchronization note](./2026-09-16_最新方案与文档同步说明.md) and the [Chinese case specification](./论文引入设计：从工程师排障现场到传播图恢复.md).

**Central argument:** Web services depend on DCN communication. A Pingmesh alert exposes an anomaly, but a suspicious-device ranking does not explain device-to-device influence or which recovery actions remain necessary. RPG-Recon reconstructs an incident-specific, device-level propagation explanation under a single-device anchor, retaining local ambiguity and enforcing global consistency. Any action or efficiency benefit remains a hypothesis until measured with common feedback and stopping rules.

## 1. Opening: from a Pingmesh anomaly to a recovery decision

- Open with the PPT's illustrative A/B/C/D relation A→B→{C,D} and ranking A,C,D,B. Because A is already ranked first, the possible value is action organization after ranking, not improved root localization.
- Explain that “four devices inspected → two devices handled” is an illustrative count, not a 50% efficiency or MTTR result. The necessity of handling B after A is repaired, the meaning of C/D's `Established` state, feedback latency, permissions, and stopping rule are unspecified.
- Use the old synthetic `DEMO_001` separately as a reproducible observation example: endpoint loss, C/S events, topology, and missing records. Do not mix it with the PPT case or import `demo_predictions.json`.
- Define the output as an incident-specific device influence DAG with a candidate/selected single-device anchor, explicit nodes, evidence references, alternatives, and unknown relations. It is not a packet-level ECMP path, a complete causal model, or an automatic repair policy.

**Figure 1:** separate observations, candidate relations, operator actions, and inferred graph structure. Label the PPT case illustrative; label DEMO_001 synthetic. Operation arrows are not propagation edges.

## 2. Prior work: distinguish observations, granularity, and output

- **Measurement and path-constrained localization — Pingmesh, deTector, NetBouncer, TraceRCA.** These constrain fault locations with endpoint, controlled-path, or distributed-trace observations that are not implied by our device alarms and raw topology.
- **Alert aggregation and incident scope — COLA and SkyNet.** These organize correlated alerts, topology context, SOP reasoning, or hierarchical alert structure. Such organization does not automatically specify incident-specific device influence directions.
- **Event dependency and propagation modeling — NetEventCause, NetCause, Hawkeye.** NetEventCause reconstructs an alarm-instance propagation DAG; NetCause uses heterogeneous incident context; Hawkeye uses specialized PFC/port telemetry. Compare event/device/flow-port granularity and evaluation targets.
- **Knowledge- and LLM-assisted diagnosis — RCACopilot and BiAn.** These support information collection, root categories, device ranking, and explanations. Ranking or natural-language reasoning is not automatically a scored device-edge graph.

Do not claim that prior work only outputs lists or never uses graphs. The remaining task is to reconstruct a device-level, incident-specific structure from incomplete Pingmesh-triggered observations while carrying competing anchors, local ambiguity, and evidence gaps into evaluation.

## 3. Two concrete challenges

- **C1 — Local Ambiguity.** For an adjacent pair, both the existence of a direct relation and its direction are uncertain. Time order, severity, topology position, and interface/peer semantics are circumstantial evidence; missing records are unknown, not a confirmed No Direct relation. Retain forward, reverse, conflict, and unknown support before hard edge selection.
- **C2 — Global Consistency.** Locally supported relations may form cycles, conflict, detach from the candidate anchor, or leave abnormal branches unexplained. Graph legality does not establish correctness. Assemble a jointly checkable explanation under a common anchor while preserving alternatives and uncovered portions.

Origin uncertainty is treated as an anchor-estimation error within M3 rather than a third challenge. Evaluate it with Shared fixed predicted roots, Direct Oracle roots, Top-1/Top-K comparisons, and root correction/corruption; do not assume graph reranking improves roots.

## 4. Motivation: evidence first, then anchor-guided reconstruction

- **M1 — Incident Evidence Graph Construction:** organize Pingmesh context, alarms, logs, timestamps, topology, evidence references, and gaps into a shared incident evidence basis. This is a conceptual responsibility, not a claim that an identically named implementation already exists.
- **M2 — Local Propagation Relation Modeling:** on raw adjacent device pairs, represent support for forward influence, reverse influence, No Direct, unknown, and conflict without prematurely committing to a final edge.
- **M3 — Anchor-Guided Global Propagation Reconstruction:** estimate or receive candidate anchors, construct conditional graphs, and apply global consistency constraints to select and merge local relations.

Top-K denotes competing single-device anchors, not simultaneous multiple roots. An anchor is a candidate start of the explanation graph, not automatically a confirmed physical root cause.

## 5. Approach and implementation boundary

- **Stage 1 / PC-STGR** supplies candidate anchor ranking from path-conditioned device-event context. It supports the anchor-candidate function of M3; it is not M1 merely because the conceptual labels have changed.
- **Stage 2 / P0** covers local support and anchor-conditioned path selection/DAG assembly, corresponding to M2+M3. M1 evidence organization is distributed across input preparation and propagation components.
- P0 currently keeps directions whose shortest raw-topology distance from the candidate anchor strictly increases. This is a modeling restriction stronger than generic reachability and acyclicity, not a universal propagation law or a guarantee of global optimality. Every output edge must map to raw `task_topo` adjacency; unknown relations remain masked.

**Figure 2 placement:** at the Method opening. Show incident evidence graph → local relations → anchor estimation/conditional construction/consistency → propagation explanation graph, and annotate the existing Stage 1/Stage 2 implementation mapping.

## 6. Contributions and evidence plan

1. An incident-conditioned organization of evidence, competing anchors, and propagation explanations that carries anchor uncertainty into graph reconstruction; RCA and Top-K alone are not claimed as novel.
2. A separation of local relation support from anchor-guided global assembly, with explicit alternatives, conflicts, and unknowns; this claim requires matched C1/C2 ablations.
3. A separate evaluation of graph quality and downstream decision value: directed-edge P/R/F1 and other graph measures only under the applicable frozen protocol, with raw/projected, fixed-root/Oracle, and end-to-end settings separated. Do not infer action or MTTR benefit from a static graph or an illustrative count.

### Falsifiable hypotheses

- H1: retaining competing local relations improves reconstruction over early hard direction selection.
- H2: full consistency-aware assembly improves graph accuracy after controlling graph size and pruning strength, not only cycle rate.
- H3: under identical initial ranking, observations, feedback, permissions, and stopping rules, graph assistance reduces redundant actions; without real action records, do not claim troubleshooting or MTTR gains.
- H4: anchor errors affect graph reconstruction; Shared, Direct Oracle, and full-flow controls separate anchor error from graph error.

All tests require verified incident-group splits and leakage controls for labels, pretraining, calibration, thresholds, and feedback. A model-generated graph cannot serve as independent ground truth, and a simulator cannot let that graph determine recovery outcomes. Detailed source mapping and baseline boundaries remain in [Related Work and Baseline Selection](./Related_Work与Baseline选型.md); this outline asserts no new experiment result.
