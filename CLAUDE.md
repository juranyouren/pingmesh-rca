# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project

RPG-Recon studies incident-specific device-level fault propagation graph reconstruction from fragmented network observations, including alarms, logs, Pingmesh/path observations, timestamps, and physical topology.

The target output is a directed propagation graph

$$G_P=(V,E_P),$$

not a reconstruction of real ECMP packet paths.

The current method should be understood as the following pipeline:

$$\boxed{\text{Raw Incident Evidence} \rightarrow G_E \rightarrow S \rightarrow q(a) \rightarrow \text{Anchor-Conditioned Reconstruction} \rightarrow G_P}$$

or, operationally:

Evidence Encoding → Local Relation Modeling → Anchor Estimation → Global Backbone Reconstruction → DAG Augmentation.

Do not describe the current method as the old "Stage 1 root ranking → Stage 2 graph reconstruction" design. Root/anchor estimation is now part of a unified propagation-reconstruction framework.

---

## Research Challenges

**C0 — Fragmented Observability**

Incident observations come from multiple systems such as alarms, logs, Pingmesh, and topology. Different vendors, device types, monitoring systems, and teams may describe the same underlying fault with different formats, fields, names, and semantics.

This means raw observations cannot be consumed as if they shared one clean schema or vocabulary.

**C1 — Local Ambiguity**

Fragmented observations make the propagation direction between abnormal devices difficult to determine.

For a locally related pair of devices, more than one directional hypothesis may remain plausible. The model should therefore preserve relation likelihoods rather than forcing an early discrete edge decision.

**C2 — Global Consistency**

Locally plausible relations may conflict when assembled globally. Propagation reconstruction therefore requires:

- selecting an appropriate global orientation reference (Anchor);
- constructing a connected and directed propagation backbone around that Anchor;
- enforcing structural consistency;
- optionally adding secondary high-confidence edges without introducing directed cycles.

---

## Research Invariants

These rules outrank convenience and "just make it run".

- **No label leakage.** Runtime inference must not read root or propagation labels. Ground-truth labels belong to evaluation only.
- **Topology grounding.** A predicted device-to-device propagation relation must be compatible with the available topology/context graph. Unknown or unavailable topology evidence must not be silently treated as a confirmed negative.
- **LLM is an evidence encoder, not an edge predictor.** The LLM normalizes and structures heterogeneous raw text. It must not directly emit the final propagation edges.
- **Preserve uncertainty.** Local modeling produces directional likelihoods. Do not collapse ambiguous relations too early.
- **Do not trust timestamps blindly.** Source timestamps may represent batch collection time rather than true event order. Temporal features must carry data-quality information and must not invent ordering from unreliable timestamps.
- **Device-scope ambiguous entities.** Interface names, aggregation-port names, peer addresses, and similar local identifiers must be scoped to their owning device unless a verified cross-device mapping exists.
- **Deduplicate semantic evidence across channels.** Two records from different systems may represent the same underlying fact and must not automatically count as two independent pieces of evidence.
- **No silent zero-filling.** Missing evidence is missing evidence, not "healthy".
- **No external LLM API dependency.** LLM inference runs on the server-side Huawei NPU environment with local model weights.

---

## Method

### 1. Incident Evidence Graph Construction

#### 1.1 Goal

For each incident, organize fragmented multi-source observations into an **Incident Evidence Graph**:

$$G_E=(V,E,X),$$

where:

- $V$: device nodes;
- $E$: physical links or context-adjacency relations;
- $X$: multimodal node/edge evidence features.

A device may carry evidence of different types and strengths. Devices without direct abnormal evidence may still remain in the graph as context nodes required for propagation reasoning.

#### 1.2 Input Evidence

The evidence graph may use, including but not limited to:

- alarms;
- logs;
- timestamps;
- Pingmesh / path observations;
- physical topology.

Do not assume all sources are equally reliable or semantically aligned.

#### 1.3 Recommended Evidence Data Model

Keep raw data and canonical evidence separate.

- **Device Table**: one record per device, containing static or semi-static attributes such as `device_id`, management IP, role, vendor, AZ, and device type.
- **Raw Event Tables**: source-specific raw records such as `syslog_event`, `alarm_event`, `pingmesh_event`, and `topology_event`. Preserve raw fields instead of prematurely forcing them into a single schema.
- **Evidence Vocabulary**: global mapping from heterogeneous source expressions to canonical evidence predicates.
- **Incident Evidence Mapping**: incident-local mapping from raw observations to canonical evidence facts.

