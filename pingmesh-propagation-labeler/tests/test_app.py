import importlib.util
import json
from pathlib import Path

import pytest


def _load_labeler():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "propagation_labeler"
        / "app.py"
    )
    spec = importlib.util.spec_from_file_location("propagation_labeler", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def labeler():
    return _load_labeler()


def _write_case(root: Path, case_id: str = "CASE_001") -> Path:
    case_dir = root / "batch" / case_id
    case_dir.mkdir(parents=True)
    (case_dir / "info.json").write_text(
        json.dumps(
            {
                "alarm_name": "pingmesh loss",
                "alarm_time": 1_700_000_000_000,
                "source_ip": '["A"]',
                "sink_ip": '["C"]',
            }
        ),
        encoding="utf-8",
    )
    nodes = {
        "node-a": {
            "mgmt_ip": "A",
            "name": "node-a",
            "role": "SPINE",
            "linked_to": ["B"],
            "linked_from": [],
            "alarms": [
                {
                    "alarm_time": 1_700_000_000_010,
                    "name": "linkDown_active",
                    "description": "Interface physical link is down",
                }
            ],
            "logs": [],
        },
        "node-b": {
            "mgmt_ip": "B",
            "name": "node-b",
            "role": "LEAF",
            "linked_to": ["C"],
            "linked_from": ["A"],
            "alarms": [],
            "logs": [],
        },
        "node-c": {
            "mgmt_ip": "C",
            "name": "node-c",
            "role": "SERVER",
            "linked_to": [],
            "linked_from": ["B"],
            "alarms": [],
            "logs": [],
        },
    }
    (case_dir / "nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
    return case_dir


def _node(device_id: str, role: str = "propagation") -> dict:
    return {
        "device_id": device_id,
        "role": role,
        "membership": "definite",
        "onset_interval": None,
        "evidence_ids": [],
        "note": "",
    }


def _edge(edge_id: str, source: str, target: str) -> dict:
    return {
        "edge_id": edge_id,
        "from": source,
        "to": target,
        "membership": "definite",
        "relation": "physical_link",
        "direction_status": "confirmed",
        "lag_interval_ms": None,
        "evidence_ids": [],
        "alternative_group": "",
        "note": "",
    }


def _event(evidence_id: str, device_id: str, role: str = "supporting") -> dict:
    return {
        "evidence_id": evidence_id,
        "device_id": device_id,
        "role": role,
        "state": "definite",
        "note": "",
    }


def _ee_edge(edge_id: str, source: str, target: str) -> dict:
    return {
        "ee_edge_id": edge_id,
        "source_evidence_id": source,
        "target_evidence_id": target,
        "state": "definite",
        "relation": "dependency_or_evolution",
        "direction_status": "confirmed",
        "lag_interval_ms": None,
        "supports_dd_edge_ids": [],
        "note": "",
    }


def test_discovers_nested_case_and_builds_fallback_graph(tmp_path, labeler):
    data_root = tmp_path / "nodes"
    case_dir = _write_case(data_root)

    assert labeler.discover_cases(data_root) == {"CASE_001": case_dir.resolve()}
    store = labeler.LabelingStore(data_root, tmp_path / "labels")
    bundle = store.case_bundle("CASE_001")

    assert bundle["topology"]["source"] == "processed_nodes_fallback"
    assert {item["device_id"] for item in bundle["topology"]["nodes"]} == {"A", "B", "C"}
    assert {
        frozenset((item["endpoint_a"], item["endpoint_b"]))
        for item in bundle["topology"]["edges"]
    } == {frozenset(("A", "B")), frozenset(("B", "C"))}
    assert bundle["topology"]["source_anchors"] == ["A", "B"]
    assert bundle["topology"]["sink_anchors"] == ["B", "C"]
    nodes_by_id = {
        item["device_id"]: item for item in bundle["topology"]["nodes"]
    }
    assert nodes_by_id["A"]["is_source_endpoint"] is True
    assert nodes_by_id["A"]["is_sink_endpoint"] is False
    assert nodes_by_id["B"]["is_source_anchor"] is True
    assert nodes_by_id["B"]["is_source_endpoint"] is False
    assert nodes_by_id["C"]["is_sink_endpoint"] is True
    assert len(bundle["evidence"]) == 1
    assert len(bundle["events"]) == 1
    assert bundle["events"][0]["event_type"] == "generic_event"
    assert bundle["evidence"][0]["details"]["description"] == "Interface physical link is down"
    assert bundle["topology"]["nodes"][0]["evidence_ids"] == [
        bundle["evidence"][0]["evidence_id"]
    ]


def test_source_label_roots_seed_the_simple_annotation_label(tmp_path, labeler):
    data_root = tmp_path / "nodes"
    case_dir = _write_case(data_root)
    (case_dir / "label_v2.json").write_text(
        json.dumps(
            {
                "primary_root_causes": [{"ip": "A"}],
                "secondary_root_causes": [{"device_id": "B"}],
            }
        ),
        encoding="utf-8",
    )

    bundle = labeler.LabelingStore(data_root, tmp_path / "labels").case_bundle(
        "CASE_001"
    )

    assert bundle["source_root_devices"] == ["A", "B"]
    assert bundle["label"]["root_scope"] == "multiple_devices"
    assert bundle["label"]["root_devices"] == ["A", "B"]
    assert {
        item["device_id"]
        for item in bundle["label"]["nodes"]
        if item["role"] == "root" and item["membership"] == "definite"
    } == {"A", "B"}


def test_normalises_manual_transit_core_topology_overrides(labeler):
    label = labeler.default_label("CASE_001")
    label["topology_overrides"] = {
        "virtual_nodes": [
            {"device_id": "MANUAL-CORE-1", "name": "中转 CORE", "topology_role": "SPINE"}
        ],
        "virtual_edges": [
            {"edge_id": "MT1", "endpoint_a": "S1", "endpoint_b": "MANUAL-CORE-1"},
            {"edge_id": "DROP", "endpoint_a": "S1", "endpoint_b": "S2"},
        ],
    }

    normalised = labeler._normalise_label(label, "CASE_001")

    assert normalised["topology_overrides"]["virtual_nodes"] == [
        {
            "device_id": "MANUAL-CORE-1",
            "name": "中转 CORE",
            "topology_role": "CORE",
            "is_inferred": True,
            "annotation_selectable": False,
            "inference_kind": "manual_transit_core",
            "note": "",
        }
    ]
    assert [item["edge_id"] for item in normalised["topology_overrides"]["virtual_edges"]] == [
        "MT1"
    ]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("region-a-pod01-leaf-1", 1),
        ("region-a_nc01_pod001-ce6885-rap", 1),
        ("POD-42-spine", 42),
        ("region-a-spd01-leaf", None),
        ("region-a-pod-leaf", None),
    ],
)
def test_extracts_numeric_pod_suffix_from_device_name(labeler, name, expected):
    assert labeler._parse_pod_number(name) == expected


