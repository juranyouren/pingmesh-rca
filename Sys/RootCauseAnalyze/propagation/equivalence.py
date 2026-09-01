from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Dict, Iterable, Mapping, Sequence, Set, Tuple


EQUIVALENCE_SCHEMA_VERSION = "topology-structural-equivalence-v1"
VIRTUAL_NODE_PREFIX = "VIRTUAL-PARALLEL"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_virtual_id(members: Sequence[str]) -> str:
    payload = "\x1f".join(sorted(members)).encode("utf-8")
    digest = hashlib.sha1(payload).hexdigest()[:12]
    return f"{VIRTUAL_NODE_PREFIX}-{digest}"


def _node_index(topology_context: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        _text(item.get("device_id")): dict(item)
        for item in topology_context.get("nodes", [])
        if isinstance(item, Mapping) and _text(item.get("device_id"))
    }


def _edge_rows(topology_context: Mapping[str, Any]) -> list[Dict[str, Any]]:
    return [
        dict(item)
        for item in topology_context.get("edges", [])
        if isinstance(item, Mapping)
        and _text(item.get("endpoint_a"))
        and _text(item.get("endpoint_b"))
        and _text(item.get("endpoint_a")) != _text(item.get("endpoint_b"))
    ]


def _neighborhoods(
    topology_context: Mapping[str, Any],
) -> tuple[Dict[str, Set[str]], Dict[str, Set[str]], Dict[str, Set[str]], Set[str]]:
    """Return upstream, downstream, undirected neighborhoods and oriented nodes."""

    node_ids = set(_node_index(topology_context))
    upstream: Dict[str, Set[str]] = {device_id: set() for device_id in node_ids}
    downstream: Dict[str, Set[str]] = {device_id: set() for device_id in node_ids}
    undirected: Dict[str, Set[str]] = {device_id: set() for device_id in node_ids}
    oriented_incident: Dict[str, int] = defaultdict(int)
    incident: Dict[str, int] = defaultdict(int)

    for edge in _edge_rows(topology_context):
        endpoint_a = _text(edge.get("endpoint_a"))
        endpoint_b = _text(edge.get("endpoint_b"))
        if endpoint_a not in node_ids or endpoint_b not in node_ids:
            continue
        undirected[endpoint_a].add(endpoint_b)
        undirected[endpoint_b].add(endpoint_a)
        incident[endpoint_a] += 1
        incident[endpoint_b] += 1
        valid_orientations: Set[Tuple[str, str]] = set()
        for raw in edge.get("raw_orientations", []):
            if not isinstance(raw, Mapping):
                continue
            source = _text(raw.get("src"))
            target = _text(raw.get("dst"))
            if {source, target} == {endpoint_a, endpoint_b} and source != target:
                valid_orientations.add((source, target))
        if not valid_orientations:
            continue
        for source, target in valid_orientations:
            downstream[source].add(target)
            upstream[target].add(source)
        oriented_incident[endpoint_a] += 1
        oriented_incident[endpoint_b] += 1

    fully_oriented = {
        device_id
        for device_id in node_ids
        if incident.get(device_id, 0) > 0
        and oriented_incident.get(device_id, 0) == incident.get(device_id, 0)
    }
    return upstream, downstream, undirected, fully_oriented


def _failure_domain_signature(node: Mapping[str, Any]) -> tuple[str, ...]:
    fields = (
        "az",
        "availability_zone",
        "region",
        "plane",
        "fabric_plane",
        "fault_domain",
        "cluster",
    )
    return tuple(_text(node.get(field)).lower() for field in fields)


def _structural_signature(
    device_id: str,
    node: Mapping[str, Any],
    *,
    upstream: Mapping[str, Set[str]],
    downstream: Mapping[str, Set[str]],
    undirected: Mapping[str, Set[str]],
    fully_oriented: Set[str],
) -> tuple[Any, ...] | None:
    role = _text(node.get("role", node.get("topology_role"))).lower()
    pod_number = node.get("pod_number")
    group_ids = tuple(sorted(_text(item) for item in node.get("group_ids", []) if _text(item)))
    common = (role, pod_number, group_ids, _failure_domain_signature(node))
    if device_id in fully_oriented:
        parents = tuple(sorted(upstream.get(device_id, set())))
        children = tuple(sorted(downstream.get(device_id, set())))
        # Only internal path nodes are eligible. Leaves and one-sided nodes are
        # preserved even if their local signatures happen to match.
        if not parents or not children:
            return None
        return ("directed", common, parents, children)
    neighbors = tuple(sorted(undirected.get(device_id, set())))
    if len(neighbors) < 2:
        return None
    return ("undirected", common, neighbors)


