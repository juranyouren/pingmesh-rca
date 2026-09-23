import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Sys.LLM.engine import ContextBudgetError, parse_json
from Sys.Preprocess.evidence.encoder import EvidenceEncoder
from Sys.Preprocess.llm_encoder import run_case


class FakeEngine:
    def __init__(self, unknown=False, malformed=False, split=False):
        self.calls = []
        self.unknown, self.malformed, self.split = unknown, malformed, split

    def generate_json(self, prompt):
        self.calls.append(prompt)
        data = json.loads(prompt.split("DATA_JSON=", 1)[1])
        if "unknown_events" in data:
            return {"concepts": [{"name": "vendor_transition", "description": "Vendor transition",
                    "raw_event_ids": [r["raw_event_id"] for r in data["unknown_events"]],
                    "entity_types": ["interface"], "states": ["up"], "possible_effects": []}]}
        if self.split and len(data["records"]) > 1:
            raise ContextBudgetError("too large")
        if self.malformed:
            return {"mappings": [{"raw_event_id": "invented", "predicate": "device_restart"}]}
        return {"mappings": [{"raw_event_id": r["raw_event_id"],
                "predicate": "UNKNOWN" if self.unknown else "interface_state_change",
                "entity": {"entity_type": "interface", "local_name": "AggregatePort 5"},
                "value": {"state": "up"}, "mapping_confidence": 0.9,
                "semantic_summary": "Interface became up"} for r in data["records"]]}


class BatchEngine:
    """Records how prompts are grouped into engine calls; fails named devices."""

    def __init__(self, fail_devices=()):
        self.chunks = []
        self.fail_devices = set(fail_devices)

    def generate_json_batch(self, prompts):
        self.chunks.append(len(prompts))
        outcomes = []
        for prompt in prompts:
            # The malformed-output retry appends its nudge after the payload, so parse
            # the leading object and ignore trailing instruction text.
            data, _ = json.JSONDecoder().raw_decode(prompt.split("DATA_JSON=", 1)[1].lstrip())
            if "unknown_events" in data:
                outcomes.append({"concepts": []})
            elif data["device"]["device_id"] in self.fail_devices:
                outcomes.append(ValueError("unusable response"))
            else:
                outcomes.append({"mappings": [{"raw_event_id": r["raw_event_id"],
                        "predicate": "interface_state_change",
                        "entity": {"entity_type": "interface", "local_name": "AggregatePort 5"},
                        "value": {"state": "up"}, "mapping_confidence": 0.9} for r in data["records"]]})
        return outcomes


def node(ip="28.219.131.16"):
    return {"mgmt_ip": ip, "logs": [{"alarm_name": "LINEPROTO_5_UPDOWN", "source": "Ruijie",
            "description": "Interface AggregatePort 5, changed state to up.", "alarm_time": 1786068493156}],
            "alarms": [{"alarm_name": "linkflap", "source": "HCSO",
            "description": "Interface AggregatePort 5, changed state to up.", "alarm_time": 1786068493156}]}


