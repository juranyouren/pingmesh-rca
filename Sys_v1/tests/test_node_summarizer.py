import json

from Sys_v1.RootCauseAnalyze.gate.node_summarizer import (
    build_per_device_prompt,
    summarize_devices,
)


def _device():
    return {
        "ip": "10.0.0.1",
        "role": "leaf",
        "cross": 2,
        "alarm_count": 2,
        "alarms": ["target-link-down", "target-packet-loss"],
        "high_weight_alarms": ["target-link-down"],
        "topology": {"upstream": ["10.0.0.2"], "downstream": []},
        "adjacent_alarm_context_policy": {"mode": "highest_weight"},
        "adjacent_alarm_context": [
            {
                "neighbor_ip": "10.0.0.2",
                "relation": "upstream",
                "selected_alarms": [{"name": "peer-interface-down", "weight": 100}],
                "total_alarm_count": 3,
            }
        ],
    }


def test_prompt_contains_target_neighbor_and_correlation_instruction():
    prompt = build_per_device_prompt(_device())

    assert "target-link-down" in prompt
    assert "10.0.0.2" in prompt
    assert "peer-interface-down" in prompt
    assert "目标设备自身告警与邻接设备告警" in prompt
    assert "不要把同时出现直接写成因果" in prompt


def test_prompt_context_is_bounded_by_dropping_low_priority_tail():
    device = _device()
    device["alarms"] = [f"target-alarm-{index}-" + "x" * 30 for index in range(100)]
    device["adjacent_alarm_context"] = [
        {
            "neighbor_ip": f"10.0.1.{index}",
            "selected_alarms": [{"name": "neighbor-" + "y" * 50, "weight": 100 - index}],
        }
        for index in range(30)
    ]

    prompt = build_per_device_prompt(device, max_chars=900)

    assert len(prompt) <= 900
    assert '"context_truncated":true' in prompt


def test_hybrid_summary_preserves_neighbor_facts_and_strips_reasoning():
    input_json = json.dumps({"devices": [_device()]}, ensure_ascii=False)
    output = summarize_devices(
        input_json,
        summarize_batch=lambda prompts: ["<think>hidden</think>目标与上游同时出现链路类告警。"],
    )
    record = json.loads(output.splitlines()[1])

    assert "hidden" not in output
    assert record["alarms_exact"] == _device()["alarms"]
    assert record["adjacent_alarm_context"] == _device()["adjacent_alarm_context"]
    assert record["semantic_summary"] == "目标与上游同时出现链路类告警。"
