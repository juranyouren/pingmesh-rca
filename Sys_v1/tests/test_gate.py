from Sys_v1.gate import assess_confidence


def _ranking(first=0.9, second=0.5):
    return [
        {"rank": 1, "ip": "10.0.0.1", "combined_score": first},
        {"rank": 2, "ip": "10.0.0.2", "combined_score": second},
    ]


def test_single_source_large_margin_is_accepted():
    gate = assess_confidence(
        _ranking(),
        {"topology": {"10.0.0.1": 0.9, "10.0.0.2": 0.5}},
        single_source_accept_margin=0.15,
    )

    assert gate["action"] == "accept"
    assert gate["reason"] == "single_source_large_margin"


def test_single_source_low_margin_routes_to_llm():
    gate = assess_confidence(
        _ranking(0.55, 0.5),
        {"temporal": {"10.0.0.1": 0.55, "10.0.0.2": 0.5}},
        single_source_accept_margin=0.15,
    )

    assert gate["action"] == "llm_review"
    assert gate["reason"] == "single_source_low_margin"


def test_two_source_top1_conflict_routes_to_llm():
    gate = assess_confidence(
        _ranking(),
        {
            "topology": {"10.0.0.1": 1.0, "10.0.0.2": 0.4},
            "temporal": {"10.0.0.1": 0.3, "10.0.0.2": 1.0},
        },
    )

    assert gate["action"] == "llm_review"
    assert gate["reason"] == "score_source_top1_conflict"


def test_no_usable_scores_routes_to_operator():
    gate = assess_confidence([], {"temporal": {"10.0.0.1": 0.0}})

    assert gate["action"] == "operator_review"
    assert gate["decision_state"] == "insufficient"
