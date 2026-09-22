"""Remote entity resolution: bind an observed remote entity to a device.

An incident observation frequently names its remote end with a local identifier:
a BGP session address, an OSPF router-id, an LLDP neighbour port. Those
identifiers are *not* management addresses, so binding them to a device is a
separate, auditable step rather than something the evidence encoder may guess.

This module answers exactly one question:

    given an observed remote entity, which device does it belong to?

It consumes only declared facts - the device inventory and the topology context.
Address arithmetic ("same subnet", "looks like a peer") is deliberately **not**
an attribution source. Unknown or unavailable evidence stays unresolved instead
of becoming a silent false negative or a silent false positive.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple

# Confidence assigned to an entity bound by a declared topology relation rather
# than by a declared device identity. A port relation is strong but indirect:
# it proves the remote *port* belongs to a device, not that the observed session
# terminates on it.
TOPOLOGY_DERIVATION_CONFIDENCE = 0.8

_STATUS_RESOLVED = "resolved"
_STATUS_AMBIGUOUS = "ambiguous"
_STATUS_UNRESOLVED = "unresolved"
_STATUS_NOT_APPLICABLE = "not_applicable"

# Entity types whose value names a port rather than an address. Port names are
# device-scoped, so they are only meaningful together with their owning device.
_INTERFACE_LIKE_TYPES = frozenset(
    {"interface", "port", "lldp_neighbor", "neighbor_adjacency", "local_interface"}
)


@dataclass(frozen=True)
class ResolutionCandidate:
    """One device that the observed entity may belong to."""

    device_id: str
    confidence: float
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "confidence": round(float(self.confidence), 6),
            "source": self.source,
        }


@dataclass(frozen=True)
class ResolutionResult:
    """The auditable outcome of resolving one remote entity."""

    entity_type: str
    value: str
    status: str
    candidates: Tuple[ResolutionCandidate, ...] = ()
    provenance: Tuple[str, ...] = ()
    reason: str = ""

    @property
    def resolved(self) -> bool:
        return self.status == _STATUS_RESOLVED

    def confidence_for(self, device_id: str) -> float:
        """Attribution of this entity to ``device_id`` (0.0 when not a candidate)."""

        target = _normalize_scalar(device_id)
        for candidate in self.candidates:
            if _normalize_scalar(candidate.device_id) == target:
                return float(candidate.confidence)
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "value": self.value,
            "status": self.status,
            "reason": self.reason,
            "candidates": [item.to_dict() for item in self.candidates],
            "provenance": list(self.provenance),
        }


def _normalize_scalar(value: Any) -> str:
    return str(value or "").strip()


def _device_id_of(device: Mapping[str, Any]) -> str:
    """The owning device of an inventory row.

    Topology-context nodes carry ``device_id``; raw node files carry ``mgmt_ip``
    instead. Both name the same thing, so both are accepted here rather than
    forcing every caller to pre-normalise.
    """

    for key in ("device_id", "mgmt_ip", "ip"):
        value = _normalize_scalar(device.get(key))
        if value:
            return value
    return ""


def _identity_key(value: Any) -> str:
    """Addresses and device names are compared case-insensitively."""

    return _normalize_scalar(value).casefold()


def _device_entries(
    topology_context: Mapping[str, Any] | None,
    inventory_context: Sequence[Mapping[str, Any]] | None,
) -> List[Mapping[str, Any]]:
    if inventory_context is not None:
        return [item for item in inventory_context if isinstance(item, Mapping)]
    context = topology_context if isinstance(topology_context, Mapping) else {}
    nodes = context.get("nodes")
    if isinstance(nodes, Sequence) and not isinstance(nodes, (str, bytes)):
        return [item for item in nodes if isinstance(item, Mapping)]
    if isinstance(nodes, Mapping):
        return [item for item in nodes.values() if isinstance(item, Mapping)]
    return []


def _declared_addresses(device: Mapping[str, Any]) -> List[str]:
    """Addresses a device explicitly declares for itself.

    ``device_id`` is the management address in this repository's topology
    context. Optional ``mgmt_ip``/``ip``/``ips``/``loopback_ips`` keys are
    honoured so a richer inventory can be supplied without changing the
    resolver.
    """

    declared: List[str] = []
    for key in ("device_id", "mgmt_ip", "ip"):
        value = _normalize_scalar(device.get(key))
        if value:
            declared.append(value)
    for key in ("ips", "loopback_ips", "interface_ips", "addresses"):
        values = device.get(key)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            declared.extend(_normalize_scalar(item) for item in values if item)
    seen: Dict[str, None] = {}
    for value in declared:
        if value:
            seen.setdefault(value, None)
    return list(seen)


def _topology_edges(
    topology_context: Mapping[str, Any] | None,
) -> List[Mapping[str, Any]]:
    context = topology_context if isinstance(topology_context, Mapping) else {}
    edges = context.get("edges")
    if isinstance(edges, Sequence) and not isinstance(edges, (str, bytes)):
        return [item for item in edges if isinstance(item, Mapping)]
    return []


def _topology_candidates(
    value: str,
    local_device_id: str,
    topology_context: Mapping[str, Any] | None,
) -> List[Tuple[str, str]]:
    """Return ``(remote_device_id, edge_id)`` pairs for a locally owned port."""

    owner = _identity_key(local_device_id)
    port = _identity_key(value)
    if not owner or not port:
        return []
    found: Dict[str, str] = {}
    for edge in _topology_edges(topology_context):
        edge_id = _normalize_scalar(edge.get("edge_id"))
        for near_key, near_port_key, far_key in (
            ("endpoint_a", "endpoint_a_port", "endpoint_b"),
            ("endpoint_b", "endpoint_b_port", "endpoint_a"),
        ):
            if _identity_key(edge.get(near_key)) != owner:
                continue
            if _identity_key(edge.get(near_port_key)) != port:
                continue
            remote = _normalize_scalar(edge.get(far_key))
            if remote and _identity_key(remote) != owner:
                found.setdefault(remote, edge_id)
    return sorted(found.items())


def resolve_remote_entity(
    entity_type: str,
    value: str,
    *,
    topology_context: Mapping[str, Any] | None = None,
    inventory_context: Sequence[Mapping[str, Any]] | None = None,
    local_device_id: str | None = None,
) -> ResolutionResult:
    """Bind an observed remote entity to zero, one, or several candidate devices.

    Tiers, in order of decreasing evidence strength:

    * **T1 declared identity** - the value is an address or name a device
      explicitly declares for itself. Confidence ``1.0``.
    * **T2 topology derivation** - the value is a port on a known local device
      and the topology declares which device holds the far end. Confidence
      ``0.8``.
    * **T3 ambiguous** - several distinct devices are equally supported. The
      tier confidence is split across them; no candidate is preferred.
    * **T4 unresolved** - no declared fact supports any device.
    """

    raw_value = _normalize_scalar(value)
    device_type = _normalize_scalar(entity_type) or "unknown"
    if not raw_value:
        return ResolutionResult(
            entity_type=device_type,
            value=raw_value,
            status=_STATUS_UNRESOLVED,
            reason="empty_entity_value",
        )

    devices = _device_entries(topology_context, inventory_context)
    key = _identity_key(raw_value)

    # --- T1: declared device identity -------------------------------------
    for field_name, source in (("address", "inventory:mgmt_ip"), ("name", "inventory:name")):
        matched: List[str] = []
        for device in devices:
            device_id = _device_id_of(device)
            if not device_id:
                continue
            values = _declared_addresses(device) if field_name == "address" else [
                _normalize_scalar(device.get("name"))
            ]
            if any(_identity_key(item) == key for item in values if item):
                matched.append(device_id)
        matched = sorted(dict.fromkeys(matched))
        if not matched:
            continue
        share = 1.0 / len(matched)
        candidates = tuple(
            ResolutionCandidate(device_id=item, confidence=share, source=source)
            for item in matched
        )
        status = _STATUS_RESOLVED if len(matched) == 1 else _STATUS_AMBIGUOUS
        return ResolutionResult(
            entity_type=device_type,
            value=raw_value,
            status=status,
            candidates=candidates,
            provenance=tuple(f"{source}:{item}" for item in matched),
            reason="declared_device_identity" if status == _STATUS_RESOLVED
            else "multiple_devices_declare_this_identity",
        )

    # --- T2: topology-derived port ownership ------------------------------
    if device_type in _INTERFACE_LIKE_TYPES and _normalize_scalar(local_device_id):
        derived = _topology_candidates(raw_value, str(local_device_id), topology_context)
        if derived:
            share = TOPOLOGY_DERIVATION_CONFIDENCE / len(derived)
            candidates = tuple(
                ResolutionCandidate(device_id=item, confidence=share, source="topology:port")
                for item, _ in derived
            )
            status = _STATUS_RESOLVED if len(derived) == 1 else _STATUS_AMBIGUOUS
            return ResolutionResult(
                entity_type=device_type,
                value=raw_value,
                status=status,
                candidates=candidates,
                provenance=tuple(edge_id for _, edge_id in derived if edge_id),
                reason="topology_port_ownership" if status == _STATUS_RESOLVED
                else "port_present_on_multiple_links",
            )

    # --- T4: no declared fact supports any device -------------------------
    return ResolutionResult(
        entity_type=device_type,
        value=raw_value,
        status=_STATUS_UNRESOLVED,
        reason="no_declared_identity_or_topology_relation",
    )


def _episode_entity_type(episode: Mapping[str, Any]) -> str:
    """Derive the remote entity namespace an episode's peer value lives in."""

    canonical = episode.get("canonical_evidence")
    if isinstance(canonical, Mapping):
        peer = canonical.get("peer")
        if isinstance(peer, Mapping) and peer.get("address_namespace"):
            return _normalize_scalar(peer.get("address_namespace"))
    object_type = _normalize_scalar(episode.get("object_type"))
    if object_type in {"neighbor_adjacency", "lldp_neighbor"}:
        return "lldp_neighbor"
    return "unverified_peer_address"