def test_reconstructs_collapsed_leaf_core_as_non_labelable_spine_set(labeler):
    nodes = [
        {
            "device_id": "L1",
            "name": "region-a-pod007-tor-1",
            "topology_role": "LEAF",
        },
        {
            "device_id": "C1",
            "name": "region-a-core-1",
            "topology_role": "CORE",
        },
        {
            "device_id": "C2",
            "name": "region-a-core-2",
            "topology_role": "CORE",
        },
    ]
    edges = [
        {"edge_id": "RAW-1", "endpoint_a": "L1", "endpoint_b": "C1"},
        {"edge_id": "RAW-2", "endpoint_a": "L1", "endpoint_b": "C2"},
        {"edge_id": "RAW-3", "endpoint_a": "C1", "endpoint_b": "C2"},
    ]

    overlay = labeler._topology_display_overlay(
        nodes,
        edges,
        info={"source_pod": "pod007"},
        source_anchors=["L1"],
    )

    virtual_nodes = [item for item in overlay["display_nodes"] if item["is_inferred"]]
    assert len(overlay["nodes"]) == 3
    assert len(virtual_nodes) == 1
    assert virtual_nodes[0]["topology_role"] == "SPINE"
    assert virtual_nodes[0]["pod_number"] == 7
    assert virtual_nodes[0]["annotation_selectable"] is False
    assert overlay["reconstruction"]["status"] == "partial_structural_reconstruction"
    assert overlay["reconstruction"]["exact_hidden_device_count_known"] is False
    assert len(overlay["reconstructed_paths"]) == 2
    assert {tuple(item["raw_edge_ids"]) for item in overlay["reconstructed_paths"]} == {
        ("RAW-1",),
        ("RAW-2",),
    }
    assert all(len(item["display_path"]) == 3 for item in overlay["reconstructed_paths"])
    assert {
        item["device_id"]: item["pod_number"] for item in overlay["nodes"]
    } == {"L1": 7, "C1": 7, "C2": 7}
    assert {
        frozenset((item["endpoint_a"], item["endpoint_b"]))
        for item in overlay["display_edges"]
    } == {
        frozenset(("C1", "C2")),
        frozenset(("L1", virtual_nodes[0]["device_id"])),
        frozenset(("C1", virtual_nodes[0]["device_id"])),
        frozenset(("C2", virtual_nodes[0]["device_id"])),
    }