Canonical evidence should preserve provenance back to all raw records that support it.

#### 1.4 LLM Semantic Evidence Encoder

Raw alarm and log text is semantically heterogeneous across vendors, departments, and monitoring systems. Use an **LLM Semantic Evidence Encoder** to convert raw textual evidence into a standardized structured representation.

Its responsibilities are:

1. **Normalization** — unify heterogeneous descriptions of the same phenomenon;
2. **Event Parsing** — parse subject/entity, object/peer, action/state, and time-related fields;
3. **Causal Semantics Extraction** — extract explicit or plausible causal semantics expressed in the source text;
4. **Evidence Vocabulary Mapping** — map heterogeneous expressions to canonical evidence predicates;
5. **Entity Grounding** — bind local object names to device-scoped entities;
6. **Evidence Deduplication** — merge duplicate cross-channel observations when they describe the same underlying fact;
7. **Unknown Handling** — retain unmatched events as UNKNOWN rather than forcing a wrong vocabulary mapping.

Example mappings may include:

```
BGP session down      -> adjacency_loss / bgp_adjacency_down
Neighbor unreachable  -> neighbor_unreachable
Increased loss        -> path_degradation
Latency degradation   -> path_degradation
```

A vendor-specific event such as:

```
LINEPROTO_5_UPDOWN
HCSO linkflap
```

may map to the same canonical predicate when both describe the same underlying interface-state change.

A local entity such as:

```
AggregatePort5
```

must become device-scoped, for example:

```
28.219.131.16::interface::AggregatePort5
```

Multiple raw observations may therefore become one canonical semantic evidence fact:

```
multiple raw observations
        -> one canonical evidence fact
        -> provenance = [all supporting raw records]
```

The LLM must not directly predict propagation edges in this stage.

#### 1.5 Evidence Quality and Time Semantics

Evidence records should carry quality metadata where possible, for example:

```json
{
  "time": {
    "raw_time": 1786068493156,
    "canonical_time": null,
    "time_quality": "unreliable",
    "time_reason": "batch_snapshot_timestamp"
  },
  "quality": {
    "mapping_confidence": 0.97,
    "quality_flags": ["unreliable_timestamp"]
  }
}
```

Important implementation rule: **a raw timestamp being present does not imply it is suitable for causal ordering.**

#### 1.6 Unknown Vocabulary Handling

Prefer a two-level flow:

1. device-level encoding against the existing vocabulary;
2. collect only UNKNOWN observations across the incident;
3. run an incident-level aggregation/temporary concept-induction step for those unknowns;
4. allow incident-local vocabulary extension when needed;
5. place possible reusable concepts into a **candidate vocabulary buffer** for later human review before global vocabulary extension.

Do not silently mutate the global vocabulary from a single incident.

---

### 2. Local Propagation Relation Modeling

#### 2.1 Goal

On the Incident Evidence Graph $G_E$, model possible propagation relations between locally related nodes.

For a candidate pair $(i,j)$, estimate both directional scores:

$$s(i\rightarrow j), \qquad s(j\rightarrow i).$$

Here $s(\cdot)$ is a **relation likelihood**, not a final discrete propagation edge.

#### 2.2 Evidence Used for Directional Relation Modeling

Combine evidence such as:

- **Neighbor Evidence** — consistency of neighboring abnormalities;
- **Path Evidence** — association among abnormal paths;
- **Log & Alarm Evidence** — semantic relations among canonicalized alarms/logs;
- **Temporal Evidence** — event ordering only when the timestamps/order are sufficiently trustworthy;
- **Topology Context** — physical/logical feasibility of propagation.

Conceptually:

$$\text{Evidence Aggregation} \rightarrow \text{Relation Likelihood}.$$

The purpose is to preserve multiple locally plausible hypotheses instead of making an early hard decision.

#### 2.3 Relation Likelihood Graph

After evaluating all local candidate pairs, build a directed candidate relation graph:

$$S=\{s(i\rightarrow j)\}.$$

Competing directions may coexist, for example:

$$s(i\rightarrow j)=0.82, \qquad s(j\rightarrow i)=0.27.$$

This is the explicit mechanism for handling **C1: Local Ambiguity**.

