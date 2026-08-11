# Trust-Tree Gate Design

## Goal

The gate decides when deterministic RCA can be trusted, when LLM arbitration is
needed, and when the case should be sent to operators. It uses two logical trust
trees instead of a continuous confidence score:

- `topo_trust_tree`: topology/PageRank evidence.
- `temporal_trust_tree`: temporal burst/early/density evidence.

Each tree returns `strong`, `weak`, or `uncertain`.  The active router is
`strict_fail_closed_v2`: tree strength is necessary but not sufficient for a
bypass.

## Routing

`rank_near` remains a diagnostic field only.  It never authorizes a bypass.

```text
if all strict safety-certificate checks pass:
    accept combined Top-1 only
else:
    invoke_llm
```

The safety certificate requires complete rankings; exact Top-1 unanimity across
topo, temporal, and combined rankings; both trees strong; directed/undirected
topology Top-1 unanimity; direct high-weight alarm evidence; burst/early Top-1
unanimity; usable temporal data; and calibrated score margins.  Missing evidence
fails closed and invokes the LLM.  A successful bypass emits one IP, not Top-3.

The former `trust_tree_v1` behavior is frozen in
`Sys/RootCauseAnalyze/gate_policies/baseline.py` for ablation only.

## Gate Safety Evaluation

The gate's positive class is a deterministic combined-ranking miss.  Error
recall measures how many such cases are routed away from bypass.  The hard
safety target is 100% error recall and zero unsafe bypasses:

```bash
bash scripts/run_gate_recall_test.sh \
  /path/to/skillpipe/res.json \
  /path/to/output/gate_recall \
  1
```

The command exits with status 2 when the safety target is not met.

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
PINGMESH_CONFIDENCE_GATE=1 ./scripts/run_inference.sh trust_tree_gated_manual "1 2"
```
