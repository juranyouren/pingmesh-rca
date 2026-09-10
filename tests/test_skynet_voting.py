"""Hand-calculated voting and observational isolation acceptance tests."""

from copy import deepcopy

from Baseline.SkyNetVoting import SkyNetVoting, predict_root


def incident(events=None):
    return {
        "case_id": "three-device-hand-check", "group_id": "synthetic-group",
        "devices": [{"id": device, "type": "switch"} for device in ("C", "B", "A")],
        "physical_links": [{"u": "A", "v": "B"}, {"u": "B", "v": "C"}],
        "events": events if events is not None else [
            {"event_id": "e1", "device_id": "A", "source": "alarm", "event_type": "device_alarm"},
            {"event_id": "e2", "device_id": "B", "source": "alarm", "related_device_ids": ["A"]},
            {"event_id": "e3", "device_id": "C", "source": "alert", "link_endpoints": ["B", "C"]},
        ],
    }


def deterministic(prediction):
    prediction = deepcopy(prediction)
    prediction.pop("timing")
    return prediction


def test_three_devices_two_links_every_vote_matches_hand_calculation():
    prediction = predict_root(incident())
    assert prediction["status"] == "ok"
    assert prediction["root_ranking"] == [
        {"device_id": "A", "score": 2}, {"device_id": "B", "score": 2}, {"device_id": "C", "score": 1}
    ]
    assert {row["event_id"]: row["vote_device_ids"] for row in prediction["diagnostics"]["event_decisions"]} == {
        "e1": ["A"], "e2": ["A", "B"], "e3": ["B", "C"]
    }
    assert prediction["diagnostics"]["total_votes"] == 5
    assert prediction["diagnostics"]["top_score_tied"] is True
    assert prediction["diagnostics"]["tied_device_fraction"] == 2 / 3


def test_duplicate_id_and_signature_dedup_keep_real_distinct_events():
    alert = {"event_id": "same", "device_id": "A", "source": "alarm", "event_time": "2026-01-01T00:00:00Z"}
    no_id = {"device_id": "B", "source": "alarm", "event_time": "2026-01-01T00:00:00Z"}
    different_id = {**alert, "event_id": "distinct"}
    changed_label = {**no_id, "root_device": "B", "score": 1000}
    prediction = predict_root(incident([alert, deepcopy(alert), different_id, no_id, changed_label]))
    assert prediction["root_ranking"] == [
        {"device_id": "A", "score": 2}, {"device_id": "B", "score": 1}, {"device_id": "C", "score": 0}
    ]
    assert prediction["diagnostics"]["ignored_reason_counts"] == {"duplicate_event": 2}


def test_distinct_timestamps_without_ids_are_not_bucket_deduplicated():
    prediction = predict_root(incident([
        {"device_id": "A", "source": "alarm", "event_time": "2026-01-01T00:00:00.001Z"},
        {"device_id": "A", "source": "alarm", "event_time": "2026-01-01T00:00:00.002Z"},
    ]))
    assert prediction["root_ranking"][0]["score"] == 2


def test_physical_multiedges_and_repeated_attribution_cannot_duplicate_a_vote():
    case = incident([{"event_id": "one", "source": "alarm", "device_id": "B",
                      "related_device_ids": ["A", "A", "B"], "link_endpoints": ["B", "A"]}])
    case["physical_links"] += [{"u": "A", "v": "B"}, {"u": "B", "v": "A"}]
    prediction = predict_root(case)
    assert prediction["root_ranking"] == [
        {"device_id": "A", "score": 1}, {"device_id": "B", "score": 1}, {"device_id": "C", "score": 0}
    ]
    assert len(prediction["diagnostics"]["vote_evidence"]) == 2


def test_unknown_interface_and_nonadjacent_peer_do_not_expand_neighbors():
    prediction = predict_root(incident([{
        "event_id": "unresolved", "source": "alarm", "device_id": "A",
        "related_device_ids": ["C", "unknown-interface"], "link_endpoints": ["A", "C"],
        "message": "interface towards B failed",  # No free-text inference.
    }]))
    assert prediction["diagnostics"]["event_decisions"][0]["vote_device_ids"] == ["A"]
    assert {issue["reason"] for issue in prediction["diagnostics"]["event_decisions"][0]["mapping_issues"]} == {
        "related_device_not_physically_adjacent", "unknown_related_device", "link_endpoints_not_physically_connected"
    }


def test_explicit_link_endpoints_are_usable_without_an_owning_device():
    prediction = predict_root(incident([{"source": "alarm", "link_endpoints": ["B", "C"]}]))
    assert prediction["diagnostics"]["event_decisions"][0]["vote_device_ids"] == ["B", "C"]
    assert prediction["root_ranking"][-1] == {"device_id": "A", "score": 0}


def test_labels_and_precomputed_scores_do_not_affect_any_deterministic_output():
    case = incident()
    before = deepcopy(case)
    changed = deepcopy(case)
    changed.update(root_device="C", positive_edges=[["C", "B"]], groud_truth={"root": "C"},
                   endpoint_context={"true_root": "C", "p0_scores": {"C": 1000}})
    for device in changed["devices"]:
        device.update(root_label=True, probability=1.0)
    for event in changed["events"]:
        event.update(is_root=True, root_device="C", score=10000, propagation_cause="C")
    assert deterministic(predict_root(case)) == deterministic(predict_root(changed))
    assert case == before


def test_logs_disabled_and_no_votes_abstain_with_complete_candidate_domain():
    case = incident([{"event_id": "log", "device_id": "B", "source": "log"}])
    prediction = predict_root(case)
    assert prediction["status"] == "abstained"
    assert prediction["root_ranking"] == [{"device_id": device, "score": 0} for device in "ABC"]
    assert prediction["diagnostics"]["ignored_reason_counts"] == {"source_not_enabled": 1}
    extended = SkyNetVoting({"include_logs": True}).predict_root(case)
    assert extended["root_ranking"][0] == {"device_id": "B", "score": 1}
    assert "alerts+logs adapt" in extended["method"]


def test_one_hop_variant_expands_once_and_is_separately_named():
    case = incident([{"event_id": "e", "device_id": "A", "source": "alarm"}])
    prediction = SkyNetVoting({"mode": "one_hop"}).predict_root(case)
    assert prediction["method"] == "SkyNet-inspired one-hop voting"
    assert prediction["diagnostics"]["event_decisions"][0]["vote_device_ids"] == ["A", "B"]
    assert prediction["root_ranking"][-1] == {"device_id": "C", "score": 0}


def test_conflicting_duplicate_is_reported_and_first_observation_wins():
    prediction = predict_root(incident([
        {"event_id": "conflict", "device_id": "A", "source": "alarm"},
        {"event_id": "conflict", "device_id": "C", "source": "alarm"},
    ]))
    duplicate = prediction["diagnostics"]["event_decisions"][1]
    assert duplicate["conflicting_duplicate"] is True
    assert duplicate["duplicate_of_input_index"] == 0
    assert prediction["root_ranking"][0] == {"device_id": "A", "score": 1}


def test_no_candidates_is_input_ineligible():
    case = incident()
    case["devices"] = []
    prediction = predict_root(case)
    assert prediction["status"] == "input_ineligible"
    assert prediction["root_ranking"] == []
    assert prediction["diagnostics"]["reason"] == "no_candidate_devices"
