"""M3's anchor-conditioned decoding: M1 evidence -> backbone -> augmented DAG.

These tests exercise the domain layer rather than the graph routine: how the
directional evidence turns into ``lift``, which structure the backbone picks,
what augmentation is allowed to add, and what the emitted graph rows must
contain for the downstream trust checks to keep working.

``_root_reachable`` in ``trust.py`` requires every node listed in ``nodes`` to be
reachable from the anchor, so a node the backbone does not claim must stay out
of ``nodes`` and be reported in diagnostics instead. Several tests below exist
only to pin that down.
"""
from __future__ import annotations

import math

import pytest

from Sys.RootCauseAnalyze.propagation.m2 import infer_root_paths
from Sys.RootCauseAnalyze.propagation.m3.decode import decode_backbone
from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig
from Sys.RootCauseAnalyze.propagation.solver import is_dag

PRIOR_LOGIT = -3.0


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def _pair(index, a, b, forward_lift, reverse_lift, *, prior_logit=PRIOR_LOGIT):
    """One M1 edge hypothesis, scored the way ``logit_evidence_v1`` scores it.

    ``forward_lift`` is the evidence gain over the prior, so the recorded logits
    are ``prior_logit + lift`` - exactly the shape ``directional_scores`` emits.
    """

    forward_logit = prior_logit + forward_lift
    reverse_logit = prior_logit + reverse_lift
    return {
        "edge_hypothesis_id": f"EH{index:05d}",
        "endpoint_a": a,
        "endpoint_b": b,
        "edge_type": "physical",
        "topology_edge_ids": [f"T{index}"],
        "state_probabilities": {
            "endpoint_a_to_b": _sigmoid(forward_logit),
            "endpoint_b_to_a": _sigmoid(reverse_logit),
            "no_direct_propagation": 0.0,
        },
        "probability_details": {
            "prior_logit": prior_logit,
            "a_to_b_logit": forward_logit,
            "b_to_a_logit": reverse_logit,
            "a_to_b_score": _sigmoid(forward_logit),
            "b_to_a_score": _sigmoid(reverse_logit),
            "a_to_b_contributions": [],
            "b_to_a_contributions": [],
            "evidence_ids": [f"E{index}"],
            "counter_evidence_ids": [],
        },
        "directions": [
            {
                "from": a,
                "to": b,
                "relation": "inferred_impact",
                "case_support_score": forward_lift,
                "lag_interval_ms": None,
                "features": {},
                "evidence_ids": [f"E{index}"],
                "counter_evidence_ids": [],
                "state_probability": _sigmoid(forward_logit),
            },
            {
                "from": b,
                "to": a,
                "relation": "inferred_impact",
                "case_support_score": reverse_lift,
                "lag_interval_ms": None,
                "features": {},
                "evidence_ids": [f"E{index}"],
                "counter_evidence_ids": [],
                "state_probability": _sigmoid(reverse_logit),
            },
        ],
    }


def _graph(pairs, node_ids, target_ids):
    return {
        "nodes": [{"device_id": node} for node in node_ids],
        "candidate_topology_edges": [
            {
                "endpoint_a": pair["endpoint_a"],
                "endpoint_b": pair["endpoint_b"],
                "edge_type": pair["edge_type"],
                "topology_edge_ids": list(pair["topology_edge_ids"]),
            }
            for pair in pairs
        ],
        "edge_hypotheses": pairs,
        "affected_targets": [
            {"device_id": node, "target_prize": 1.0} for node in target_ids
        ],
        "source_anchors": [],
        "sink_anchors": [],
        "evidence_map": {},
    }


def _root(device):
    return {
        "hypothesis_id": "R1",
        "root_scope": "device",
        "root_devices": [device],
        "root_link": None,
        "rank": 1,
        "support_score": 1.0,
        "decision_state": "ranked_candidate",
        "evidence_ids": [],
    }


def _config(**overrides):
    base = {
        "edge_probability_method": "logit_evidence_v1",
        "backbone_method": "maximum_evidence_arborescence_v1",
        # logit(0.10) - (-3.0) = 0.803, so a lift of 1.0 clears it.
        "augmentation_min_probability": 0.10,
    }
    base.update(overrides)
    return PropagationConfig(**base)


def _pairs(result):
    return {(edge["from"], edge["to"]) for edge in result["edges"]}


def _edge(result, source, target):
    for edge in result["edges"]:
        if edge["from"] == source and edge["to"] == target:
            return edge
    raise AssertionError(f"no edge {source}->{target} in {sorted(_pairs(result))}")


# --------------------------------------------------------------------------
# Backbone structure
# --------------------------------------------------------------------------


def test_backbone_prefers_the_stronger_shortcut_over_a_weak_chain():
    """``a->c`` scores 5.0 against ``a->b->c``'s 2.0 + 1.5, so the direct edge wins."""
    pairs = [
        _pair(1, "a", "b", 2.0, 0.1),
        _pair(2, "b", "c", 1.5, 0.3),
        _pair(3, "a", "c", 5.0, 0.1),
    ]
    result = decode_backbone(
        _graph(pairs, ["a", "b", "c"], ["c"]), _root("a"), [], config=_config()
    )

    assert _edge(result, "a", "b")["edge_origin"] == "backbone"
    assert _edge(result, "a", "c")["edge_origin"] == "backbone"
    # b->c is not needed for reachability, but it is strong evidence for a
    # second propagation path into c.
    assert _edge(result, "b", "c")["edge_origin"] == "augmented"
    assert result["covered_targets"] == ["c"]
    assert result["target_coverage"] == 1.0


