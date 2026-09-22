"""Audit tests for the remote entity resolver.

The resolver answers one question only: *which device, if any, does an observed
remote entity belong to?* It may consume declared inventory and topology facts.
It must never invent an attribution from address arithmetic.
"""
import unittest


def node(device_id, name, **extra):
    return {"device_id": device_id, "name": name, **extra}


def link(edge_id, a, a_port, b, b_port):
    return {
        "edge_id": edge_id,
        "endpoint_a": a,
        "endpoint_a_port": a_port,
        "endpoint_b": b,
        "endpoint_b_port": b_port,
    }


def topology(nodes, edges=None):
    return {"schema_version": "topology-context-v1", "nodes": nodes, "edges": edges or []}


# 10.0.0.1 --GE1/0/0===GE1/0/1-- 10.0.0.2
TWO_DEVICE_TOPOLOGY = topology(
    [
        node("10.0.0.1", "PE-1", role="PE"),
        node("10.0.0.2", "PE-2", role="PE"),
    ],
    [link("L-aaa", "10.0.0.1", "GE1/0/0", "10.0.0.2", "GE1/0/1")],
)


class ResolutionTests(unittest.TestCase):
    def test_mgmt_ip_resolves_uniquely_at_full_confidence(self):
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        result = resolve_remote_entity(
            "bgp_session_ip", "10.0.0.2", topology_context=TWO_DEVICE_TOPOLOGY
        )

        self.assertEqual(result.status, "resolved")
        self.assertEqual([c.device_id for c in result.candidates], ["10.0.0.2"])
        self.assertEqual(result.candidates[0].confidence, 1.0)
        self.assertEqual(result.candidates[0].source, "inventory:mgmt_ip")

    def test_device_name_resolves_uniquely(self):
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        result = resolve_remote_entity(
            "bgp_session_ip", "PE-2", topology_context=TWO_DEVICE_TOPOLOGY
        )

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.candidates[0].device_id, "10.0.0.2")
        self.assertEqual(result.candidates[0].confidence, 1.0)

    def test_session_ip_absent_from_inventory_is_unresolved(self):
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        result = resolve_remote_entity(
            "bgp_session_ip", "28.219.131.16", topology_context=TWO_DEVICE_TOPOLOGY
        )

        self.assertEqual(result.status, "unresolved")
        self.assertEqual(result.candidates, ())

    def test_same_subnet_is_not_an_attribution(self):
        """Address arithmetic must never stand in for a declared identity."""
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        result = resolve_remote_entity(
            "bgp_session_ip", "10.0.0.99", topology_context=TWO_DEVICE_TOPOLOGY
        )

        self.assertEqual(result.status, "unresolved")
        self.assertEqual(result.candidates, ())

    def test_topology_port_derives_the_remote_device(self):
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        result = resolve_remote_entity(
            "lldp_neighbor",
            "GE1/0/0",
            topology_context=TWO_DEVICE_TOPOLOGY,
            local_device_id="10.0.0.1",
        )

        self.assertEqual(result.status, "resolved")
        self.assertEqual([c.device_id for c in result.candidates], ["10.0.0.2"])
        self.assertAlmostEqual(result.candidates[0].confidence, 0.8, places=6)
        self.assertEqual(result.candidates[0].source, "topology:port")

    def test_topology_port_lookup_is_direction_aware(self):
        """The remote port resolves back to the near end, not to itself."""
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        result = resolve_remote_entity(
            "lldp_neighbor",
            "GE1/0/1",
            topology_context=TWO_DEVICE_TOPOLOGY,
            local_device_id="10.0.0.2",
        )

        self.assertEqual([c.device_id for c in result.candidates], ["10.0.0.1"])

    def test_interface_value_without_local_device_is_unresolved(self):
        """A port name is device-scoped; without an owner it proves nothing."""
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        result = resolve_remote_entity(
            "lldp_neighbor", "GE1/0/0", topology_context=TWO_DEVICE_TOPOLOGY
        )

        self.assertEqual(result.status, "unresolved")

    def test_duplicate_declared_name_is_ambiguous_and_splits_confidence(self):
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        context = topology(
            [node("10.0.0.1", "PE-1"), node("10.0.0.2", "SPINE"), node("10.0.0.3", "SPINE")]
        )
        result = resolve_remote_entity("bgp_session_ip", "SPINE", topology_context=context)

        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(
            sorted(c.device_id for c in result.candidates), ["10.0.0.2", "10.0.0.3"]
        )
        for candidate in result.candidates:
            self.assertAlmostEqual(candidate.confidence, 0.5, places=6)

    def test_port_shared_by_two_links_is_ambiguous(self):
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        context = topology(
            [
                node("10.0.0.1", "PE-1"),
                node("10.0.0.2", "PE-2"),
                node("10.0.0.3", "PE-3"),
            ],
            [
                link("L-aaa", "10.0.0.1", "Agg5", "10.0.0.2", "GE1/0/1"),
                link("L-bbb", "10.0.0.1", "Agg5", "10.0.0.3", "GE1/0/1"),
            ],
        )
        result = resolve_remote_entity(
            "lldp_neighbor", "Agg5", topology_context=context, local_device_id="10.0.0.1"
        )

        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(
            sorted(c.device_id for c in result.candidates), ["10.0.0.2", "10.0.0.3"]
        )

    def test_resolution_carries_provenance(self):
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        result = resolve_remote_entity(
            "lldp_neighbor",
            "GE1/0/0",
            topology_context=TWO_DEVICE_TOPOLOGY,
            local_device_id="10.0.0.1",
        )

        self.assertIn("L-aaa", result.provenance)

    def test_confidence_for_pair_device_is_zero_when_unresolved(self):
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        result = resolve_remote_entity(
            "bgp_session_ip", "28.219.131.16", topology_context=TWO_DEVICE_TOPOLOGY
        )

        self.assertEqual(result.confidence_for("10.0.0.2"), 0.0)

    def test_confidence_for_pair_device_is_zero_for_a_non_candidate(self):
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        result = resolve_remote_entity(
            "bgp_session_ip", "10.0.0.2", topology_context=TWO_DEVICE_TOPOLOGY
        )

        self.assertEqual(result.confidence_for("10.0.0.3"), 0.0)

    def test_explicit_inventory_context_overrides_topology_nodes(self):
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        result = resolve_remote_entity(
            "bgp_session_ip",
            "10.0.0.2",
            topology_context=topology([]),
            inventory_context=[{"device_id": "10.0.0.2", "name": "PE-2"}],
        )

        self.assertEqual(result.status, "resolved")

    def test_result_is_json_serializable(self):
        import json

        from Sys.RootCauseAnalyze.propagation.resolution import resolve_remote_entity

        result = resolve_remote_entity(
            "bgp_session_ip", "10.0.0.2", topology_context=TWO_DEVICE_TOPOLOGY
        )

        payload = result.to_dict()
        self.assertEqual(payload["status"], "resolved")
        self.assertEqual(payload["candidates"][0]["device_id"], "10.0.0.2")
        json.dumps(payload)


