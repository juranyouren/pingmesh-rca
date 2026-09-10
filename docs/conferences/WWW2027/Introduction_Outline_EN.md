# Introduction Outline — English

Date: 2026-09-10. Status: six-part outline for drafting.

Companion files: [Chinese opening and prior-work prose](./Introduction_引入与以往工作_中文初稿.md) and [updated Chinese outline with figure-generation prompts](./Introduction_提纲_讨论稿.md).

**Central argument:** Identifying suspicious devices does not explain how a network incident affects other devices. Reconstructing that influence requires retaining uncertain local relations and organizing them into a coherent graph under competing root hypotheses.

## 1. Opening: an operator workflow after a Pingmesh alert

- Open with the repository's synthetic DEMO_001: endpoint loss between H1/H2, a C–S interface-down observation on C, a BGP transition on S, and a peer-state log on C. L1/L2 have no event records. Do not import the old demo prediction's fabricated route-withdrawal event.
- Show concrete illustrative operations: fix the incident window, open C/S records, match interface/peer evidence, record competing hypotheses in a troubleshooting tree, and check which device relations can be supported. The troubleshooting tree contains investigation questions; the output graph contains device influence hypotheses.
- Explain why a suspicious-device list leaves work unfinished: changing the assumed origin changes admissible graph structure; timestamp order does not prove direction; absent records on L1/L2 do not justify extending a propagation path.
- Position the task as diagnosis of network infrastructure supporting Web services. Establish service-to-endpoint and operational value with real evidence before making workload-specific or efficiency claims. The current example is not a measured production Web incident.
- Define the output as an incident-specific device influence graph under a single-device-root model, with evidence references and unresolved relations. Endpoints provide context and possible auxiliary targets, not an observed packet route.

**Figure 1:** introduce it in the opening paragraph. Follow the [case specification](./论文引入设计：从工程师排障现场到传播图恢复.md), using observed topology, operator actions, and conditional hypotheses in separate regions. No field record is currently available; keep the synthetic/workflow labels.

## 2. Prior work: four groups with different observations and outputs

