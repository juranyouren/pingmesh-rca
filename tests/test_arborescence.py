"""M3's structural solver: Chu-Liu/Edmonds with a virtual-root null option.

The solver is a pure graph routine. It knows nodes, weighted directed edges and
a root - nothing about devices, evidence or anchors. These tests pin down the
two places where a Chu-Liu/Edmonds implementation is easy to get wrong:

* **cycle expansion** must delete ``pi(v*)`` - the cycle edge that the entering
  edge replaced - and not the lightest edge of the cycle;
* **the null option** must leave an unsupported node unattached instead of
  inventing an edge for it.

Nested contraction is not hand-verifiable, so it is covered by the networkx
oracle at the bottom of this file rather than by a crafted example. The oracle
lives in the tests only: the propagation package itself stays free of
third-party imports.
"""
from __future__ import annotations

import random
from collections import defaultdict

import pytest

from Sys.RootCauseAnalyze.propagation.m3.arborescence import (
    WeightedEdge,
    maximum_arborescence,
    maximum_arborescence_with_null_option,
)


def _pairs(result) -> set:
    return {(edge.source, edge.target) for edge in result.edges}


def _assert_valid_arborescence(result, root: str, all_nodes) -> None:
    """Every reached node has exactly one parent, the root has none, and no cycle."""
    parents = {}
    children = defaultdict(set)
    for edge in result.edges:
        assert edge.target not in parents, f"{edge.target} has two parents"
        parents[edge.target] = edge.source
        children[edge.source].add(edge.target)

    assert root not in parents, "the root must not take an incoming edge"

    reached = {root}
    queue = [root]
    while queue:
        node = queue.pop()
        for child in children[node]:
            assert child not in reached, "cycle detected"
            reached.add(child)
            queue.append(child)

    assert reached == {root} | set(parents)
    assert reached.isdisjoint(result.unreached)
    assert reached | set(result.unreached) == set(all_nodes)


# --------------------------------------------------------------------------
# Cycle contraction and expansion
# --------------------------------------------------------------------------


def test_cycle_expansion_drops_the_replaced_incoming_edge():
    """The heaviest cycle edge is deleted when an entering edge replaces it.

    ``B->C->D->B`` is the only cycle and both ``A->B`` and ``A->C`` enter it,
    so the choice inside the contracted node decides the answer:

    * ``A->B`` replaces ``pi(B) = D->B``, giving 6 + 10 + 9 = 25;
    * ``A->C`` replaces ``pi(C) = B->C``, giving 5 + 9 + 8 = 22.

    Expanding by deleting the *lightest* cycle edge would leave ``C`` with two
    parents and ``B`` with none - not an arborescence at all.
    """
    result = maximum_arborescence(
        ["A", "B", "C", "D"],
        [
            WeightedEdge("A", "B", 6.0),
            WeightedEdge("A", "C", 5.0),
            WeightedEdge("B", "C", 10.0),
            WeightedEdge("C", "D", 9.0),
            WeightedEdge("D", "B", 8.0),
        ],
        "A",
    )

    assert _pairs(result) == {("A", "B"), ("B", "C"), ("C", "D")}
    assert result.arborescence_weight == 25.0
    assert result.contraction_count == 1
    _assert_valid_arborescence(result, "A", ["A", "B", "C", "D"])


def test_two_cycle_is_resolved_by_its_external_entering_edge():
    """``B<->C`` is broken by ``A->B``; the cycle edge into B is the one dropped."""
    result = maximum_arborescence(
        ["A", "B", "C"],
        [
            WeightedEdge("A", "B", 4.0),
            WeightedEdge("B", "C", 5.0),
            WeightedEdge("C", "B", 4.5),
        ],
        "A",
    )

    assert _pairs(result) == {("A", "B"), ("B", "C")}
    assert result.arborescence_weight == 9.0
    assert result.contraction_count == 1
    _assert_valid_arborescence(result, "A", ["A", "B", "C"])


def test_root_is_forced_to_have_no_parent():
    """The root never takes an incoming edge, however tempting that edge is."""
    result = maximum_arborescence(
        ["A", "B"],
        [WeightedEdge("A", "B", 1.0), WeightedEdge("B", "A", 99.0)],
        "A",
    )

    assert _pairs(result) == {("A", "B")}


def test_unreachable_node_is_infeasible_without_a_null_option():
    """``C`` has no incoming edge at all, so no arborescence rooted at ``A`` exists."""
    with pytest.raises(ValueError):
        maximum_arborescence(["A", "B", "C"], [WeightedEdge("A", "B", 1.0)], "A")


# --------------------------------------------------------------------------
# The virtual-root null option
# --------------------------------------------------------------------------


def test_null_option_leaves_a_node_without_support_unreached():
    result = maximum_arborescence_with_null_option(
        ["a", "b", "c"],
        [WeightedEdge("a", "b", 3.0)],
        "a",
    )

    assert _pairs(result) == {("a", "b")}
    assert result.unreached == ("c",)
    assert result.arborescence_weight == 3.0


