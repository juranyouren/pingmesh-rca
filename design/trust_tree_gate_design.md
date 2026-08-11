# Trust-Tree Gate Design

## Goal

The gate decides when deterministic RCA can be trusted and when local-LLM
arbitration is required. It uses two logical trust trees instead of a continuous
confidence score:

- `topo_trust_tree`: topology/PageRank evidence.
- `temporal_trust_tree`: temporal burst/early/density evidence.

Each tree returns `strong`, `weak`, or `uncertain`. The active router is
`configurable_gate_v1`. It evaluates named and parameterized policies after the
deterministic ranking is available, then selects the highest-coverage policy
that satisfies the safety constraints on labeled cases.

## Routing

`rank_near` remains a diagnostic field only.  It never authorizes a bypass.

```text
if all strict safety-certificate checks pass:
    accept combined Top-1 only
else:
    invoke_llm
```

Candidate policies vary Top-1 agreement, tree trust, temporal-data, margin, and
evidence-quorum requirements. Independent evidence votes are topology direction
support, direct high-weight alarm evidence, temporal multisignal support, and a
ranker score margin. Every successful bypass emits only the combined Top-1.
Missing required evidence fails closed and invokes the LLM.

Policy selection requires zero unsafe bypasses, no bypass of an optional known
bad-case list, and the configured error-recall target globally and in every
non-empty deterministic fold. It then maximizes bypass coverage. If no useful
candidate passes, `always_llm` is selected explicitly.

The former `trust_tree_v1` behavior is frozen in
`Sys/RootCauseAnalyze/gate_policies/baseline.py` for ablation only.

## Gate Safety Evaluation

The gate's positive class is a deterministic combined-ranking miss.  Error
recall measures how many such cases are routed away from bypass.  The hard
safety target is 100% error recall and zero unsafe bypasses:

```bash
python Sys/Score/evaluate_gate_recall.py \
  --res /path/to/skillpipe/res.json \
  --out-dir /path/to/output/gate_recall \
  --target-k 1 \
  --policy-config /path/to/selected_gate_policy.json \
  --assert-safe
```

The command exits with status 2 when the safety target is not met.

For automatic policy search and application, run:

```bash
PINGMESH_EXPERIMENTS="pipe gate_auto" ./scripts/run_rca_experiments.sh
```

The script first creates `pipe/res.json`, then writes the search report to
`gate_search/`, the selected gated result to `gate_selected/res.json`, and the
final recall assertion to `gate_recall/`. Set `PINGMESH_GATE_BADCASES` to a
JSON, JSONL, or CSV list of known false-positive cases when available.

## Server Evaluation

After pulling the branch on the server, first regenerate skillpipe results so
`skill_details` contains own Top-K rankings and trust-tree states:

```bash
python Sys/RootCauseAnalyze/skill_pipeline.py \
  --data-root /home/sbp/lixinyang/pingmesh/data/node/nodes_max_labeled \
  --skills 1 2 \
  --top-k 5 \
  --weight-file /home/sbp/lixinyang/pingmesh/data/weights/classified_alarms/all_alarms.json \
  --output-dir trust_tree_skillpipe_manual
```

Then evaluate the gate without calling the LLM:

```bash
python Sys/Score/evaluate_trust_gate.py \
  --res /home/sbp/lixinyang/pingmesh/data/res/trust_tree_skillpipe_manual/res.json \
  --out-dir /home/sbp/lixinyang/pingmesh/data/res/trust_tree_skillpipe_manual/trust_gate_eval
```

Expected outputs:

- `trust_gate_cases.jsonl`
- `trust_gate_summary.json`
- `trust_gate_by_route.csv`

For online gated inference:

```bash
export PINGMESH_GATE_POLICY_CONFIG=/path/to/selected_gate_policy.json
PINGMESH_ENABLE_GATE=1 ./scripts/run_rca_inference.sh trust_tree_gated_manual "1 2"
```
