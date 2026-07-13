from datetime import datetime

from scripts.stat_focus_device_evidence import (
    device_evidence_stats,
    event_bucket,
    markdown_summary,
    percentile,
    parse_args,
    rank_nodes_by_event_volume,
    timestamped_output_dir,
    aggregate_report,
)


def test_device_evidence_stats_counts_both_sources_without_exposing_text():
    node = {
        "alarms": [
            {"name": "linkDown", "description": "abcd"},
            {"alarm_name": "linkDown", "description": "xy"},
        ],
        "logs": [{"name": "bgpDown", "message": "123456"}],
    }
    stats = device_evidence_stats(node, chars_per_token=4)
    assert stats == {
        "alarm_count": 2,
        "log_count": 1,
        "event_count": 3,
        "distinct_event_type_count": 2,
        "description_chars": 12,
        "estimated_tokens": 3,
    }
    assert "abcd" not in str(stats)


def test_percentile_and_buckets_are_stable():
    assert percentile([0, 10], 0.95) == 9.5
    assert [event_bucket(n) for n in (0, 1, 10, 50, 100, 500)] == [
        "0", "1-9", "10-49", "50-99", "100-499", "500+"
    ]


def test_rank_nodes_by_event_volume_uses_total_then_stable_ties():
    nodes = [
        {"mgmt_ip": "10.0.0.3", "alarms": [{}], "logs": [{}]},
        {"mgmt_ip": "10.0.0.2", "alarms": [{}, {}], "logs": []},
        {"mgmt_ip": "10.0.0.1", "alarms": [{}], "logs": [{}, {}]},
    ]
    assert rank_nodes_by_event_volume(nodes, 2) == ["10.0.0.1", "10.0.0.2"]


def test_timestamped_output_dir_has_stable_format():
    output = timestamped_output_dir(datetime(2026, 7, 13, 16, 5, 9))
    assert output.as_posix() == "data/res/focus_device_evidence_20260713_160509"


def test_cli_defaults_match_full_dataset_and_top5():
    args = parse_args([])
    assert args.data_root.as_posix() == "data/node/nodes_max_labeled"
    assert args.top_k == 5
    assert args.output_dir is None


def test_report_and_markdown_warn_against_overclaim():
    metrics_a = dict(alarm_count=2, log_count=1, event_count=3, distinct_event_type_count=2,
                     description_chars=12, estimated_tokens=3)
    metrics_b = dict(alarm_count=0, log_count=0, event_count=0, distinct_event_type_count=0,
                     description_chars=0, estimated_tokens=0)
    rows = [
        dict(case_id="case_x", device_id="device_a", role="LEAF", is_focused=True,
             focus_rank=1, event_volume_bucket="1-9", **metrics_a),
        dict(case_id="case_x", device_id="device_b", role="SPINE", is_focused=False,
             focus_rank="", event_volume_bucket="0", **metrics_b),
    ]
    case = {"case_id": "case_x", "all_device_count": 2, "focused_device_count": 1,
            "device_reduction_ratio": 0.5}
    for metric in metrics_a:
        case[f"all_{metric}"] = metrics_a[metric]
        case[f"focused_{metric}"] = metrics_a[metric]
        case[f"{metric}_reduction_ratio"] = 0.0
    report = aggregate_report(
        rows, [case], {"top_k": 1, "chars_per_token": 4, "large_event_threshold": 10}, []
    )
    text = markdown_summary(report)
    assert report["focused_device_statistics"]["event_count"]["median"] == 3
    assert "数据不支持“每一个设备都有大量告警”的绝对表述" in text