def test_groups_parallel_cores_without_completing_unobserved_pairs(labeler):
    nodes = [
        {"device_id": "SRC", "name": "source-server", "topology_role": "SERVER"},
        {"device_id": "SL", "name": "source-pod01-leaf", "topology_role": "LEAF"},
        {"device_id": "SC1", "name": "source-core-1", "topology_role": "CORE"},
        {"device_id": "SC2", "name": "source-core-2", "topology_role": "CORE"},
        {"device_id": "DC1", "name": "sink-core-1", "topology_role": "CORE"},
        {"device_id": "DC2", "name": "sink-core-2", "topology_role": "CORE"},
        {"device_id": "DL", "name": "sink-pod02-leaf", "topology_role": "LEAF"},
        {"device_id": "DST", "name": "sink-server", "topology_role": "SERVER"},
    ]
    edges = [
        {"edge_id": "E-SRC", "endpoint_a": "SRC", "endpoint_b": "SL"},
        {"edge_id": "E-SC1", "endpoint_a": "SL", "endpoint_b": "SC1"},
        {"edge_id": "E-SC2", "endpoint_a": "SL", "endpoint_b": "SC2"},
        {"edge_id": "E-11", "endpoint_a": "SC1", "endpoint_b": "DC1"},
        {"edge_id": "E-12", "endpoint_a": "SC1", "endpoint_b": "DC2"},
        {"edge_id": "E-21", "endpoint_a": "SC2", "endpoint_b": "DC1"},
        {"edge_id": "E-DC1", "endpoint_a": "DC1", "endpoint_b": "DL"},
        {"edge_id": "E-DC2", "endpoint_a": "DC2", "endpoint_b": "DL"},
        {"edge_id": "E-DST", "endpoint_a": "DL", "endpoint_b": "DST"},
    ]

    overlay = labeler._topology_display_overlay(
        nodes,
        edges,
        source_anchors=["SRC", "SL"],
        sink_anchors=["DST", "DL"],
    )

    layers = overlay["core_forwarding_layers"]
    assert [item["device_ids"] for item in layers] == [
        ["SC1", "SC2"],
        ["DC1", "DC2"],
    ]
    assert [item["layer_role"] for item in layers] == ["source_core", "sink_core"]
    connection = overlay["core_layer_connections"][0]
    assert connection["possible_pair_count"] == 4
    assert connection["observed_pair_count"] == 3
    assert connection["inferred_candidate_pairs"] == []
    inferred = [
        item
        for item in overlay["display_edges"]
        if item.get("inference_kind") == "layered_core_candidate"
    ]
    assert inferred == []
    by_id = {item["device_id"]: item for item in overlay["display_nodes"]}
    assert by_id["SC1"]["core_forwarding_layer_index"] == 0
    assert by_id["DC2"]["core_forwarding_layer_index"] == 1