---

### 3. Anchor Estimation

#### 3.1 Goal

Local relation scores alone are insufficient to recover a globally consistent propagation structure. Estimate one or more **Anchor** candidates as global orientation references.

An Anchor is not merely a root-ranking output. Its role is:

> Provide a global orientation reference for assembling locally plausible relations.

#### 3.2 Graph Model

Encode the Incident Evidence Graph with a **Graph Attention Network (GAT)** and estimate:

$$q(a)=P(a\text{ is anchor}\mid G_E).$$

The model may output:

- one best Anchor;
- Top-K Anchor candidates;
- the full Anchor probability distribution $q(a)$.

Example:

$$q(R_3)=0.68, \qquad q(R_1)=0.21, \qquad q(R_5)=0.08.$$

#### 3.3 Role in the Full Method

The conceptual transition is:

$$\text{Anchor Estimation} \rightarrow \text{Anchor-Conditioned Graph Decoding}.$$

Anchor estimation and propagation reconstruction are part of the **same framework**. Do not implement them as unrelated objectives whose outputs are simply concatenated afterward.

This provides the global directional reference needed for **C2: Global Consistency**.

---

### 4. Anchor-Conditioned Propagation Reconstruction

#### 4.1 Goal

Given the Anchor distribution $q(a)$ and local relation likelihood graph $S$, reconstruct the final propagation graph:

$$G_P=(V,E_P).$$

The reconstruction must jointly consider local evidence strength and global structural consistency.

#### 4.2 Anchor-Conditioned Edge Weighting

For a given Anchor $a$, define the weight of a candidate directed edge $i\rightarrow j$ as:

$$w^{(a)}(i\rightarrow j)=\lambda_s s(i\rightarrow j)+\lambda_t\phi_{\mathrm{temp}}(i,j)+\lambda_p\phi_{\mathrm{ping}}(i,j)+\lambda_g\phi_{\mathrm{topo}}(i,j)+\lambda_a\phi_{\mathrm{anchor}}^{(a)}(i,j).$$

where:

- $s(i\rightarrow j)$: local propagation relation likelihood;
- $\phi_{\mathrm{temp}}(i,j)$: temporal consistency;
- $\phi_{\mathrm{ping}}(i,j)$: Pingmesh/path-observation consistency;
- $\phi_{\mathrm{topo}}(i,j)$: topology consistency;
- $\phi_{\mathrm{anchor}}^{(a)}(i,j)$: orientation consistency relative to Anchor $a$;
- $\lambda_s,\lambda_t,\lambda_p,\lambda_g,\lambda_a$: evidence weights.

If temporal evidence is unreliable, its feature/weight must reflect that uncertainty instead of creating a false causal order.

#### 4.3 Global Backbone Reconstruction

For each Anchor candidate $a$, first recover a maximum-evidence directed backbone using a **Maximum Evidence Arborescence**.

Use the **Chu–Liu/Edmonds** algorithm to find the maximum-score arborescence rooted at $a$:

$$T^{(a)}=\arg\max_{T\in\mathcal{A}(a)}\sum_{(i\rightarrow j)\in T} w^{(a)}(i\rightarrow j),$$

where $\mathcal{A}(a)$ is the set of valid directed spanning/arborescence structures rooted at $a$ under the candidate-graph constraints.

This step is responsible for:

- maintaining a globally coherent propagation backbone;
- preventing incompatible local high-score edges from being naively concatenated;
- extracting the core fault-propagation structure.

#### 4.4 DAG Augmentation

A tree backbone may be too sparse for real incidents with multiple propagation paths, parallel effects, or secondary influence relations.

After obtaining $T^{(a)}$, add secondary high-confidence edges only when they satisfy consistency constraints such as:

- sufficiently high local relation likelihood;
- consistency with the Anchor-defined global orientation;
- consistency with reliable temporal evidence;
- consistency with topology and Pingmesh/path observations;
- no clear contradiction with the existing propagation structure;
- no directed cycle.

The final graph is:

$$E_P = E_{\mathrm{backbone}} \cup E_{\mathrm{aug}},$$

$$G_P=(V,E_P).$$

---

## Data-Specific Constraints

Real incident data may contain all of the following simultaneously:

- **Semantic Heterogeneity** — different monitoring systems use different names, fields, and severity conventions for the same phenomenon;
- **Entity Ambiguity** — the same device/link may be referenced using management IPs, BGP-session IPs, tunnel IPs, or local interface names;
- **Temporal Unreliability** — timestamps may be batch-collection snapshots and may not reflect actual event order;
- **Evidence Redundancy** — multiple monitoring channels may duplicate the same underlying event.

Do not merge unrelated severity channels such as `alarm_level`, `alarm_weight`, `score`, and `delimitation` into a single number unless an explicit, documented calibration model defines how.

When raw description text and epoch timestamps disagree, preserve both and mark the inconsistency instead of silently "fixing" one from the other.

---

## LLM / NPU Runtime

### Environment

LLM inference runs on the server with Huawei NPU hardware. The data and NPU cards are server-side; the complete LLM experiments are not expected to run locally.

Do not add a cloud/external LLM API dependency as a fallback.

### Model Paths

Default larger model:

```bash
export PINGMESH_MODEL_PATH="${PINGMESH_MODEL_PATH:-/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B}"
```

Smaller available models:

```
/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-7B
/usr/share/large_language_models/Qwen2.5-0.5B
```

Use `PINGMESH_MODEL_PATH` as the normal model-selection interface unless there is a strong repository-specific reason not to.

### Shared LLM Engine

The process-level runtime pattern is:

```
program start
    -> initialize one LLM engine
    -> pass/reuse the same engine across different agents/modules
    -> shutdown at program end
```

Do not initialize a new heavyweight LLM engine separately for every agent or every evidence-encoding call. Repeated initialization wastes NPU memory and startup cost and may make experiments unstable.

Prefer dependency injection or a shared runtime/context object over module-local engine construction.

---

## Scripts and Experiment Outputs

### `scripts/`

Use `scripts/` for end-to-end orchestration and experiment-table filling, including:

- scripts that run the complete method;
- scripts that run an ablation/variant needed to fill one or more paper tables;
- scripts that combine preprocessing, inference, reconstruction, and evaluation into a reproducible workflow.

Every runnable shell script should place its normal invocation examples at the top of the script as comments, for example:

```bash
# Usage:
#   bash scripts/run_xxx.sh
#   PINGMESH_MODEL_PATH=/path/to/model bash scripts/run_xxx.sh --variant small
```

Do not require users to reconstruct the intended command by reading the implementation body.

### `scripts/common.sh`

`scripts/common.sh` is the central place for default experiment configuration, including common paths, model defaults, NPU-card configuration, and shared hyperparameters.

The goal is to avoid commands with a long list of manually repeated parameters.

Recommended pattern:

```bash
source scripts/common.sh

# Environment variables may override defaults before/while sourcing.
# Individual runner scripts should consume these shared defaults.
```

Avoid duplicating the same default values across many runner scripts.

### `res/`

Experiment results should be written under:

```
res/
```

Create a new timestamped output directory automatically for each run so results are not silently overwritten.

A simple convention is sufficient, for example:

```
res/<experiment>_<YYYYMMDD_HHMMSS>/
```

If variants are useful, include them before the timestamp:

```
res/<experiment>_<variant>_<YYYYMMDD_HHMMSS>/
```

Each result directory should contain enough configuration/provenance metadata to reproduce the run, especially:

- model path / model name;
- relevant evidence/model configuration;
- random seed if applicable;
- input dataset/version or incident list;
- code version/commit when available;
- evaluation settings.

---

## Coding Conventions

- Match the surrounding source language. Keep implementation docstrings/comments/CLI help in the repository's existing style; high-level research notes may remain Chinese where that is already the norm.
- New experiment entry points should expose a clear CLI and a normal `main()` entry point.
- Prefer explicit configuration and provenance over hidden global state, except for the intentionally shared process-level LLM engine.
- Never hard-code a workstation-only path for data/models that exist only on the NPU server.
- Keep raw observations immutable whenever practical; write normalized/canonical evidence as derived artifacts.
- Preserve provenance from canonical evidence back to raw observations.
- When adding temporal logic, require an explicit notion of timestamp quality/reliability.
- When adding new propagation-edge logic, state whether it affects local relation likelihood, Anchor estimation, backbone reconstruction, or DAG augmentation. Avoid adding one-off edge heuristics with no stage ownership.
- When introducing a new LLM agent, reuse the existing initialized engine rather than constructing a second engine.
