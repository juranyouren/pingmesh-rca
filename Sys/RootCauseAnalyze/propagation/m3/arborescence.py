"""``arborescence``: maximum-weight arborescence with a virtual-root null option.

This module is a graph routine. It knows nodes, weighted directed edges and a
root - it knows nothing about devices, evidence, anchors or incidents.

Two entry points:

``maximum_arborescence``
    Chu-Liu/Edmonds maximum-weight arborescence rooted at a given node. Every
    other node takes exactly one incoming edge. Infeasible when some node
    cannot be reached from the root.

``maximum_arborescence_with_null_option``
    The reduction this project uses: attach a virtual root that offers every
    node a *null* alternative - "this node is not claimed by anyone". A node is
    taken into the root's arborescence only when a real edge beats the null
    weight; everything else stays unreached instead of acquiring an edge that
    the evidence never supported.

Three properties this module guarantees, because downstream stages depend on
them:

* **Structural selection only.** The weights here choose a structure. They are
  not scores to be reported back. Contraction rewrites them into quantities
  that are no longer evidence, so the caller must re-attach the original
  evidence to whatever structure comes out.
* **Provenance-correct expansion.** When a contracted cycle is entered by an
  external edge ``u -> v*``, the cycle edge that must be dropped is ``pi(v*)``
  - the one the entering edge replaced - and *not* the lightest edge of the
  cycle. Each contracted edge therefore carries the base edges it stands for.
* **Determinism.** Ties break on ``(source, target)`` and cycles are found by
  scanning nodes in sorted order, so the same input always yields the same
  output.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple

#: Node name reserved for the virtual root. Callers must not use it.
VIRTUAL_ROOT = "__virtual_root__"


@dataclass(frozen=True)
class WeightedEdge:
    """One directed candidate edge, in whichever graph space it currently lives."""

    source: str
    target: str
    weight: float


@dataclass(frozen=True)
class ArborescenceForest:
    """The chosen structure plus the numbers needed to reason about it.

    ``edges`` is the root's arborescence, expressed in the *base* graph and
    carrying the original weights. ``unreached`` lists the nodes the root's
    arborescence does not contain.

    ``objective`` is what the optimiser maximised, spanning the whole
    virtual-root forest - including edges of components the root cannot reach -
    so it is not the same number as ``arborescence_weight``. It deliberately
    leaves out the forced ``virtual_root -> root`` edge, whose magnitude is an
    implementation detail rather than a quantity about the incident.
    """

    edges: Tuple[WeightedEdge, ...]
    unreached: Tuple[str, ...]
    arborescence_weight: float
    objective: float
    contraction_count: int


@dataclass(frozen=True)
class _Edge:
    """An edge in the current graph space, plus the base edges it stands for.

    ``payload`` is the reason this design needs no separate expansion pass: an
    edge created by contracting a cycle already carries the *base* edges that
    selecting it implies, so flattening the payloads of the final solution
    yields the arborescence directly.
    """

    source: str
    target: str
    weight: float
    payload: Tuple[WeightedEdge, ...]


def _precedes(candidate: _Edge, current: _Edge) -> bool:
    """Deterministic "is ``candidate`` the better incoming edge" test."""

    if candidate.weight != current.weight:
        return candidate.weight > current.weight
    return (candidate.source, candidate.target) < (current.source, current.target)


def _find_cycle(
    nodes: Sequence[str],
    incoming: Mapping[str, _Edge],
    root: str,
) -> List[str] | None:
    """Return one cycle of the parent graph, or ``None``.

    Every node but the root has exactly one parent, so following parents either
    reaches the root or revisits a node. Scanning starts in sorted order so the
    cycle that is found - and therefore the contraction order - is deterministic.
    """

    finished: set[str] = set()
    for start in sorted(nodes):
        if start == root or start in finished:
            continue
        path: List[str] = []
        position: Dict[str, int] = {}
        node: str | None = start
        while node is not None and node != root and node not in finished:
            if node in position:
                return path[position[node]:]
            position[node] = len(path)
            path.append(node)
            edge = incoming.get(node)
            node = edge.source if edge is not None else None
        finished.update(path)
    return None


def _contract(
    nodes: Sequence[str],
    edges: Sequence[_Edge],
    cycle: Sequence[str],
    incoming: Mapping[str, _Edge],
    merged: str,
) -> Tuple[List[str], List[_Edge]]:
    """Contract ``cycle`` into ``merged`` and rebuild the edge list around it."""

    members = set(cycle)
    contracted: List[_Edge] = []
    for edge in edges:
        source_inside = edge.source in members
        target_inside = edge.target in members
        if source_inside and target_inside:
            # Internal to the cycle: unselectable, and reconstructed from
            # ``incoming`` by whichever entering edge wins.
            continue
        if target_inside:
            # Entering edge. It stands for itself plus every cycle edge except
            # the one it replaces - pi(target) - which is exactly the edge that
            # must disappear when this cycle is expanded.
            replaced = incoming[edge.target]
            payload = edge.payload + tuple(
                item
                for member in cycle
                if member != edge.target
                for item in incoming[member].payload
            )
            contracted.append(
                _Edge(edge.source, merged, edge.weight - replaced.weight, payload)
            )
        elif source_inside:
            contracted.append(_Edge(merged, edge.target, edge.weight, edge.payload))
        else:
            contracted.append(edge)
    return [node for node in nodes if node not in members] + [merged], contracted


def _solve(
    nodes: Sequence[str],
    edges: Sequence[_Edge],
    root: str,
    counter: List[int],
) -> List[_Edge]:
    """Chu-Liu/Edmonds, returning edges whose payloads are already base edges."""

    incoming: Dict[str, _Edge] = {}
    for edge in edges:
        if edge.target == root:
            continue
        current = incoming.get(edge.target)
        if current is None or _precedes(edge, current):
            incoming[edge.target] = edge

    unreachable = sorted(node for node in nodes if node != root and node not in incoming)
    if unreachable:
        raise ValueError(
            f"no arborescence rooted at {root!r}: unreachable nodes {unreachable}"
        )

    cycle = _find_cycle(nodes, incoming, root)
    if cycle is None:
        return list(incoming.values())

    merged = f"{VIRTUAL_ROOT}cycle{counter[0]}"
    counter[0] += 1
    contracted_nodes, contracted_edges = _contract(nodes, edges, cycle, incoming, merged)
    return _solve(contracted_nodes, contracted_edges, root, counter)


def _as_edges(edges: Sequence[WeightedEdge]) -> List[_Edge]:
    return [
        _Edge(edge.source, edge.target, edge.weight, (edge,))
        for edge in edges
        if edge.source != edge.target
    ]


def maximum_arborescence(
    nodes: Sequence[str],
    edges: Sequence[WeightedEdge],
    root: str,
) -> ArborescenceForest:
    """Maximum-weight arborescence rooted at ``root``, spanning every node.

    Raises ``ValueError`` when no such arborescence exists, which happens as
    soon as one node is unreachable from ``root``.
    """

    unique_nodes = sorted(set(nodes))
    if root not in set(unique_nodes):
        raise ValueError(f"root {root!r} is not one of the nodes")

    contractions = [0]
    picked = _solve(unique_nodes, _as_edges(edges), root, contractions)
    selected = sorted(
        (edge for item in picked for edge in item.payload),
        key=lambda edge: (edge.source, edge.target, edge.weight),
    )
    total = math.fsum(edge.weight for edge in selected)
    return ArborescenceForest(
        edges=tuple(selected),
        unreached=(),
        arborescence_weight=total,
        objective=total,
        contraction_count=contractions[0],
    )


def maximum_arborescence_with_null_option(
    nodes: Sequence[str],
    edges: Sequence[WeightedEdge],
    root: str,
    *,
    null_weight: float = 0.0,
) -> ArborescenceForest:
    """Maximum-evidence backbone rooted at ``root``, with a null option per node.

    ``null_weight`` is what a node is deemed worth when nothing claims it. A
    real edge is eligible only when it *strictly* beats that value, so the
    default of ``0.0`` reads as "net positive evidence required to assert a
    relation", and a tie leaves the node unreached rather than asserting a
    zero-evidence edge.

    The returned ``edges`` hold the original weights, never the reweighted ones
    produced while contracting a cycle.
    """

    if null_weight < 0.0:
        raise ValueError("null_weight must be non-negative")

    unique_nodes = sorted(set(nodes))
    if not unique_nodes:
        raise ValueError("at least one node is required")
    if root not in set(unique_nodes):
        raise ValueError(f"root {root!r} is not one of the nodes")
    if VIRTUAL_ROOT in set(unique_nodes):
        raise ValueError(f"node name {VIRTUAL_ROOT!r} is reserved")

    eligible = [
        edge
        for edge in edges
        if edge.weight > null_weight
        and edge.source != edge.target
        and VIRTUAL_ROOT not in (edge.source, edge.target)
    ]

    # Dominates every alternative, so the root can never acquire a real parent.
    big = 1.0 + math.fsum(abs(edge.weight) for edge in eligible) + null_weight * len(
        unique_nodes
    )

    virtual = [
        _Edge(
            VIRTUAL_ROOT,
            root,
            big,
            (WeightedEdge(VIRTUAL_ROOT, root, big),),
        )
    ]
    for node in unique_nodes:
        if node == root:
            continue
        virtual.append(
            _Edge(
                VIRTUAL_ROOT,
                node,
                null_weight,
                (WeightedEdge(VIRTUAL_ROOT, node, null_weight),),
            )
        )

    contractions = [0]
    picked = _solve(
        [VIRTUAL_ROOT, *unique_nodes],
        [*virtual, *_as_edges(eligible)],
        VIRTUAL_ROOT,
        contractions,
    )
    selected = [edge for item in picked for edge in item.payload]
    objective = math.fsum(
        edge.weight
        for edge in selected
        if not (edge.source == VIRTUAL_ROOT and edge.target == root)
    )

    children: Dict[str, List[str]] = defaultdict(list)
    for edge in selected:
        if edge.source != VIRTUAL_ROOT:
            children[edge.source].append(edge.target)

    reached = {root}
    stack = [root]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in reached:
                reached.add(child)
                stack.append(child)

    backbone = sorted(
        (
            edge
            for edge in selected
            if edge.source != VIRTUAL_ROOT
            and edge.source in reached
            and edge.target in reached
        ),
        key=lambda edge: (edge.source, edge.target, edge.weight),
    )
    return ArborescenceForest(
        edges=tuple(backbone),
        unreached=tuple(sorted(set(unique_nodes) - reached)),
        arborescence_weight=math.fsum(edge.weight for edge in backbone),
        objective=objective,
        contraction_count=contractions[0],
    )