def test_reports_disconnected_core_fabrics_without_inferred_bridge(labeler):
    nodes = [
        {"device_id": "SRC", "name": "source-server", "topology_role": "SERVER"},
        {"device_id": "SC", "name": "source-core", "topology_role": "CORE"},
        {"device_id": "DC", "name": "sink-core", "topology_role": "CORE"},
        {"device_id": "DST", "name": "sink-server", "topology_role": "SERVER"},
    ]
    edges = [
        {"edge_id": "E-SRC", "endpoint_a": "SRC", "endpoint_b": "SC"},
        {"edge_id": "E-DST", "endpoint_a": "DC", "endpoint_b": "DST"},
    ]

    overlay = labeler._topology_display_overlay(
        nodes,
        edges,
        source_anchors=["SRC"],
        sink_anchors=["DST"],
    )

    layers = overlay["core_forwarding_layers"]
    assert [item["layer_role"] for item in layers] == ["source_core", "sink_core"]
    bridges = [
        item
        for item in overlay["display_edges"]
        if item.get("inference_kind") == "collapsed_core_stage_bridge"
    ]
    assert bridges == []
    assert overlay["reconstruction"]["virtual_node_count"] == 0
    assert overlay["reconstruction"]["core_forwarding_status"] == "disconnected_observed_only"
    assert overlay["reconstruction"]["status"] == "incomplete_observed_topology"
    assert "未生成推测 CORE 边" in overlay["reconstruction"]["warning"]


def test_reads_legacy_label_root_nodes(tmp_path, labeler):
    case_dir = tmp_path / "CASE_001"
    case_dir.mkdir()
    (case_dir / "label.json").write_text(
        json.dumps(
            [
                {
                    "ranking": 1,
                    "abnormal_node": [{"ip": "A"}, {"mgmt_ip": "B"}],
                }
            ]
        ),
        encoding="utf-8",
    )

    assert labeler._source_root_devices(case_dir) == ["A", "B"]