def test_backbone_edge_carries_original_evidence_not_the_contracted_weight():
    """A cycle forces a contraction; the reported score must survive it.

    ``b->c->d->b`` is a cycle, so the solver contracts it and rewrites the
    entering edge's weight to ``2.0 - 4.0 = -2.0``. That reweighted value is a
    selection device, and emitting it as ``support_score`` would be wrong on
    every count - including sign.

    The cycle's selected incoming edges are ``d->b`` (4.0), ``b->c`` (5.0) and
    ``c->d`` (3.0); ``a->b`` replaces ``pi(b) = d->b``. Dropping the *lightest*
    cycle edge instead would remove ``c->d`` and leave a malformed structure.
    """
    pairs = [
        _pair(1, "a", "b", 2.0, 0.1),
        _pair(2, "b", "c", 5.0, 0.5),
        _pair(3, "c", "d", 3.0, 0.5),
        _pair(4, "d", "b", 4.0, 0.5),
    ]
    result = decode_backbone(
        _graph(pairs, ["a", "b", "c", "d"], ["d"]), _root("a"), [], config=_config()
    )

    assert _pairs(result) == {("a", "b"), ("b", "c"), ("c", "d")}
    assert ("d", "b") not in _pairs(result)
    assert result["diagnostics"]["cycle_contraction_count"] >= 1

    entering = _edge(result, "a", "b")
    assert entering["edge_origin"] == "backbone"
    assert entering["features"]["evidence_lift"] == pytest.approx(2.0)
    # Emitted scores are rounded to 6 decimals, hence the absolute tolerance.
    assert entering["support_score"] == pytest.approx(
        _sigmoid(PRIOR_LOGIT + 2.0), abs=1e-6
    )

    # b->c and c->d come out of the contraction, so their reported scores prove
    # the expansion restored the original evidence rather than the reduced one.
    assert _edge(result, "b", "c")["features"]["evidence_lift"] == pytest.approx(5.0)
    assert _edge(result, "c", "d")["features"]["evidence_lift"] == pytest.approx(3.0)
    assert _edge(result, "b", "c")["support_score"] == pytest.approx(
        _sigmoid(PRIOR_LOGIT + 5.0), abs=1e-6
    )


def test_backbone_rejects_a_direction_whose_lift_is_not_positive():
    """Negative evidence for b->a means b->a is never asserted."""
    pairs = [_pair(1, "a", "b", 2.0, -1.5)]
    result = decode_backbone(
        _graph(pairs, ["a", "b"], ["b"]), _root("a"), [], config=_config()
    )

    assert _pairs(result) == {("a", "b")}


# --------------------------------------------------------------------------
# Augmentation
# --------------------------------------------------------------------------


def test_augmentation_never_grows_from_an_unreached_component():
    """A strongly evidenced island the anchor cannot reach stays out.

    ``x<->y`` carries a huge lift, but neither end is reachable from the anchor.
    Accepting ``x->y`` on lift alone would smuggle a second component into a
    graph presented as anchor-conditioned.
    """
    pairs = [
        _pair(1, "a", "b", 2.0, 0.1),
        _pair(2, "x", "y", 50.0, 0.1),
        _pair(3, "y", "x", 40.0, 0.1),
    ]
    result = decode_backbone(
        _graph(pairs, ["a", "b", "x", "y"], ["b"]), _root("a"), [], config=_config()
    )

    assert _pairs(result) == {("a", "b")}
    assert {node["device_id"] for node in result["nodes"]} == {"a", "b"}
    assert result["diagnostics"]["unreached_nodes"] == ["x", "y"]


def test_augmentation_threshold_follows_each_pairs_prior():
    """The same lift clears the bar under one prior and misses it under another.

    The bar lives in probability space, so it converts per edge with
    ``logit(p) - prior_logit``. ``c->d`` (prior -3.0) has a bar of 0.803 and is
    added; ``c->e`` (prior -5.0) has a bar of 2.803 and is not, even though both
    carry the same lift of 1.0.
    """
    pairs = [
        _pair(1, "a", "b", 5.0, 0.1),
        _pair(2, "a", "c", 4.0, 0.1),
        _pair(3, "b", "d", 1.0, 0.1),
        _pair(4, "c", "d", 1.0, 0.1),
        _pair(5, "b", "e", 1.0, 0.1),
        _pair(6, "c", "e", 1.0, 0.1, prior_logit=-5.0),
    ]
    result = decode_backbone(
        _graph(pairs, ["a", "b", "c", "d", "e"], ["d", "e"]),
        _root("a"),
        [],
        config=_config(),
    )

    assert _edge(result, "c", "d")["edge_origin"] == "augmented"
    assert ("c", "e") not in _pairs(result)
    assert _edge(result, "b", "e")["edge_origin"] == "backbone"


