from Sys_v1.scoring import mean_enabled_scores, ranking_rows


def test_full_fusion_is_equal_weight_mean():
    combined, meta = mean_enabled_scores(
        {
            "topology": {"10.0.0.1": 1.0, "10.0.0.2": 0.2},
            "temporal": {"10.0.0.1": 0.4, "10.0.0.2": 1.0},
        },
        ["10.0.0.1", "10.0.0.2"],
    )

    assert combined == {"10.0.0.1": 0.7, "10.0.0.2": 0.6}
    assert meta["weights"] == {"topology": 0.5, "temporal": 0.5}
    assert [row["ip"] for row in ranking_rows(combined, {})] == ["10.0.0.1", "10.0.0.2"]


def test_component_ablation_uses_only_enabled_available_source():
    combined, meta = mean_enabled_scores(
        {"temporal": {"10.0.0.1": 0.3, "10.0.0.2": 0.8}},
        ["10.0.0.1", "10.0.0.2"],
    )

    assert combined == {"10.0.0.1": 0.3, "10.0.0.2": 0.8}
    assert meta["sources_used"] == ["temporal"]
    assert meta["weights"] == {"temporal": 1.0}


def test_zero_only_source_is_recorded_as_unavailable():
    combined, meta = mean_enabled_scores(
        {"temporal": {"10.0.0.1": 0.0}},
        ["10.0.0.1"],
    )

    assert combined == {"10.0.0.1": 0.0}
    assert meta["sources_used"] == ["temporal"]
    assert meta["sources_unavailable"] == []
    assert meta["zero_signal_sources"] == ["temporal"]