def test_parses_root_independent_hypothesis_graph(tmp_path, labeler):
    path = tmp_path / "hypotheses.json"
    path.write_text(
        json.dumps(
            [
                {
                    "case_id": "CASE_001",
                    "propagation": {
                        "hypothesis_graph": {
                            "schema_version": "hypothesis-graph-v1",
                            "graph_type": "root_independent_hypothetical_propagation_graph",
                            "nodes": [{"device_id": "A"}, {"device_id": "B"}],
                            "candidate_topology_edges": [
                                {"endpoint_a": "A", "endpoint_b": "B"}
                            ],
                            "edge_hypotheses": [
                                {
                                    "endpoint_a": "A",
                                    "endpoint_b": "B",
                                    "preferred_state": "A->B",
                                    "state_probabilities": {
                                        "endpoint_a_to_b": 0.7,
                                        "endpoint_b_to_a": 0.2,
                                        "no_direct_propagation": 0.1,
                                    },
                                    "directions": [
                                        {
                                            "from": "A",
                                            "to": "B",
                                            "relation": "physical_link",
                                            "evidence_ids": ["E1"],
                                            "state_probability": 0.7,
                                        }
                                    ],
                                }
                            ],
                            "evidence_map": {"E1": {"event_type": "physical_link_down"}},
                            "summary": {"root_independent": True},
                        }
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    parsed = labeler._hypothesis_map(path)["CASE_001"]

    assert parsed["graph_kind"] == "hypothesis_graph"
    assert parsed["summary"]["root_independent"] is True
    assert parsed["edge_hypotheses"][0]["preferred_state"] == "A->B"
    assert parsed["evidence_map"]["E1"]["event_type"] == "physical_link_down"


def test_legacy_selected_graph_is_available_as_hypothesis_view(tmp_path, labeler):
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            [
                {
                    "dir": "batch/CASE_001",
                    "selected_propagation_graph": {
                        "nodes": [{"device_id": "A"}, {"device_id": "B"}],
                        "edges": [{"from": "A", "to": "B"}],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    parsed = labeler._prediction_map(path)["CASE_001"]
    edge = parsed["edge_hypotheses"][0]

    assert parsed["graph_kind"] == "selected_propagation_graph"
    assert edge["state_probabilities"]["endpoint_a_to_b"] == 1.0
    assert edge["preferred_state"] == "A->B"


def test_ui_contains_hypothesis_views_and_fixed_inspector_tabs():
    ui_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "propagation_labeler"
        / "propagation_labeler_ui.html"
    )
    html = ui_path.read_text(encoding="utf-8")

    assert 'data-perspective="annotation"' in html
    assert 'data-perspective="hypothesis"' in html
    assert 'data-perspective="compare"' in html
    assert 'id="alarmTabPanel"' in html
    assert 'id="logTabPanel"' in html
    assert 'id="hypothesisTabPanel"' in html
    assert 'id="graphLayer"' in html
    assert 'id="layoutMode"' in html
    assert 'value="path" selected>CORE 转发级' in html
    assert 'value="ee">EE 事件演化' in html
    assert "function renderEventLayerGraph" in html
    assert "function renderEeEdgeInspector" in html
    assert ".inspector-body { flex: 1 1 auto; min-height: 0; overflow: auto;" in html
    assert 'data-interface-mode="simple"' in html
    assert 'data-interface-mode="full"' in html
    assert "body.simple-mode { overflow-x: auto; overflow-y: auto; }" in html
    assert "function labelRootIds()" in html
    assert "function appendDeviceStatusMarkers" in html
    assert "data-alarm-count" in html
    assert "touch-action: none; cursor: grab" in html
    assert "function handleGraphWheel" in html
    assert "function beginGraphPan" in html
    assert "function moveGraphPan" in html
    assert "function endGraphPan" in html
    assert "function displayTopologyMaps" in html
    assert "function layoutByPathLayers" in html
    assert "function shortestHopDistances" in html
    assert "function renderLayoutGuides" in html
    assert "function appendEndpointMarkers" in html
    assert "function reconstructedDisplayPath" in html
    assert "function renderInferredNodeInspector" in html
    assert "隐藏层节点只是结构推测" in html
    assert "function seedAlarmNodesInPlace" in html
    assert "告警节点→传播" in html
    assert "role:'propagation',membership:'possible'" in html
    assert "function refreshSimplePathRolesInPlace" in html
    assert "只标传播边" in html
    assert "传播节点后可以继续连边" in html
    assert "function isPropagationForeground" in html
    assert "background-cluster-label" in html
    assert "聚合未标注节点" in html
    assert "未标注节点（可点击）" in html
    assert "function topologyIncidentEdges" in html
    assert "function renderTopologyNeighbors" in html
    assert "图中已高亮该节点的连边" in html
    assert "function addTransitCore" in html
    assert "function removeManualTransitCore" in html
    assert "从此连接其他节点" in html


def test_parses_active_heterogeneous_m1_m2_m3_artifact(labeler):
    path = Path(__file__).resolve().parents[1] / "examples" / "demo_predictions.json"

    parsed = labeler._hypothesis_map(path)["DEMO_001"]

    assert parsed["graph_kind"] == "heterogeneous_propagation"
    assert {item["evidence_id"] for item in parsed["event_nodes"]} == {
        "DEMO-E1",
        "DEMO-E2",
        "DEMO-E3",
    }
    assert len(parsed["dd_relations"]) == 3
    assert len(parsed["ee_relations"]) == 3
    assert parsed["dd_relations"][0]["m3_selected_state"] == "10.0.0.1->10.0.0.2"
    assert parsed["ee_relations"][0]["m3_selected_state"] == "DEMO-E1->DEMO-E2"
    assert parsed["root_devices"] == ["10.0.0.1"]
    assert parsed["summary"]["heterogeneous"] is True


def test_save_is_atomic_and_revision_protected(tmp_path, labeler):
    data_root = tmp_path / "nodes"
    _write_case(data_root)
    labels_root = tmp_path / "labels"
    store = labeler.LabelingStore(data_root, labels_root, annotator="A01")
    bundle = store.case_bundle("CASE_001")
    label = bundle["label"]
    label.update(
        {
            "root_scope": "device",
            "root_devices": ["A"],
            "identifiability": "partially_identifiable",
            "nodes": [_node("A", "root"), _node("B")],
            "edges": [_edge("P1", "A", "B")],
        }
    )

    result = store.save_label(
        "CASE_001", label, base_revision=bundle["revision"]
    )
    path = labels_root / "CASE_001" / "propagation_label.json"

    assert path.exists()
    assert not list(path.parent.glob("*.tmp"))
    assert result["revision"] != "new"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == "heterogeneous-propagation-label-v1"
    assert saved["dd_edges"][0]["source"] == "A"
    assert saved["device_nodes"][0]["state"] == "definite"
    assert saved["annotation_metadata"]["annotator"] == "A01"
    assert saved["annotation_metadata"]["updated_at"]
    with pytest.raises(labeler.RevisionConflict):
        store.save_label("CASE_001", label, base_revision="new")


def test_validation_rejects_cycles_and_unknown_devices(labeler):
    label = labeler.default_label("CASE_001")
    label.update(
        {
            "root_scope": "device",
            "root_devices": ["A"],
            "nodes": [_node("A", "root"), _node("B")],
            "edges": [_edge("P1", "A", "B"), _edge("P2", "B", "A")],
        }
    )

    errors, warnings = labeler.validate_label(
        label,
        case_id="CASE_001",
        valid_device_ids={"A", "B"},
        topology_pairs={frozenset(("A", "B"))},
    )

    assert any("DAG" in error for error in errors)
    assert any("definite" in warning for warning in warnings)

    label["nodes"].append(_node("NOT_IN_TOPOLOGY"))
    errors, _ = labeler.validate_label(
        label,
        case_id="CASE_001",
        valid_device_ids={"A", "B"},
    )
    assert any("NOT_IN_TOPOLOGY" in error for error in errors)


def test_completed_edge_only_path_allows_propagation_node_to_continue(labeler):
    label = labeler.default_label("CASE_001")
    label.update(
        {
            "root_scope": "device",
            "root_devices": ["A"],
            "annotation_status": "completed",
            "nodes": [
                _node("A", "root"),
                _node("B", "propagation"),
                _node("C", "propagation"),
            ],
            "edges": [_edge("P1", "A", "B"), _edge("P2", "B", "C")],
        }
    )

    errors, _ = labeler.validate_label(
        label,
        case_id="CASE_001",
        valid_device_ids={"A", "B", "C"},
        topology_pairs={frozenset(("A", "B")), frozenset(("B", "C"))},
    )

    assert not errors


def test_completed_edge_only_path_rejects_component_unreachable_from_root(labeler):
    label = labeler.default_label("CASE_001")
    label.update(
        {
            "root_scope": "device",
            "root_devices": ["A"],
            "annotation_status": "completed",
            "nodes": [
                _node("A", "root"),
                _node("B", "propagation"),
                _node("C", "propagation"),
                _node("D", "propagation"),
            ],
            "edges": [_edge("P1", "A", "B"), _edge("P2", "D", "C")],
        }
    )

    errors, _ = labeler.validate_label(
        label,
        case_id="CASE_001",
        valid_device_ids={"A", "B", "C", "D"},
        topology_pairs={frozenset(("A", "B")), frozenset(("D", "C"))},
    )

    assert any("无法从根因节点到达" in error for error in errors)


def test_completed_observable_case_requires_a_node(labeler):
    label = labeler.default_label("CASE_001")
    label.update(
        {
            "root_scope": "uncertain",
            "identifiability": "identifiable",
            "annotation_status": "completed",
        }
    )

    errors, _ = labeler.validate_label(label, case_id="CASE_001")

    assert any("至少需要标注 1 个设备节点" in error for error in errors)


def test_dd_ee_negative_states_require_declared_complete_scope(labeler):
    label = labeler.default_label("CASE_001")
    dd = _edge("DD1", "A", "B")
    dd["membership"] = "explicit_no_direct"
    ee = _ee_edge("EE1", "E1", "E2")
    ee["state"] = "explicit_no_dependency"
    label.update(
        {
            "nodes": [_node("A"), _node("B")],
            "edges": [dd],
            "event_nodes": [_event("E1", "A"), _event("E2", "B")],
            "ee_edges": [ee],
        }
    )

    errors, _ = labeler.validate_label(
        label,
        case_id="CASE_001",
        valid_device_ids={"A", "B"},
        topology_pairs={frozenset(("A", "B"))},
        valid_event_ids={"E1", "E2"},
        event_devices={"E1": "A", "E2": "B"},
    )

    assert any("explicit_no_direct" in error for error in errors)
    assert any("explicit_no_dependency" in error for error in errors)

    label["annotation_complete_scope"].update(
        {"dd_candidate_pairs": True, "priority_ee_pairs": True}
    )
    errors, _ = labeler.validate_label(
        label,
        case_id="CASE_001",
        valid_device_ids={"A", "B"},
        topology_pairs={frozenset(("A", "B"))},
        valid_event_ids={"E1", "E2"},
        event_devices={"E1": "A", "E2": "B"},
    )

    assert not any("explicit_no" in error for error in errors)
