# Trust-Tree Gate Design

## Goal

The gate decides when deterministic RCA can be trusted, when LLM arbitration is
needed, and when the case should be sent to operators. It uses two logical trust
trees instead of a continuous confidence score:

- `topo_trust_tree`: topology/PageRank evidence.
- `temporal_trust_tree`: temporal burst/early/density evidence.

Each tree returns `strong`, `weak`, or `uncertain`.

## Routing

`rank_near` is true when topo and temporal Top-1 match, or their Top-3 overlap
has at least two devices.

```text
if topo == weak and temporal == weak:
    operator_review
elif rank_near:
    accept_combined
elif topo == strong and temporal != strong:
    accept_topo
elif temporal == strong and topo != strong:
    accept_temporal
elif topo == strong and temporal == strong:
    invoke_llm
else:
    invoke_llm
```

`operator_review` returns an empty `response.ip` list so automatic scoring does
not count it as an automated diagnosis.

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