def test_augmentation_can_be_switched_off_for_an_ablation():
    pairs = [
        _pair(1, "a", "b", 2.0, 0.1),
        _pair(2, "b", "c", 1.5, 0.3),
        _pair(3, "a", "c", 5.0, 0.1),
    ]
    result = decode_backbone(
        _graph(pairs, ["a", "b", "c"], ["c"]),
        _root("a"),
        [],
        config=_config(dag_augmentation=False),
    )

    assert _pairs(result) == {("a", "b"), ("a", "c")}
    assert result["diagnostics"]["augmented_edge_count"] == 0


# --------------------------------------------------------------------------
# Output contract
# --------------------------------------------------------------------------


def test_output_satisfies_the_downstream_trust_contract():
    pairs = [
        _pair(1, "a", "b", 2.0, 0.1),
        _pair(2, "b", "c", 5.0, 0.5),
        _pair(3, "c", "d", 3.0, 0.5),
        _pair(4, "d", "b", 4.0, 0.5),
    ]
    result = decode_backbone(
        _graph(pairs, ["a", "b", "c", "d"], ["d"]), _root("a"), [], config=_config()
    )

    assert is_dag(result["edges"])
    assert all(
        float(edge["features"]["topology_valid"]) >= 1.0 for edge in result["edges"]
    )
    assert all(edge["support_level"] in {"strong", "moderate", "weak"} for edge in result["edges"])
    assert not any(edge.get("alternative_group") for edge in result["edges"])

    # Every listed node must be reachable from the anchor (trust._root_reachable).
    reached = {"a"}
    for _ in range(len(result["nodes"])):
        for edge in result["edges"]:
            if edge["from"] in reached:
                reached.add(edge["to"])
    assert {node["device_id"] for node in result["nodes"]} <= reached
    assert result["root_hypothesis"]["root_devices"] == ["a"]


def test_every_edge_records_the_pair_it_was_decoded_from():
    pairs = [_pair(1, "a", "b", 2.0, 0.1), _pair(2, "a", "c", 3.0, 0.1)]
    result = decode_backbone(
        _graph(pairs, ["a", "b", "c"], ["b"]), _root("a"), [], config=_config()
    )

    assert all(edge["edge_hypothesis_id"] for edge in result["edges"])
    assert all(edge["topology_edge_ids"] for edge in result["edges"])
    assert all(edge["edge_id"] for edge in result["edges"])


# --------------------------------------------------------------------------
# Configuration guards
# --------------------------------------------------------------------------


def test_arborescence_backbone_requires_additive_evidence():
    """Simplex probabilities cannot drive a max-sum objective, so refuse them."""
    pairs = [_pair(1, "a", "b", 2.0, 0.1)]
    with pytest.raises(ValueError, match="logit"):
        decode_backbone(
            _graph(pairs, ["a", "b"], ["b"]),
            _root("a"),
            [],
            config=_config(edge_probability_method="deterministic_evidence_v1"),
        )


def test_m2_routes_to_the_arborescence_backbone_when_configured():
    """``backbone_method`` selects the solver inside the per-anchor M2 loop."""
    graph = _graph(
        [_pair(1, "a", "b", 2.0, 0.1), _pair(2, "a", "c", 5.0, 0.1)],
        ["a", "b", "c"],
        ["c"],
    )
    result = infer_root_paths(
        hypothesis_graph=graph, initial_root_rankings=["a"], config=_config()
    )

    selected = result["selected_propagation_graph"]
    assert selected["diagnostics"]["backbone_method"] == "maximum_evidence_arborescence_v1"
    assert {(edge["from"], edge["to"]) for edge in selected["edges"]} == {
        ("a", "b"),
        ("a", "c"),
    }
    assert result["selected_root"] == "a"


def test_m2_keeps_the_beam_search_solver_as_the_default():
    """The pre-existing solver stays reachable so it can serve as an ablation."""
    graph = _graph(
        [_pair(1, "a", "b", 2.0, 0.1), _pair(2, "a", "c", 5.0, 0.1)],
        ["a", "b", "c"],
        ["c"],
    )
    result = infer_root_paths(
        hypothesis_graph=graph,
        initial_root_rankings=["a"],
        config=PropagationConfig(edge_probability_method="logit_evidence_v1"),
    )

    selected = result["selected_propagation_graph"]
    assert "backbone_method" not in selected["diagnostics"]
    assert selected["edges"]


def test_edge_hypotheses_without_a_validated_topology_edge_are_ignored():
    """A pair whose topology ids do not line up is not a candidate relation."""
    pairs = [_pair(1, "a", "b", 2.0, 0.1), _pair(2, "a", "c", 9.0, 0.1)]
    graph = _graph(pairs, ["a", "b", "c"], ["c"])
    graph["candidate_topology_edges"][1]["topology_edge_ids"] = ["SOMETHING_ELSE"]

    result = decode_backbone(graph, _root("a"), [], config=_config())

    assert ("a", "c") not in _pairs(result)
    assert _pairs(result) == {("a", "b")}
