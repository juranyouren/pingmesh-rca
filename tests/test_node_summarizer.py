import json
import unittest

from Sys.RootCauseAnalyze.gate.node_summarizer import (
    MultiCardSummarizer,
    VllmNodeSummarizer,
    build_per_device_prompt,
    strip_reasoning_content,
    summarize_devices,
    summarize_nodes_with,
)


class NodeSummarizerTest(unittest.TestCase):
    def test_multicard_configuration_requires_process_isolation(self):
        with self.assertRaisesRegex(ValueError, "exactly one NPU card"):
            MultiCardSummarizer(model_path="unused", npu_cards="0,1")

    def test_per_device_prompt_is_small(self):
        """Single device prompt should be ~200-600 chars, well under any model limit."""
        device = {
            "ip": "10.0.0.1",
            "role": "leaf",
            "cross": 3,
            "alarm_count": 2,
            "alarms": ["trunkdown", "bgp_down"],
            "high_weight_alarms": ["trunkdown"],
            "topology": {"upstream": ["10.0.0.2"], "downstream": ["10.0.0.3"]},
        }
        prompt = build_per_device_prompt(device)
        self.assertIn("10.0.0.1", prompt)
        self.assertIn("trunkdown", prompt)
        self.assertIn("不是根因分析器", prompt)
        self.assertIn("禁止判断该设备是否为根因", prompt)
        self.assertIn("结构化事实会由程序原样保留", prompt)
        self.assertIn("不要展示思考过程", prompt)
        self.assertNotIn("whether this device looks like a root cause", prompt)
        # Should fit in 2000 chars (safe for max_model_len=2048)
        self.assertLess(len(prompt), 2000)

    def test_summarize_devices_one_at_a_time(self):
        """Each device is sent as a separate inference call."""
        devices_json = json.dumps({
            "devices": [
                {"ip": "10.0.0.1", "role": "leaf", "cross": 3, "alarms": ["trunkdown"]},
                {"ip": "10.0.0.2", "role": "spine", "cross": 1, "alarms": ["bgp_down"]},
            ]
        }, ensure_ascii=False)

        seen_prompts = []

        def fake_model(prompts):
            seen_prompts.extend(prompts)
            return [f"summary of {json.loads(p)['ip']}" if 'ip' in json.loads(p.get('device_json','{}') or '{}') else "?" for p in prompts]

        # Actually, fake_model receives list of prompt strings
        def fake_batch(prompts):
            seen_prompts.extend(prompts)
            results = []
            for p in prompts:
                try:
                    d = json.loads(json.loads(p.split("Device JSON:\n")[1]) if "Device JSON:" in p else "{}")
                    ip = d.get("ip", "?")
                except Exception:
                    ip = "?"
                results.append(f"summary of {ip}")
            return results

        result = summarize_devices(devices_json, summarize_batch=fake_batch)

        self.assertEqual(len(seen_prompts), 2)
        self.assertIn("10.0.0.1", result)
        self.assertIn("10.0.0.2", result)
        self.assertIn("lossless facts + semantic annotation", result)

    def test_handles_empty_devices(self):
        result = summarize_devices('{"devices": []}', summarize_batch=lambda x: [])
        self.assertEqual(result, '{"devices": []}')

    def test_handles_non_json_input(self):
        result = summarize_devices("garbled", summarize_batch=lambda x: [])
        self.assertEqual(result, "garbled")

    def test_summarize_nodes_with_compat(self):
        """summarize_nodes_with still works with old signature."""
        devices_json = json.dumps({
            "devices": [{"ip": "10.0.0.1", "role": "leaf", "alarms": ["trunkdown"]}]
        }, ensure_ascii=False)

        def fake_batch(prompts):
            return ["leaf device 10.0.0.1 with trunkdown"]

        result = summarize_nodes_with(devices_json, summarize_batch=fake_batch)
        self.assertIn("10.0.0.1", result)
        self.assertIn("trunkdown", result)
        self.assertIn("Device evidence records", result)
        self.assertIn('"alarms_exact":["trunkdown"]', result)
        self.assertIn('"semantic_summary":"leaf device 10.0.0.1 with trunkdown"', result)

    def test_exact_facts_survive_even_when_model_omits_them(self):
        devices_json = json.dumps({
            "devices": [{
                "ip": "10.0.0.1",
                "role": "leaf",
                "cross": 3,
                "alarm_count": 2,
                "alarms": ["trunkdown", "bgp_down"],
                "high_weight_alarms": ["trunkdown"],
                "topology": {
                    "upstream": ["10.0.0.2"],
                    "downstream": ["10.0.0.3"],
                },
            }]
        }, ensure_ascii=False)

        result = summarize_devices(
            devices_json,
            summarize_batch=lambda _prompts: ["观察到链路及路由会话异常。"],
        )
        record = json.loads(result.split("\n", 1)[1])

        self.assertEqual(record["ip"], "10.0.0.1")
        self.assertEqual(record["alarms_exact"], ["trunkdown", "bgp_down"])
        self.assertEqual(record["high_weight_alarms"], ["trunkdown"])
        self.assertEqual(record["upstream"], ["10.0.0.2"])
        self.assertEqual(record["semantic_summary"], "观察到链路及路由会话异常。")

    def test_summary_engine_defaults_to_parallel_sequences(self):
        summarizer = VllmNodeSummarizer(model_path="unused", npu_cards="0")
        self.assertEqual(summarizer.max_num_seqs, 8)
        with self.assertRaisesRegex(ValueError, "max_num_seqs must be positive"):
            VllmNodeSummarizer(model_path="unused", npu_cards="0", max_num_seqs=0)

    def test_strips_think_content_before_building_summary(self):
        devices_json = json.dumps({
            "devices": [{"ip": "10.0.0.1", "role": "leaf"}]
        })

        result = summarize_devices(
            devices_json,
            summarize_batch=lambda _prompts: [
                "<think>long private reasoning that must not be cached</think>"
                "10.0.0.1 是 leaf 设备。"
            ],
        )

        self.assertNotIn("<think>", result)
        self.assertNotIn("private reasoning", result)
        self.assertIn("10.0.0.1 是 leaf 设备", result)

    def test_strips_unclosed_reasoning_block(self):
        self.assertEqual(strip_reasoning_content("<think>unfinished reasoning"), "")


if __name__ == "__main__":
    unittest.main()