class EncoderTests(unittest.TestCase):
    def test_dedup_recovery_provenance_and_scope(self):
        engine = FakeEngine()
        result = EvidenceEncoder(engine).encode_incident("8294294", [node(), node("another")])
        self.assertEqual(len(engine.calls), 2)
        self.assertEqual(result["status"], "completed")
        a, b = [d["evidence"][0] for d in result["devices"]]
        self.assertEqual(a["source_count"], 2)
        self.assertEqual(a["provenance"]["source_type"], "multi_source")
        self.assertIn("path_recovery", a["possible_effects"])
        self.assertNotIn("path_degradation", a["possible_effects"])
        self.assertNotEqual(a["entity"]["scoped_id"], b["entity"]["scoped_id"])
        self.assertIsNone(a["time"]["canonical_time"])
        self.assertEqual(len(result["evidence_graph"]["edges"]), 2)

    def test_unknown_one_aggregate_call_and_incident_isolation(self):
        engine = FakeEngine(unknown=True)
        encoder = EvidenceEncoder(engine)
        original = copy.deepcopy(encoder.vocabulary)
        first = encoder.encode_incident("one", [node(), node("another")])
        self.assertEqual(len(engine.calls), 3)
        self.assertEqual(len(first["incident_vocabulary"]), 1)
        self.assertEqual(first["candidate_vocabulary"][0]["review_status"], "pending")
        self.assertEqual(first["devices"][0]["unknown_events"], [])
        second = encoder.encode_incident("two", [node()])
        self.assertNotEqual(first["incident_vocabulary"], second["incident_vocabulary"])
        self.assertEqual(encoder.vocabulary, original)

    def test_bad_ids_are_not_evidence_and_records_are_retained(self):
        result = EvidenceEncoder(FakeEngine(malformed=True)).encode_incident("i", [node()])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["devices"][0]["unknown_events"]), 2)
        self.assertEqual(len(result["raw_records"]), 2)
        self.assertEqual(result["devices"][0]["evidence"], [])

    def test_different_or_missing_times_not_merged(self):
        for time in (123, None):
            n = node()
            n["logs"][0]["alarm_time"] = time
            result = EvidenceEncoder(FakeEngine()).encode_incident("i", [n])
            self.assertEqual(len(result["devices"][0]["evidence"]), 2)

    def test_context_split_keeps_every_record(self):
        result = EvidenceEncoder(FakeEngine(split=True)).encode_incident("i", [node()])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["devices"][0]["evidence"][0]["source_count"], 2)

    def test_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "case"
            case.mkdir()
            (case / "nodes.json").write_text(json.dumps([node()]), encoding="utf-8")
            output = Path(tmp) / "output"
            self.assertEqual(run_case(EvidenceEncoder(FakeEngine()), case, output), "completed")
            saved = json.loads((output / "case" / "incident.json").read_text(encoding="utf-8"))
            self.assertEqual(len(saved["raw_records"]), 2)
            self.assertTrue((output / "case" / "candidate_vocabulary.json").exists())

    def test_json_reasoning_and_invalid(self):
        self.assertEqual(parse_json('<think>reason</think>```json\n{"mappings": []}\n```'), {"mappings": []})
        with self.assertRaises(ValueError):
            parse_json('{"mappings":')

    def test_singleton(self):
        from Sys.LLM import engine
        with patch.object(engine, "_engine", None), patch.object(engine, "NpuEngine") as factory:
            self.assertIs(engine.get_shared_engine(), engine.get_shared_engine())
            factory.assert_called_once()

    def test_malformed_predicate_and_ungrounded_entity(self):
        for invalid in ({"predicate": []}, {"entity": {"entity_type": "interface", "local_name": "invented"}}):
            fake = FakeEngine()
            original = fake.generate_json

            def generate(prompt):
                response = original(prompt)
                for mapping in response.get("mappings", []):
                    mapping.update(invalid)
                return response

            fake.generate_json = generate
            result = EvidenceEncoder(fake).encode_incident("i", [node()])
            # Invalid entities cannot be rescued by concept induction either.
            if "entity" in invalid:
                self.assertEqual(result["devices"][0]["evidence"], [])
            self.assertEqual(len(result["raw_records"]), 2)

    def test_empty_device_and_stable_ids(self):
        encoder = EvidenceEncoder(FakeEngine())
        first = encoder.encode_incident("i", [node()])
        second = encoder.encode_incident("i", [node()])
        self.assertEqual(first, second)
        empty = encoder.encode_incident("i", [{"mgmt_ip": "empty"}])
        self.assertEqual(empty["devices"][0]["evidence"], [])

    def test_npu_adapter_reuses_model_and_base_model_prompt(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from Sys.LLM.engine import NpuEngine
        tokenizer = MagicMock()
        tokenizer.chat_template = None
        tokenizer.encode.return_value = [1, 2]
        llm = MagicMock()
        llm.get_tokenizer.return_value = tokenizer
        llm.generate.return_value = [SimpleNamespace(outputs=[SimpleNamespace(text='{"mappings": []}')])]
        vllm = SimpleNamespace(LLM=MagicMock(return_value=llm), SamplingParams=MagicMock())
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "PINGMESH_MODEL_PATH": tmp, "PINGMESH_NPU_CARDS": "0,1",
            "PINGMESH_MAX_TOKENS": "50", "PINGMESH_MAX_MODEL_LEN": "1000"
        }), patch.dict("sys.modules", {"vllm": vllm}):
            engine = NpuEngine()
            engine.generate_json("test")
            engine.generate_json("test again")
            vllm.LLM.assert_called_once()
            self.assertEqual(vllm.LLM.call_args.kwargs["tensor_parallel_size"], 2)
            self.assertEqual(llm.generate.call_count, 2)
            tokenizer.encode.return_value = list(range(951))
            with self.assertRaises(ContextBudgetError):
                engine.generate_json("too long")