def test_null_option_rejects_a_negative_weight_edge():
    """A node whose only incoming evidence is negative is not claimed."""
    result = maximum_arborescence_with_null_option(
        ["a", "b"],
        [WeightedEdge("a", "b", -0.5)],
        "a",
    )

    assert result.edges == ()
    assert result.unreached == ("b",)


def test_null_option_wins_a_tie_rather_than_asserting_a_zero_weight_edge():
    """Exactly-null evidence is missing evidence, not a confirmed relation."""
    result = maximum_arborescence_with_null_option(
        ["a", "b"],
        [WeightedEdge("a", "b", 0.0)],
        "a",
    )

    assert result.edges == ()
    assert result.unreached == ("b",)


def test_null_option_raises_the_bar_for_attachment():
    """Raising the null weight drops edges that would otherwise be kept."""
    edges = [WeightedEdge("a", "b", 1.0)]

    assert _pairs(maximum_arborescence_with_null_option(["a", "b"], edges, "a")) == {
        ("a", "b")
    }

    strict = maximum_arborescence_with_null_option(["a", "b"], edges, "a", null_weight=2.0)
    assert strict.edges == ()
    assert strict.unreached == ("b",)


def test_null_option_requires_a_non_negative_null_weight():
    with pytest.raises(ValueError):
        maximum_arborescence_with_null_option(
            ["a", "b"], [WeightedEdge("a", "b", 1.0)], "a", null_weight=-1.0
        )


def test_null_option_keeps_a_node_reachable_through_a_weak_edge_chain():
    """A cheap first hop is kept when it is the only way to a strong second hop."""
    result = maximum_arborescence_with_null_option(
        ["a", "b", "c"],
        [WeightedEdge("a", "b", 0.1), WeightedEdge("b", "c", 9.0)],
        "a",
    )

    assert _pairs(result) == {("a", "b"), ("b", "c")}
    assert result.arborescence_weight == pytest.approx(9.1)


def test_null_option_is_deterministic_under_ties():
    ties = [WeightedEdge("a", "c", 1.0), WeightedEdge("b", "c", 1.0)]

    forward = maximum_arborescence_with_null_option(["a", "b", "c"], ties, "a")
    reversed_ = maximum_arborescence_with_null_option(
        ["a", "b", "c"], list(reversed(ties)), "a"
    )

    assert forward.edges == reversed_.edges
    assert _pairs(forward) == {("a", "c")}


def test_null_option_ignores_a_component_the_root_cannot_reach():
    """A strongly evidenced island does not leak into the root's arborescence."""
    result = maximum_arborescence_with_null_option(
        ["a", "b", "x", "y"],
        [
            WeightedEdge("a", "b", 2.0),
            WeightedEdge("x", "y", 50.0),
            WeightedEdge("y", "x", 40.0),
        ],
        "a",
    )

    assert _pairs(result) == {("a", "b")}
    assert result.unreached == ("x", "y")


# --------------------------------------------------------------------------
# Oracle: the objective must match networkx's maximum branching
# --------------------------------------------------------------------------


def test_objective_matches_networkx_on_random_graphs():
    """Cross-check the optimiser itself, not merely its edge set.

    Ties admit several optimal edge sets, so compare the objective. The graph
    handed to networkx is the same virtual-root construction the wrapper builds,
    which also exercises nested contraction on the random nested cycles.
    """

    nx = pytest.importorskip("networkx")
    from networkx.algorithms.tree.branchings import maximum_branching

    rng = random.Random(20260922)
    big = 1e6

    for _ in range(300):
        size = rng.randint(2, 7)
        nodes = [f"n{index}" for index in range(size)]
        edges = [
            WeightedEdge(source, target, round(rng.uniform(-3.0, 6.0), 3))
            for source in nodes
            for target in nodes
            if source != target and rng.random() < 0.5
        ]
        null_weight = round(rng.choice([0.0, 0.5, 1.5]), 3)

        graph = nx.DiGraph()
        graph.add_edge("r0", nodes[0], weight=big)
        for node in nodes[1:]:
            graph.add_edge("r0", node, weight=null_weight)
        for edge in edges:
            if edge.weight > null_weight:
                graph.add_edge(edge.source, edge.target, weight=edge.weight)

        # ``objective`` excludes the forced virtual-root edge, whose magnitude
        # is an implementation detail, so drop networkx's copy of it too.
        expected = -big + sum(
            data["weight"]
            for _, _, data in maximum_branching(graph, "weight").edges(data=True)
        )
        actual = maximum_arborescence_with_null_option(
            nodes,
            edges,
            nodes[0],
            null_weight=null_weight,
        )

        assert actual.objective == pytest.approx(expected, abs=1e-6), (
            f"nodes={nodes} edges={edges} null={null_weight}"
        )
        _assert_valid_arborescence(actual, nodes[0], nodes)