def build_structural_equivalence(
    topology_context: Mapping[str, Any],
    evidence_episodes: Sequence[Mapping[str, Any]] = (),
    *,
    protected_device_ids: Iterable[str] = (),
) -> Dict[str, Any]:
    """Build a label-free quotient mapping for evidence-free structural twins.

    A cluster is formed only when at least two internal devices have identical
    topology role/failure-domain metadata and identical immediate upstream and
    downstream sets. When trustworthy raw link orientations are unavailable,
    exact undirected-neighbor equality is used instead. Incident labels are
    deliberately not accepted by this function.
    """

    nodes = _node_index(topology_context)
    edges = _edge_rows(topology_context)
    upstream, downstream, undirected, fully_oriented = _neighborhoods(topology_context)
    evidence_devices = {
        _text(item.get("device_id"))
        for item in evidence_episodes
        if isinstance(item, Mapping) and _text(item.get("device_id"))
    }
    protected = {
        _text(item)
        for item in protected_device_ids
        if _text(item)
    }
    # A raw endpoint may itself be a topology device. In that case some legacy
    # contexts also list its immediate neighbors as anchors; protecting every
    # such neighbor would incorrectly suppress parallel-node aggregation.
    # Prefer direct endpoint devices and use derived anchors only for external
    # endpoints that are absent from the device graph.
    for endpoint_key, anchor_key in (
        ("source_endpoints", "source_anchors"),
        ("sink_endpoints", "sink_anchors"),
    ):
        direct = {
            _text(item)
            for item in topology_context.get(endpoint_key, [])
            if _text(item) in nodes
        }
        protected.update(
            direct
            or {
                _text(item)
                for item in topology_context.get(anchor_key, [])
                if _text(item)
            }
        )
    protected.update(evidence_devices)

    buckets: Dict[tuple[Any, ...], list[str]] = defaultdict(list)
    for device_id, node in nodes.items():
        if device_id in protected:
            continue
        signature = _structural_signature(
            device_id,
            node,
            upstream=upstream,
            downstream=downstream,
            undirected=undirected,
            fully_oriented=fully_oriented,
        )
        if signature is not None:
            buckets[signature].append(device_id)

    mapping = {device_id: device_id for device_id in nodes}
    clusters: list[Dict[str, Any]] = []
    for signature, raw_members in sorted(
        buckets.items(), key=lambda item: tuple(sorted(item[1]))
    ):
        members = sorted(set(raw_members))
        if len(members) < 2:
            continue
        virtual_id = _stable_virtual_id(members)
        for member in members:
            mapping[member] = virtual_id
        incident_edges = [
            edge
            for edge in edges
            if _text(edge.get("endpoint_a")) in members
            or _text(edge.get("endpoint_b")) in members
        ]
        clusters.append(
            {
                "virtual_node_id": virtual_id,
                "members": members,
                "mode": signature[0],
                "role": _text(nodes[members[0]].get("role", nodes[members[0]].get("topology_role"))),
                "pod_number": nodes[members[0]].get("pod_number"),
                "upstream": sorted(upstream.get(members[0], set())),
                "downstream": sorted(downstream.get(members[0], set())),
                "neighbors": sorted(undirected.get(members[0], set())),
                "supporting_raw_edges": [
                    {
                        "edge_id": _text(edge.get("edge_id")),
                        "endpoint_a": _text(edge.get("endpoint_a")),
                        "endpoint_b": _text(edge.get("endpoint_b")),
                    }
                    for edge in sorted(incident_edges, key=lambda item: _text(item.get("edge_id")))
                ],
            }
        )

    virtual_edge_buckets: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for edge in edges:
        raw_a = _text(edge.get("endpoint_a"))
        raw_b = _text(edge.get("endpoint_b"))
        endpoint_a = mapping.get(raw_a, raw_a)
        endpoint_b = mapping.get(raw_b, raw_b)
        if not endpoint_a or not endpoint_b or endpoint_a == endpoint_b:
            continue
        pair = tuple(sorted((endpoint_a, endpoint_b)))
        bucket = virtual_edge_buckets.setdefault(
            pair,
            {
                "endpoint_a": pair[0],
                "endpoint_b": pair[1],
                "supporting_raw_edge_ids": [],
                "supporting_raw_pairs": [],
            },
        )
        edge_id = _text(edge.get("edge_id"))
        if edge_id and edge_id not in bucket["supporting_raw_edge_ids"]:
            bucket["supporting_raw_edge_ids"].append(edge_id)
        raw_pair = [raw_a, raw_b]
        if raw_pair not in bucket["supporting_raw_pairs"]:
            bucket["supporting_raw_pairs"].append(raw_pair)

    return {
        "schema_version": EQUIVALENCE_SCHEMA_VERSION,
        "node_mapping": dict(sorted(mapping.items())),
        "clusters": clusters,
        "virtual_edges": [virtual_edge_buckets[key] for key in sorted(virtual_edge_buckets)],
        "diagnostics": {
            "raw_node_count": len(nodes),
            "raw_edge_count": len(edges),
            "protected_node_count": len(protected & set(nodes)),
            "evidence_device_count": len(evidence_devices & set(nodes)),
            "cluster_count": len(clusters),
            "aggregated_member_count": sum(len(item["members"]) for item in clusters),
            "quotient_node_count": len(set(mapping.values())),
            "quotient_edge_count": len(virtual_edge_buckets),
        },
    }


def project_device_id(device_id: Any, equivalence: Mapping[str, Any] | None) -> str:
    value = _text(device_id)
    if not value or not isinstance(equivalence, Mapping):
        return value
    mapping = equivalence.get("node_mapping", {})
    if not isinstance(mapping, Mapping):
        return value
    return _text(mapping.get(value, value)) or value


def project_device_set(
    device_ids: Iterable[Any], equivalence: Mapping[str, Any] | None
) -> Set[str]:
    return {
        projected
        for item in device_ids
        for projected in [project_device_id(item, equivalence)]
        if projected
    }


def project_directed_edges(
    edges: Iterable[Tuple[Any, Any]], equivalence: Mapping[str, Any] | None
) -> Set[Tuple[str, str]]:
    result: Set[Tuple[str, str]] = set()
    for raw_source, raw_target in edges:
        source = project_device_id(raw_source, equivalence)
        target = project_device_id(raw_target, equivalence)
        if source and target and source != target:
            result.add((source, target))
    return result
