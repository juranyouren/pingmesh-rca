"""Device voting inspired by SkyNet SIGCOMM 2025, section 7.1.

Unit weights and the explicit attribution rules are project adaptations, not
an implementation of the full SkyNet incident detection/evaluation system.
Only the observational fields named below participate in inference.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
from time import perf_counter
from typing import Any, Mapping


VERSION = "1.0.0"
CONTRACT_VERSION = "baseline-incident-v1"
ALARM_SOURCES = frozenset({"alarm", "alert"})
LOG_SOURCES = frozenset({"log", "syslog"})
SIGNATURE_FIELDS = (
    "device_id", "event_type", "event_time", "record_time", "severity", "message"
)


@dataclass(frozen=True)
class VotingConfig:
    """No fitted parameters; alternate variants receive different method names."""

    mode: str = "attribution"
    include_logs: bool = False

    def __post_init__(self) -> None:
        if self.mode not in {"attribution", "one_hop"}:
            raise ValueError("mode must be 'attribution' or 'one_hop'")
        if not isinstance(self.include_logs, bool):
            raise ValueError("include_logs must be a boolean")


def _identifier(value: Any) -> str | None:
    # IncidentInput uses strings; do not manufacture IDs from arbitrary values.
    return value if isinstance(value, str) and value.strip() else None


def _signature(event: Mapping[str, Any]) -> str:
    """Exact field signature, never a time bucket or root/score-derived key."""
    fields = {key: event.get(key) for key in SIGNATURE_FIELDS}
    fields["source"] = str(event.get("source", "")).strip().lower()
    for key in ("related_device_ids", "link_endpoints"):
        value = event.get(key)
        fields[key] = sorted(set(value)) if isinstance(value, list) and all(
            isinstance(item, str) for item in value
        ) else value
    payload = json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SkyNetVoting:
    """Return every candidate device, descending unit votes, then string ID."""

    def __init__(self, config: VotingConfig | Mapping[str, Any] | None = None) -> None:
        self.config = config if isinstance(config, VotingConfig) else VotingConfig(**dict(config or {}))

    @property
    def method(self) -> str:
        name = "SkyNet-inspired alert attribution voting"
        if self.config.mode == "one_hop":
            name = "SkyNet-inspired one-hop voting"
        if self.config.include_logs:
            name += " (alerts+logs adapt)"
        return name

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "version": VERSION,
            "supported_tasks": ["root"],
            "requires_fit": False,
            "score_semantics": "unit vote count; not a probability",
            "input_contract_version": CONTRACT_VERSION,
        }

    def predict_root(self, incident: Mapping[str, Any]) -> dict[str, Any]:
        started = perf_counter()
        devices = sorted({identifier for device in incident.get("devices", [])
                          if isinstance(device, Mapping)
                          and (identifier := _identifier(device.get("id"))) is not None})
        device_set = set(devices)
        adjacency: dict[str, set[str]] = {device: set() for device in devices}
        rejected_links = []
        for index, link in enumerate(incident.get("physical_links", [])):
            if not isinstance(link, Mapping):
                rejected_links.append({"input_index": index, "reason": "invalid_link_object"})
                continue
            u, v = _identifier(link.get("u")), _identifier(link.get("v"))
            if u not in device_set or v not in device_set or u == v:
                rejected_links.append({"input_index": index, "reason": "unknown_endpoint_or_self_loop"})
                continue
            adjacency[u].add(v)
            adjacency[v].add(u)

        scores: Counter[str] = Counter({device: 0 for device in devices})
        seen: dict[tuple[str, str], tuple[int, str]] = {}
        event_decisions: list[dict[str, Any]] = []
        vote_evidence: list[dict[str, Any]] = []
        permitted_sources = ALARM_SOURCES | (LOG_SOURCES if self.config.include_logs else frozenset())
        input_events = incident.get("events", [])

        for index, event in enumerate(input_events):
            if not isinstance(event, Mapping):
                event_decisions.append({"input_index": index, "status": "ignored", "reason": "invalid_event_object"})
                continue
            event_id = _identifier(event.get("event_id"))
            source = str(event.get("source", "")).strip().lower()
            decision: dict[str, Any] = {"input_index": index, "event_id": event_id,
                                        "source": source, "vote_device_ids": []}
            if source not in permitted_sources:
                decision.update(status="ignored", reason="source_not_enabled")
                event_decisions.append(decision)
                continue

            signature = _signature(event)
            dedup_key = ("event_id", event_id) if event_id else ("signature", signature)
            decision["dedup_key"] = {"kind": dedup_key[0], "value": dedup_key[1]}
            if dedup_key in seen:
                previous_index, previous_signature = seen[dedup_key]
                decision.update(status="ignored", reason="duplicate_event",
                                duplicate_of_input_index=previous_index,
                                conflicting_duplicate=signature != previous_signature)
                event_decisions.append(decision)
                continue
            seen[dedup_key] = (index, signature)

            owner = _identifier(event.get("device_id"))
            targets: dict[str, list[dict[str, Any]]] = defaultdict(list)
            mapping_issues: list[dict[str, Any]] = []
            if owner in device_set:
                targets[owner].append({"rule": "owning_device", "field": "device_id"})
            else:
                mapping_issues.append({"reason": "unknown_or_missing_owning_device", "device_id": owner})

            # A peer is evidence only when explicitly named AND physically adjacent.
            related = event.get("related_device_ids", [])
            if not isinstance(related, list):
                mapping_issues.append({"reason": "invalid_related_device_ids"})
                related = []
            for peer in sorted({item for item in related if _identifier(item) is not None}):
                if peer not in device_set:
                    mapping_issues.append({"reason": "unknown_related_device", "device_id": peer})
                elif owner not in device_set:
                    mapping_issues.append({"reason": "peer_without_known_owner", "device_id": peer})
                elif peer == owner:
                    # Already counted; the duplicate attribution does not add a vote.
                    targets[owner].append({"rule": "explicit_self_reference", "field": "related_device_ids"})
                elif peer in adjacency[owner]:
                    targets[peer].append({"rule": "explicit_connected_peer", "field": "related_device_ids",
                                          "physical_edge": [owner, peer]})
                else:
                    mapping_issues.append({"reason": "related_device_not_physically_adjacent", "device_id": peer})

            endpoints = event.get("link_endpoints", [])
            if endpoints not in ([], None):
                if not isinstance(endpoints, list) or len(endpoints) != 2 or any(
                    _identifier(item) is None for item in endpoints
                ):
                    mapping_issues.append({"reason": "invalid_link_endpoints"})
                else:
                    u, v = endpoints
                    if u not in device_set or v not in device_set:
                        mapping_issues.append({"reason": "unknown_link_endpoint", "link_endpoints": endpoints})
                    elif u == v or v not in adjacency[u]:
                        mapping_issues.append({"reason": "link_endpoints_not_physically_connected", "link_endpoints": endpoints})
                    else:
                        for endpoint in (u, v):
                            targets[endpoint].append({"rule": "explicit_physical_link_endpoint",
                                                      "field": "link_endpoints", "physical_edge": [u, v]})

            if self.config.mode == "one_hop":
                # Expand the resolved ownership set once, never transitively.
                for base in sorted(targets):
                    for peer in sorted(adjacency[base]):
                        targets[peer].append({"rule": "one_hop_extension", "physical_edge": [base, peer]})

            decision["mapping_issues"] = mapping_issues
            decision["vote_device_ids"] = sorted(targets)
            if not targets:
                decision.update(status="ignored", reason="no_resolved_device")
            else:
                decision.update(status="voted", reason="resolved_attribution")
                for device in sorted(targets):
                    scores[device] += 1
                    vote_evidence.append({"input_index": index, "event_id": event_id,
                                          "dedup_key": decision["dedup_key"], "device_id": device,
                                          "weight": 1, "attribution": targets[device]})
            event_decisions.append(decision)

        ranking = [{"device_id": device, "score": scores[device]}
                   for device in sorted(devices, key=lambda device: (-scores[device], device))]
        groups: dict[int, list[str]] = defaultdict(list)
        for row in ranking:
            groups[row["score"]].append(row["device_id"])
        tie_groups = [{"score": score, "device_ids": group} for score, group in groups.items() if len(group) > 1]
        voted_events = sum(decision["status"] == "voted" for decision in event_decisions)
        status = "ok" if vote_evidence else "abstained"
        if not devices:
            status = "input_ineligible"
        return {
            "case_id": incident.get("case_id"), "method": self.method, "version": VERSION,
            "status": status, "root_ranking": ranking,
            "diagnostics": {
                "config": asdict(self.config), "input_contract_version": CONTRACT_VERSION,
                "score_semantics": "unit vote count; not a probability",
                "candidate_count": len(devices), "input_event_count": len(input_events),
                "unique_eligible_event_count": len(seen), "voted_event_count": voted_events,
                "total_votes": len(vote_evidence),
                "ignored_event_count": len(event_decisions) - voted_events,
                "ignored_reason_counts": dict(Counter(decision["reason"] for decision in event_decisions if decision["status"] == "ignored")),
                "event_decisions": event_decisions, "vote_evidence": vote_evidence,
                "rejected_physical_links": rejected_links,
                "zero_vote_device_ids": [device for device in devices if scores[device] == 0],
                "tie_break": "ascending device ID (Unicode lexicographic)", "tie_groups": tie_groups,
                "tied_device_fraction": sum(len(group["device_ids"]) for group in tie_groups) / len(devices) if devices else 0.0,
                "top_score_tied": len(groups[ranking[0]["score"]]) > 1 if ranking else False,
                "reason": "no_candidate_devices" if not devices else ("no_resolved_votes" if not vote_evidence else None),
            },
            "timing": {"predict_seconds": perf_counter() - started},
        }


def predict_root(incident: Mapping[str, Any], config: VotingConfig | Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Convenience entry point for the common prediction runner."""
    return SkyNetVoting(config).predict_root(incident)
