import json
import unittest

from Sys.RootCauseAnalyze.gate.node_summarizer import (
    build_per_device_prompt,
    summarize_devices,
    summarize_nodes_with,
)


class NodeSummarizerTest(unittest.TestCase):
    def test_per_device_prompt_is_small(self):
        """Single device prompt should be ~200-600 chars, well under any model limit."""
        device = {
            "ip": "10.0.0.1",
            "role": "leaf",
            "cross": 3,
            "alarm_count": 2,
            "alarms": ["trunkdown", "bgp_down"],
            "high_severity_alarms": ["trunkdown"],
            "topology": {"upstream": ["10.0.0.2"], "downstream": ["10.0.0.3"]},
        }
        prompt = build_per_device_prompt(device)
        self.assertIn("10.0.0.1", prompt)
        self.assertIn("trunkdown", prompt)
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


if __name__ == "__main__":
    unittest.main()
