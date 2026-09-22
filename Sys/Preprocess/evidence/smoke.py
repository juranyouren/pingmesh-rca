"""Synthetic integration fixtures. Never used implicitly for real inference."""
import json
import re

from Sys.Preprocess.llm_encoder import write_json
from Sys.RootCauseAnalyze.propagation.topology_context import build_topology_context


class SmokeEngine:
    model_path = "SYNTHETIC_SMOKE_ONLY"

    def generate_json(self, prompt):
        data = json.loads(prompt.split("DATA_JSON=", 1)[1])
        if "unknown_events" in data:
            return {"concepts": []}
        mappings = []
        for record in data["records"]:
            text = record["description"]
            interface = re.search(r"Interface (\S+), changed state to (up|down)", text)
            bgp = re.search(r"BGP peer (\S+) session down", text)
            mapping = {"raw_event_id": record["raw_event_id"], "predicate": "UNKNOWN"}
            if interface:
                mapping.update(predicate="interface_state_change", entity={"entity_type": "interface", "local_name": interface[1]}, value={"state": interface[2]}, mapping_confidence=1.0)
            elif bgp:
                mapping.update(predicate="bgp_adjacency_down", entity={"entity_type": "bgp_session", "local_name": bgp[1]}, value={"state": "down"}, mapping_confidence=1.0)
            mappings.append(mapping)
        return {"mappings": mappings}


def create_cases(root):
    for index in (1, 2):
        ips = [f"10.{index}.0.{i}" for i in (1, 2, 3)]
        event = {"alarm_name": "vendor_down", "description": "Interface Eth1, changed state to down.", "alarm_time": 1700000000000}
        nodes = [
            {"mgmt_ip": ips[0], "name": "core", "alarms": [event], "logs": [dict(event, source="syslog")], "linked_to": [ips[1]], "linked_from": []},
            {"mgmt_ip": ips[1], "name": "leaf", "alarms": [{"description": f"BGP peer {ips[0]} session down", "alarm_time": 1700000000000}], "logs": [], "linked_from": [ips[0]], "linked_to": [ips[2]]},
            {"mgmt_ip": ips[2], "name": "host", "alarms": [], "logs": [], "linked_from": [ips[1]], "linked_to": []},
        ]
        info = {"alarm_time": 1700000000000, "source_ip": [ips[0]], "sink_ip": [ips[2]]}
        topo = [[{"nodes": nodes, "links": [{"src_ip": ips[0], "dst_ip": ips[1]}, {"src_ip": ips[1], "dst_ip": ips[2]}]}]]
        case = root / f"smoke_{index}"
        write_json(case / "nodes.json", nodes)
        write_json(case / "info.json", info)
        write_json(case / "topology_context.json", build_topology_context(topo, info))
        write_json(case / "label.json", [{"ranking": 1, "abnormal_node": [{"ip": ips[0]}]}])
        write_json(case / "propagation_label.json", {"root_scope": "device", "root_devices": [ips[0]],
                   "edges": [{"from": ips[0], "to": ips[1], "membership": "definite"}, {"from": ips[1], "to": ips[2], "membership": "definite"}]})
