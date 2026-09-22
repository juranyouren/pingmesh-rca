"""Loss-aware bridge from canonical LLM facts to the existing M1/M2 schema."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from Sys.Preprocess.evidence.encoder import stable_id
from Sys.utils.case_utils import get_device_ip


def to_episodes(incident):
    episodes = []
    seen = set()
    for device in incident["devices"]:
        device_id = device["device"]["device_id"]
        for evidence in device["evidence"]:
            eid = evidence["evidence_id"]
            if eid in seen or evidence["device_id"] != device_id:
                raise ValueError("Duplicate evidence ID or mismatched device")
            seen.add(eid)
            predicate = evidence["predicate"]
            state = evidence["value"].get("state")
            event_type, layer = {
                "interface_flap": ("interface_state_down", "physical"),
                "bgp_adjacency_down": ("bgp_session_down", "routing"),
                "bgp_adjacency_up": ("bgp_session_up", "routing"),
                "bfd_session_down": ("bfd_session_down", "routing"),
                "lldp_neighbor_rebuild": ("lldp_neighbor_recovery", "link"),
                "device_restart": ("device_health", "device"),
            }.get(predicate, ("generic_event", "unknown"))
            if predicate == "interface_state_change":
                event_type, layer = ("interface_state_down" if state == "down" else "physical_link_up"), "physical"
            clear = state in ("up", "rebuild", "recovery", "recovered")
            confidence = evidence["quality"]["mapping_confidence"]
            # Raw times were not independently verified: they never create temporal edges.
            # A session IP is not a management IP: no peer resolution is invented here.
            episode = {
                "evidence_id": eid, "device_id": device_id,
                "raw_evidence_ids": evidence["provenance"]["raw_event_ids"],
                "source_types": evidence["provenance"]["source_types"],
                "event_type": event_type, "fault_layer": layer,
                "object_type": evidence["entity"]["entity_type"],
                "object": evidence["entity"]["local_name"], "peer_device": "",
                "peer_raw": evidence.get("peer", {}).get("address", ""),
                "observation_scope": "local" if evidence["entity"]["entity_type"] in ("interface", "device") else "unknown",
                "lifecycle": "clear" if clear else "raised",
                "onset_time_ms": None, "onset_interval_ms": None,
                "end_time_ms": None, "end_interval_ms": None,
                "duplicate_count": evidence["source_count"],
                "parse_method": "llm_encoder", "parse_status": "success",
                "quality": {"timestamp": 0.0, "description": confidence, "object": 1.0,
                            "peer": 0.0, "traceability": 1.0, "core": confidence},
                "incident_relevance": round((0.2 if clear else 0.6) * confidence, 6),
                "predicate": predicate, "value": copy.deepcopy(evidence["value"]),
                "possible_effects": list(evidence["possible_effects"]),
                "canonical_evidence": copy.deepcopy(evidence),
            }
            episodes.append(episode)
    return episodes


def load_episodes(evidence_root, case_id, nodes):
    path = Path(evidence_root) / case_id / "incident.json"
    incident = json.loads(path.read_text(encoding="utf-8"))
    if incident.get("incident_id") != case_id:
        raise ValueError(f"Incident mismatch: {path}")
    if incident.get("input_fingerprint") != stable_id("input_", nodes):
        raise ValueError(f"Evidence is stale or input differs; re-encode: {path}")
    expected = {get_device_ip(n) for n in nodes}
    actual = {d["device"]["device_id"] for d in incident["devices"]}
    if actual != expected:
        raise ValueError(f"Encoded device set differs from input: {path}")
    return to_episodes(incident), incident
