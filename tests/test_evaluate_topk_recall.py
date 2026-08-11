from scripts.evaluate_topk_recall import _combined_scores, _normalize_k_values, summarize_recall


def _ranking(*ips):
    return [{"rank": index, "ip": ip} for index, ip in enumerate(ips, 1)]


def test_combined_scores_use_equal_weighting():
    scores = _combined_scores(
        {"a": 1.0, "b": 0.2},
        {"a": 0.0, "b": 0.8},
        ["a", "b"],
    )

    assert scores == {"a": 0.5, "b": 0.5}


def test_recall_summary_compares_both_full_device_rankings():
    records = [
        {
            "ground_truth_ips": ["a"],
            "pagerank_ranking": _ranking("a", "b", "c", "d", "e", "f", "g"),
            "pagerank_temporal_ranking": _ranking(
                "b", "a", "c", "d", "e", "f", "g"
            ),
        },
        {
            "ground_truth_ips": ["g"],
            "pagerank_ranking": _ranking("a", "b", "c", "d", "e", "f", "g"),
            "pagerank_temporal_ranking": _ranking(
                "a", "g", "b", "c", "d", "e", "f"
            ),
        },
    ]

    summary = summarize_recall(records, [5, 7])

    assert summary["strategies"]["pagerank"]["5"]["recall"] == 0.5
    assert summary["strategies"]["pagerank"]["7"]["recall"] == 1.0
    assert summary["strategies"]["pagerank+temporal"]["5"]["recall"] == 1.0
    assert summary["strategies"]["pagerank+temporal"]["7"]["recall"] == 1.0


def test_k_values_are_positive_unique_and_sorted():
    assert _normalize_k_values([10, 5, 7, 5]) == [5, 7, 10]