class PipelineTests(unittest.TestCase):
    def test_adapter_preserves_identity_and_untrusted_time(self):
        from Sys.Preprocess.evidence.adapter import to_episodes
        result = EvidenceEncoder(FakeEngine()).encode_incident("i", [node()])
        episode = to_episodes(result)[0]
        self.assertEqual(episode["duplicate_count"], 2)
        self.assertEqual(episode["lifecycle"], "clear")
        self.assertIsNone(episode["onset_interval_ms"])
        self.assertEqual(episode["peer_device"], "")
        self.assertEqual(episode["evidence_id"], result["devices"][0]["evidence"][0]["evidence_id"])

    def test_full_workflow_with_metrics_and_actual_llm_evidence(self):
        from Sys.Score.llm_encoder_experiment import build_parser, run
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            args = build_parser().parse_args(["--smoke", "--compare-rules", "--output", str(output)])
            self.assertEqual(run(args), 0)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["mode"], "synthetic_smoke")
            self.assertEqual(summary["encoding"]["mapped_observations"], 6)
            for variant in ("llm_encoder", "rules"):
                self.assertEqual(summary["variants"][variant]["failed_cases"], 0)
                self.assertEqual(summary["variants"][variant]["root"]["Total Evaluated Cases"], 2)
                self.assertEqual(summary["variants"][variant]["propagation_labeled_cases"], 2)
                self.assertIn("macro_directed_edge_f1", summary["variants"][variant]["path_metrics"])
            episodes = json.loads((output / "llm_encoder" / "evidence_episodes.json").read_text(encoding="utf-8"))
            self.assertTrue(all(e["parse_method"] == "llm_encoder" for row in episodes for e in row["episodes"]))
            paths = json.loads((output / "llm_encoder" / "selected_propagation_paths.json").read_text(encoding="utf-8"))
            episode_ids = {e["evidence_id"] for row in episodes for e in row["episodes"]}
            graph_ids = {eid for row in paths for edge in row["selected_propagation_graph"]["edges"] for eid in edge["evidence_ids"]}
            self.assertTrue(graph_ids)
            self.assertLessEqual(graph_ids, episode_ids)
            with self.assertRaisesRegex(ValueError, "new or empty"):
                run(args)

    def test_stale_or_missing_evidence_does_not_fallback_to_rules(self):
        from Sys.Preprocess.evidence.adapter import load_episodes
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / "i"
            case.mkdir()
            nodes = [node()]
            (case / "nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
            run_case(EvidenceEncoder(FakeEngine()), case, root / "evidence")
            episodes, _ = load_episodes(root / "evidence", "i", nodes)
            self.assertEqual(len(episodes), 1)
            nodes[0]["logs"][0]["description"] = "changed input"
            with self.assertRaisesRegex(ValueError, "stale"):
                load_episodes(root / "evidence", "i", nodes)
            with self.assertRaises(FileNotFoundError):
                load_episodes(root / "missing", "i", nodes)

    def test_metrics_include_failed_cases_and_missing_labels_are_null(self):
        from Sys.Score.llm_encoder_experiment import evaluate
        from Sys.Preprocess.llm_encoder import write_json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / "case"
            case.mkdir()
            predictions = root / "res.json"
            write_json(predictions, [{"dir": str(case), "error": "failed", "root_ips": []}])
            result = evaluate(predictions)
            self.assertIsNone(result["root"])
            self.assertIsNone(result["path_metrics"])
            write_json(case / "label.json", [{"ranking": 1, "abnormal_node": [{"ip": "10.0.0.1"}]}])
            write_json(case / "propagation_label.json", {"root_scope": "device", "root_devices": ["10.0.0.1"], "edges": []})
            result = evaluate(predictions)
            self.assertEqual(result["failed_cases"], 1)
            self.assertEqual(result["root"]["Total Evaluated Cases"], 1)
            self.assertEqual(result["root"]["Top-1 Acc (%)"], 0)
            self.assertEqual(result["path_metrics"]["macro_directed_edge_f1"], 0)

    def test_encoder_not_called_when_raw_topology_missing(self):
        from Sys.Score.llm_encoder_experiment import build_parser, run
        from Sys.Preprocess.evidence.smoke import create_cases, SmokeEngine
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_cases(root / "data")
            (root / "data" / "smoke_1" / "topology_context.json").unlink()
            args = build_parser().parse_args(["--data", str(root / "data"), "--output", str(root / "run")])
            # Preflight dependencies are isolated; topology must fail before any inference.
            from unittest.mock import MagicMock
            with patch.dict("sys.modules", {"networkx": MagicMock(), "scipy": MagicMock()}):
                with self.assertRaisesRegex(ValueError, "Raw topology missing"):
                    run(args, engine=SmokeEngine())

    def test_partial_unknown_never_reappears_as_rule_evidence(self):
        from Sys.Preprocess.evidence.smoke import create_cases, SmokeEngine
        from Sys.Preprocess.llm_encoder import write_json
        from Sys.RootCauseAnalyze.propagation_pipeline import run_propagation_pipeline
        from Sys.utils.case_utils import load_case_nodes
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_cases(root / "data")
            case = root / "data" / "smoke_1"
            nodes = load_case_nodes(str(case))
            for n in nodes:
                for event in n.get("alarms", []) + n.get("logs", []):
                    event["description"] = "vendor text not recognized"
            write_json(case / "nodes.json", nodes)
            run_case(EvidenceEncoder(SmokeEngine()), case, root / "evidence")
            result = run_propagation_pipeline(str(root / "data"), str(root / "prediction"),
                        evidence_dir=str(root / "evidence"), selected_case_dirs=[str(case)])
            records = json.loads(Path(result).read_text(encoding="utf-8"))
            self.assertNotIn("error", records[0])
            self.assertEqual(records[0]["encoder_status"], "partial")
            actual = json.loads((root / "prediction" / "evidence_episodes.json").read_text(encoding="utf-8"))
            self.assertEqual(actual[0]["episodes"], [])


class BatchEncodingTests(unittest.TestCase):
    def test_devices_with_records_share_one_engine_call(self):
        engine = BatchEngine()
        result = EvidenceEncoder(engine).encode_incident("i", [node(), node("a"), node("b"), {"mgmt_ip": "ctx"}])
        # Three devices carry records and share a single batched call; the context-only
        # device is never sent.
        self.assertEqual(engine.chunks, [3])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["devices"]), 4)

    def test_malformed_slot_is_retried_alone_and_does_not_cost_the_batch(self):
        engine = BatchEngine(fail_devices={"a"})
        result = EvidenceEncoder(engine).encode_incident("i", [node(), node("a")])
        # First pass batches both; only the bad slot is retried, still failing, and the
        # two unresolved observations then trigger one incident-level aggregation call.
        self.assertEqual(engine.chunks, [2, 1, 1])
        healthy, broken = result["devices"]
        self.assertEqual(healthy["device"]["device_id"], "28.219.131.16")
        self.assertTrue(healthy["evidence"])
        self.assertEqual(broken["device"]["device_id"], "a")
        self.assertEqual(broken["evidence"], [])
        # The failed device keeps its observations as UNKNOWN rather than losing them.
        self.assertEqual(len(broken["unknown_events"]), 2)
        self.assertEqual(result["status"], "partial")

    def test_no_aggregation_call_when_everything_maps(self):
        engine = BatchEngine()
        encode = EvidenceEncoder(engine)
        encode.encode_incident("i", [node()])
        self.assertEqual(engine.chunks, [1])
        self.assertEqual(encode.last_stats["llm_calls"], 1)

    def test_engine_batch_size_chunks_calls(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from Sys.LLM.engine import NpuEngine
        tokenizer = MagicMock()
        tokenizer.chat_template = None
        tokenizer.encode.return_value = [1, 2]
        llm = MagicMock()
        llm.get_tokenizer.return_value = tokenizer
        llm.generate.return_value = [SimpleNamespace(outputs=[SimpleNamespace(text='{"a": 1}')]) for _ in range(2)]
        vllm = SimpleNamespace(LLM=MagicMock(return_value=llm), SamplingParams=MagicMock())
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "PINGMESH_MODEL_PATH": tmp, "PINGMESH_NPU_CARDS": "0",
            "PINGMESH_MAX_TOKENS": "50", "PINGMESH_MAX_MODEL_LEN": "1000",
            "PINGMESH_BATCH_SIZE": "2",
        }), patch.dict("sys.modules", {"vllm": vllm}):
            engine = NpuEngine()
            self.assertEqual(engine.batch_size, 2)
            self.assertEqual(len(engine.generate_json_batch(["a", "b", "c"])), 3)
            # Three prompts at batch size 2 mean two engine calls: 2 then 1.
            self.assertEqual(llm.generate.call_count, 2)
            self.assertEqual([len(call.args[0]) for call in llm.generate.call_args_list], [2, 1])
            with patch.dict("os.environ", {"PINGMESH_BATCH_SIZE": "0"}):
                with self.assertRaises(ValueError):
                    NpuEngine()

    def test_reasoning_tokens_are_separated_from_the_answer(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from Sys.LLM.engine import NpuEngine
        reasoning = "<think>weighing the vendor alarm text</think>"
        answer = '{"mappings": []}'
        tokenizer = MagicMock()
        tokenizer.chat_template = None
        # One token per character, so lengths are directly comparable.
        tokenizer.encode.side_effect = lambda text: [0] * len(text)
        llm = MagicMock()
        llm.get_tokenizer.return_value = tokenizer
        llm.generate.return_value = [SimpleNamespace(
            outputs=[SimpleNamespace(text=reasoning + answer, finish_reason="stop")])]
        vllm = SimpleNamespace(LLM=MagicMock(return_value=llm), SamplingParams=MagicMock())
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "PINGMESH_MODEL_PATH": tmp, "PINGMESH_NPU_CARDS": "0",
            "PINGMESH_MAX_TOKENS": "50", "PINGMESH_MAX_MODEL_LEN": "100000",
        }), patch.dict("sys.modules", {"vllm": vllm}):
            engine = NpuEngine()
            engine.generate_json("encode this")
            snapshot = engine.stats.snapshot()
            self.assertEqual(snapshot["output_tokens"], len(reasoning) + len(answer))
            self.assertEqual(snapshot["answer_tokens"], len(answer))
            # Everything not in the answer is discarded by parse_json.
            self.assertEqual(snapshot["output_tokens"] - snapshot["answer_tokens"], len(reasoning))


