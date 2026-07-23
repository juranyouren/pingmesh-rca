import json

from scripts.build_evidence_tables import (
    build_device_task,
    parse_summary,
    prepare_summary_prompt,
)


class CharTokenizer:
    def encode(self, text):
        return list(text)


def _nodes():
    target = {
        "mgmt_ip": "10.0.0.1",
        "role": "LEAF",
        "linked_from": ["10.0.0.2"],
        "linked_to": ["10.0.0.3"],
        "alarms": [{"alarm_name": "TargetDown", "alarm_time": 100}],
        "logs": [],
    }
    upstream = {
        "mgmt_ip": "10.0.0.2",
        "role": "SPINE",
        "linked_from": [],
        "linked_to": ["10.0.0.1"],
        "alarms": [
            {"alarm_name": "HighAlarm", "description": "short"},
            {"alarm_name": "LowAlarm", "description": "x" * 6000},
        ],
        "logs": [],
    }
    downstream = {
        "mgmt_ip": "10.0.0.3",
        "role": "SERVER",
        "linked_from": ["10.0.0.1"],
        "linked_to": [],
        "alarms": [],
        "logs": [],
    }
    return target, upstream, downstream


def test_build_task_keeps_all_alarming_neighbors_and_relation():
    target, upstream, downstream = _nodes()
    task = build_device_task(
        case_id="case-a",
        dirpath="/case-a",
        node=target,
        node_by_ip={
            "10.0.0.1": target,
            "10.0.0.2": upstream,
            "10.0.0.3": downstream,
        },
        weights={"highalarm": 100, "lowalarm": 1},
    )

    assert task["neighbor_stats"] == {
        "total_neighbors": 2,
        "neighbors_with_alarms": 1,
        "neighbors_without_alarms": 1,
        "total_neighbor_alarms": 2,
    }
    assert task["neighbors"][0]["relation"] == "upstream"
    assert len(task["neighbors"][0]["alarms"]) == 2


def test_prompt_falls_back_to_highest_weight_alarm_when_full_context_is_too_long():
    target, upstream, downstream = _nodes()
    task = build_device_task(
        case_id="case-a",
        dirpath="/case-a",
        node=target,
        node_by_ip={
            "10.0.0.1": target,
            "10.0.0.2": upstream,
            "10.0.0.3": downstream,
        },
        weights={"highalarm": 100, "lowalarm": 1},
    )

    prompt, policy = prepare_summary_prompt(task, CharTokenizer(), 3000)

    assert policy["mode"] == "highest_weight_per_neighbor"
    assert "HighAlarm" in prompt
    assert "LowAlarm" not in prompt
    assert "100" not in json.dumps(policy)  # weights are not exposed via policy


def test_parse_summary_accepts_json_and_preserves_raw_fallback():
    assert parse_summary('{"summary":"目标与上游均有链路告警"}') == (
        "目标与上游均有链路告警",
        "json",
    )
    assert parse_summary("普通摘要") == ("普通摘要", "raw_fallback")


def test_parse_summary_uses_content_after_last_closing_think_tag():
    raw = (
        "这里是没有起始标签的思考过程。</think>\n"
        "<think>第二段思考</think>\n"
        '```json\n{"summary":"目标设备与上游邻居同时出现链路告警"}\n```'
    )

    assert parse_summary(raw) == (
        "目标设备与上游邻居同时出现链路告警",
        "json",
    )


def test_parse_summary_prefers_valid_json_before_after_think_fallback():
    raw = (
        '{"summary":"JSON 摘要优先"}\n'
        "额外思考内容</think>\n"
        "标签后的普通文本"
    )

    assert parse_summary(raw) == ("JSON 摘要优先", "json")


def test_parse_summary_falls_back_to_plain_text_after_think():
    raw = "模型思考过程，其中包含 {无效 JSON}。</think>\n最终的关联摘要"

    assert parse_summary(raw) == ("最终的关联摘要", "after_think")


def test_parse_summary_treats_malformed_json_after_think_as_plain_summary():
    raw = '推理内容</think>\n{"summary":"缺少结束引号}'

    assert parse_summary(raw) == (
        '{"summary":"缺少结束引号}',
        "after_think",
    )