def resolve_episode_peers(
    episodes: Sequence[Mapping[str, Any]],
    topology_context: Mapping[str, Any] | None = None,
    *,
    inventory_context: Sequence[Mapping[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """Annotate episodes with the resolution of their remote entity.

    The raw peer token is preserved untouched; the resolution is added under
    ``peer_resolution`` so downstream stages can gate on it without re-deriving
    it, and so the reader can always audit what was actually observed.
    """

    resolved: List[Dict[str, Any]] = []
    for raw in episodes:
        if not isinstance(raw, Mapping):
            continue
        episode = dict(raw)
        entity_type = _episode_entity_type(episode)
        local_device_id = _normalize_scalar(episode.get("device_id")) or None
        remote_value = _normalize_scalar(episode.get("peer_raw"))
        derived_from = "peer_raw" if remote_value else ""
        if not remote_value and entity_type == "lldp_neighbor":
            # A neighbour event names the near port. Which device holds the far
            # end is a declared topology fact, not a guess, so it may be used.
            port = _normalize_scalar(episode.get("object"))
            if port:
                remote_value = port
                derived_from = "local_port"
        if not remote_value:
            episode["peer_resolution"] = ResolutionResult(
                entity_type=entity_type,
                value="",
                status=_STATUS_NOT_APPLICABLE,
                reason="episode_names_no_remote_entity",
            ).to_dict()
        else:
            payload = resolve_remote_entity(
                entity_type,
                remote_value,
                topology_context=topology_context,
                inventory_context=inventory_context,
                local_device_id=local_device_id,
            ).to_dict()
            payload["derived_from"] = derived_from
            episode["peer_resolution"] = payload
        resolved.append(episode)
    return resolved


def peer_attribution(episode: Mapping[str, Any], other_device_id: str) -> float:
    """Attribution of one episode to the device pair it is being evaluated in.

    An episode that names no remote entity belongs unambiguously to its own
    device, so it is attributed to the pair at full weight - the pair itself
    already comes from the topology-constrained candidate graph. An episode that
    *does* name a remote entity is only attributable when that entity is
    resolved to the other device of the pair.
    """

    resolution = episode.get("peer_resolution")
    if not isinstance(resolution, Mapping):
        # Unresolved because resolution never ran is not evidence of a link.
        return 0.0 if _normalize_scalar(episode.get("peer_raw")) else 1.0
    status = _normalize_scalar(resolution.get("status"))
    if status == _STATUS_NOT_APPLICABLE:
        return 1.0
    for candidate in resolution.get("candidates", []) or []:
        if not isinstance(candidate, Mapping):
            continue
        if _identity_key(candidate.get("device_id")) == _identity_key(other_device_id):
            return float(candidate.get("confidence", 0.0) or 0.0)
    return 0.0