class EncodeStatisticsTests(unittest.TestCase):
    def test_stats_are_out_of_band_and_do_not_change_the_artifact(self):
        engine = FakeEngine()
        encoder = EvidenceEncoder(engine)
        first = encoder.encode_incident("i", [node()])
        second = encoder.encode_incident("i", [node()])
        # Reporting must not leak into the artifact: identical input stays reproducible.
        self.assertEqual(first, second)
        stats = encoder.last_stats
        self.assertEqual(stats["incident_id"], "i")
        self.assertEqual(stats["devices"], 1)
        self.assertEqual(stats["devices_with_records"], 1)
        self.assertEqual(stats["records"], 2)
        # Counters are per incident, while the engine accumulates across both.
        self.assertEqual(stats["llm_calls"], 1)
        self.assertEqual(len(engine.calls), 2)
        # FakeEngine carries no instrumentation; counts still work.
        self.assertEqual(stats["engine"], {})
        self.assertGreaterEqual(stats["elapsed_seconds"], 0)

    def test_context_only_devices_are_counted_but_never_called(self):
        engine = FakeEngine()
        encoder = EvidenceEncoder(engine)
        encoder.encode_incident("i", [node(), {"mgmt_ip": "context-only"}])
        self.assertEqual(encoder.last_stats["devices"], 2)
        self.assertEqual(encoder.last_stats["devices_with_records"], 1)
        self.assertEqual(encoder.last_stats["llm_calls"], 1)

    def test_engine_stats_and_summary_aggregation(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from Sys.LLM.engine import NpuEngine
        from Sys.Score.llm_encoder_experiment import encoding_stats_metrics
        tokenizer = MagicMock()
        tokenizer.chat_template = None
        tokenizer.encode.return_value = [1, 2]
        llm = MagicMock()
        llm.get_tokenizer.return_value = tokenizer
        llm.generate.return_value = [SimpleNamespace(
            outputs=[SimpleNamespace(text='{"mappings": []}', finish_reason="stop")])]
        vllm = SimpleNamespace(LLM=MagicMock(return_value=llm), SamplingParams=MagicMock())
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {
            "PINGMESH_MODEL_PATH": tmp, "PINGMESH_NPU_CARDS": "0",
            "PINGMESH_MAX_TOKENS": "50", "PINGMESH_MAX_MODEL_LEN": "1000"
        }), patch.dict("sys.modules", {"vllm": vllm}):
            engine = NpuEngine()
            engine.generate_json("one")
            engine.generate_json("two")
            snapshot = engine.stats.snapshot()
            self.assertEqual((snapshot["calls"], snapshot["errors"]), (2, 0))
            self.assertEqual((snapshot["prompt_tokens"], snapshot["output_tokens"]), (4, 4))
            self.assertEqual(snapshot["length_truncations"], 0)
            tokenizer.encode.return_value = list(range(951))
            with self.assertRaises(ContextBudgetError):
                engine.generate_json("too long")
            # A budget rejection is a routing decision, not an inference failure.
            snapshot = engine.stats.snapshot()
            self.assertEqual((snapshot["calls"], snapshot["budget_rejections"]), (3, 1))
            self.assertEqual(snapshot["errors"], 0)

        rows = [{"incident_id": "a", "devices": 3, "devices_with_records": 2, "records": 5,
                 "llm_calls": 3, "elapsed_seconds": 1.5,
                 "engine": {"output_tokens": 10, "generate_seconds": 1.0}}]
        metrics = encoding_stats_metrics(rows)
        self.assertEqual(metrics["llm_calls"], 3)
        self.assertEqual(metrics["devices_with_records"], 2)
        self.assertEqual(metrics["engine"]["output_tokens"], 10)
        self.assertIsNone(encoding_stats_metrics([]))


if __name__ == "__main__":
    unittest.main()