class EpisodePeerResolutionTests(unittest.TestCase):
    def test_resolution_annotates_episodes_and_never_replaces_raw_peer(self):
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_episode_peers

        episodes = [
            {"evidence_id": "E1", "device_id": "10.0.0.1", "peer_raw": "10.0.0.2",
             "object_type": "bgp_session", "peer_device": ""},
            {"evidence_id": "E2", "device_id": "10.0.0.1", "peer_raw": "28.219.131.16",
             "object_type": "bgp_session", "peer_device": ""},
        ]

        resolved = resolve_episode_peers(episodes, TWO_DEVICE_TOPOLOGY)

        self.assertEqual(resolved[0]["peer_resolution"]["status"], "resolved")
        self.assertEqual(resolved[0]["peer_resolution"]["candidates"][0]["device_id"], "10.0.0.2")
        self.assertEqual(resolved[1]["peer_resolution"]["status"], "unresolved")
        self.assertEqual(resolved[0]["peer_raw"], "10.0.0.2")

    def test_episode_without_a_peer_is_marked_not_applicable(self):
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_episode_peers

        episodes = [
            {"evidence_id": "E1", "device_id": "10.0.0.1", "peer_raw": "",
             "object_type": "interface", "peer_device": ""}
        ]

        resolved = resolve_episode_peers(episodes, TWO_DEVICE_TOPOLOGY)

        self.assertEqual(resolved[0]["peer_resolution"]["status"], "not_applicable")

    def test_lldp_episode_resolves_its_remote_through_the_local_port(self):
        """An LLDP event names the near port; the far device comes from topology."""
        from Sys.RootCauseAnalyze.propagation.resolution import resolve_episode_peers

        episodes = [
            {"evidence_id": "E1", "device_id": "10.0.0.1", "peer_raw": "",
             "object_type": "neighbor_adjacency", "object": "GE1/0/0", "peer_device": ""}
        ]

        resolved = resolve_episode_peers(episodes, TWO_DEVICE_TOPOLOGY)

        self.assertEqual(resolved[0]["peer_resolution"]["status"], "resolved")
        self.assertEqual(
            resolved[0]["peer_resolution"]["candidates"][0]["device_id"], "10.0.0.2"
        )


if __name__ == "__main__":
    unittest.main()