- **Measurement and path-constrained localization — Pingmesh, deTector, NetBouncer, and TraceRCA.** Summarize endpoint monitoring, identifiable probe designs, controlled path measurements, and normal/abnormal call-trace coverage. These methods constrain faulty locations; their required measured routes or distributed traces are not implied by our topology and alarm records. Fault location or link health also leaves device influence directions unspecified. [Pingmesh](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/11/pingmesh_sigcomm2015.pdf), [deTector](https://www.usenix.org/conference/atc17/technical-sessions/presentation/peng), [NetBouncer](https://www.usenix.org/conference/nsdi19/presentation/tan), [TraceRCA](https://github.com/NetManAIOps/TraceRCA).
- **Alert aggregation and incident-scope analysis — COLA and SkyNet.** Acknowledge spatiotemporal statistics, topology, SOP-assisted reasoning, hierarchical alert organization, and localization support. Correlated alert groups and existing connectivity graphs describe membership, scope, or adjacency; they do not directly specify incident-specific influence directions. Do not claim these methods ignore topology or never use graphs. [COLA](https://arxiv.org/abs/2403.06485), [SkyNet](https://ennanzhai.github.io/pub/sigcomm25-skynet.pdf).
- **Event dependencies and propagation modeling — NetEventCause, NetCause, and Hawkeye.** NetEventCause already reconstructs an alarm-instance DAG under explicit timestamp assumptions. NetCause models propagation over heterogeneous incident topology for counterfactual root ranking. Hawkeye reconstructs PFC provenance with specialized flow/port telemetry. Compare event, device, and flow/port granularity; specialized versus available observations; and ranking versus explicit structure reconstruction. Historical training can support incident-specific inference. [NetEventCause](https://doi.org/10.1109/TNNLS.2025.3574316), [NetCause, 2026 preprint](https://arxiv.org/html/2606.13543v1), [Hawkeye](https://zhangmenghao.github.io/papers/SIGCOMM2025-Hawkeye.pdf).
- **Knowledge- and LLM-assisted diagnosis — RCACopilot and BiAn.** Explain diagnostic information collection, root-category prediction, device ranking, and reasoning with topology, timelines, and historical knowledge. Their diagnostic outputs must be distinguished from explicitly scored device propagation edges. Disclose unavailable knowledge or inputs in any adaptation. [RCACopilot](https://arxiv.org/abs/2305.15778), [BiAn](https://ennanzhai.github.io/pub/sigcomm25-bian.pdf).
- Define the remaining task as connecting competing root hypotheses, uncertain local device relations, and coherent incident-level structure. Avoid claiming that previous work does not reconstruct propagation, or that combining topology and time is novel by itself. Use four compact paragraphs in the Introduction, with detailed input and replication comparisons in Related Work.
## 3. Three concrete challenges

- **C1 — Origin uncertainty changes the space of reconstructable graphs.** Committing to one device does more than change a ranking: it constrains root reachability and can exclude alternative directions and branches before reconstruction. Different origins can yield different structures over the same devices. Retain a bounded set of origin–graph hypotheses for comparison under the same observations and local support, without treating graph validity as proof of a root. Ordinary RCA difficulty and Top-K selection alone are not the novelty claim.
- **C2 — Ambiguity of direct influence and direction.** Temporal order, alarm severity, physical adjacency, and a spatial cluster provide different circumstantial clues. In a schematic example, a root may affect two devices separately; an earlier alarm on one and a later, stronger alarm on the other do not establish influence between them. Both direction and the existence of a direct relation remain uncertain.
- **C3 — Local support does not ensure a coherent incident graph.** Independently favored directions may form a cycle, remain disconnected from the assumed root, or leave relevant abnormal devices unexplained. Even several valid acyclic graphs can compete. Under the chosen static DAG model, a cycle exposes incompatible local selections; avoiding cycles alone does not establish correctness.

**Evidence needed for C1:** compare frozen predicted-root and direct oracle-root reconstruction, Top-1/Top-K graph quality and cost, and fixed-root versus graph reranking. Measure rule-induced edge exclusions; do not presume graph reranking improves roots.

## 4. Motivation: preserve uncertainty, then organize evidence

- **For C1:** combine incident context, topology position, and event timing to retain origins for conditional reconstruction; candidate generation and graph assembly jointly address the coupling. Path conditioning uses endpoint anchors, topology distances, and a path corridor; it neither assumes an observed exact forwarding path nor guarantees that the root lies on it.
- **For C2:** retain support for forward influence, reverse influence, and no direct propagation before selecting hard edges. P0 produces normalized evidence support, not calibrated causal probabilities.
- **For C3:** use each candidate root as a starting condition for selecting compatible paths and assembling a graph. The root constrains admissible structure but does not itself prove edge directions. Top-K represents competing single-root hypotheses, not simultaneous roots.

## 5. Approach: two stages addressing three challenges

- **Stage 1, PC-STGR (conceptual M1), provides candidates for C1:** construct a path-conditioned Device–Event graph and learn incident-level root ranking from spatial and temporal evidence. Pass scored Top-K device candidates to reconstruction. Supervised root training remains required; describe optional self-supervised initialization only if selected for the evaluated configuration.
- **Stage 2, P0 (conceptual M2 + M3), completes conditional comparison for C1 and addresses C2/C3:** compute root-independent three-state support on raw adjacent device pairs, then perform root-conditioned path selection and DAG assembly. Targets include relevant event-bearing devices and endpoint anchors. Attach available evidence and retain alternatives or insufficient-evidence status.
- State the implementation boundary: current P0 admits only directions whose physical shortest-hop distance from the candidate root strictly increases. This is a modeling restriction stronger than general root reachability and acyclicity, not a universal propagation law. Describe constrained search, not guaranteed global optimization. Root–graph scoring does not imply improved root accuracy without evaluation.

**Figure 2 placement:** at the Method section opening. Show observations → PC-STGR → Top-K → P0 → device graph and evidence; expose P0's local-support construction and conditional assembly inside Stage 2.

## 6. Contributions and evidence plan

1. An incident-conditioned organization of origin–graph hypotheses that carries root uncertainty into reconstruction. Candidate ranking supports this task; RCA or Top-K alone is not claimed as new.
2. Root-conditioned device propagation reconstruction that separates uncertain local support from constrained graph assembly, addressing C2/C3 as the main methodological contribution.
3. Separate evaluation of root ranking and graph reconstruction under the [frozen metric design](./故障传播图指标调研与最终评价方案.md): directed-edge P/R/F1, nodes, and exact graphs only when labels are complete. Use controlled root settings and matched ablations to isolate each stage's role. Report structural validity separately from accuracy, distinguish raw from projected graph metrics, and reserve numerical improvements for verified comparisons.

### Baseline selection and controlled comparisons

- **Root-ranking table:** Topology+Temporal, SkyNet-inspired Alert Voting, NetEventCause-DeviceRank, and BiAn-adapt, compared with PC-STGR. NetCause is the priority additional learned baseline once its input mapping and implementation are established.
- **Fixed-root graph table:** Topology-SP, Evidence-SP, NetEventCause-Device with a disclosed device/graph adapter, and P0. Use the same OOF-predicted root for all methods; present oracle-root experiments separately. Evidence-SP shares P0 local support and is a controlled structure baseline, not an independent published method.
- **End-to-end table:** combine each root ranker with the same P0 and label it “X + P0”. Do not attribute P0's graph reconstruction to the external ranker.
- Keep LocalEdges, greedy structural filtering, representation ablations, and P4 separate from external baselines. Use incident-grouped training, common candidate sets and labels, transparent missing inputs, and local LLM inference.
- Keep legacy NEC/TraceRCA/BiAn scripts distinct from the new baseline framework. The new NEC reimplementation, BiAn adaptation, SkyNet-inspired voting, PCMCI+, and DYNOTEARS have explicit input/replication boundaries; implementation acceptance is not reproduced paper accuracy. See [baseline status](./Baseline实现进度与验收.md).

Detailed source mapping, adaptation rules, implementation audit, and the six-group initial comparison plan are in [Related Work and Baseline Selection](./Related_Work与Baseline选型.md). No new experiment results are asserted in this outline.