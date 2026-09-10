import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from Baseline.common.evaluation import evaluate_case, load_labels, summarize
from Baseline.common.graph import adapt_graph, graph_validity, is_dag
from Baseline.common.io import dump_json, from_processed, from_raw, load_incidents, normalize_incident
from Baseline.common.runner import predict_one
from Baseline.common.schema import input_fingerprint, parse_timestamp, stable_hash, validate_incident
from Baseline.common.splits import build_manifest, validate_manifest
from Baseline.common.synthetic import make_cases
from Baseline.common.timeseries import build_timeseries


def case():
    return make_cases(1)[0][0]


def native(edges):
    return {"status": "ok", "nodes": [{"id": d} for d in "ABC"],
            "edges": [{"source": u, "target": v, "score": s, "evidence_ids": [f"{u}{v}"]}
                      for u, v, s in edges]}


def pred(incident, root="A", status="ok", task="full"):
    graph = adapt_graph(native([("A", "B", 2), ("B", "C", 1)]), incident, root,
                        condition="oracle" if task == "oracle" else "own_prediction")
    return {"case_id": incident["case_id"], "status": status, "task": task,
            "input_hash": input_fingerprint(incident), "root_ranking": [{"device_id": root}],
            "device_graph": graph}


def label(incident, complete=True):
    return {"case_id": incident["case_id"], "root_status": "confirmed", "root_device": "A",
            "graph_complete": complete, "positive_nodes": list("ABC"),
            "positive_edges": [["A", "B"], ["B", "C"]]}


@pytest.mark.parametrize("scale", [1, 1000, 1000000, 1000000000])
def test_timestamp_units(scale):
    assert parse_timestamp(1700000000 * scale) == 1700000000


def test_whitelist_excludes_answers_and_keeps_endpoint_lists():
    x = case()
    x.update(root_device="SECRET", cross={"SECRET": 1}, score=999)
    x["endpoint_context"] = {"source_ip": ["A", "B"], "sink_ip": {"root": "SECRET"}, "root": "SECRET"}
    x["events"][0].update(score=999, prediction="SECRET")
    x["observation_coverage"]["root"] = "SECRET"
    result = normalize_incident(x)
    assert "SECRET" not in json.dumps(result)
    assert result["endpoint_context"]["source_ip"] == ["A", "B"]
    assert input_fingerprint(normalize_incident({**x, "root_device": "DIFFERENT"})) == input_fingerprint(result)


def test_cutoff_event_and_collection_time_and_unknown():
    x = case()
    late = {**x["events"][0], "event_id": "late", "record_time": 1700000061}
    future = {**x["events"][0], "event_id": "future", "event_time": 1700000061}
    unknown = {**x["events"][0], "event_id": "unknown", "event_time": None}
    x["events"].extend([late, future, unknown])
    y = normalize_incident(x)
    assert {e["event_id"] for e in y["events"]} == {e["event_id"] for e in x["events"][:3]} | {"unknown"}
    assert y["input_diagnostics"]["excluded_events"]["recorded_after_cutoff"] == 1
    assert y["input_diagnostics"]["excluded_events"]["event_outside_window"] == 1
    with pytest.raises(ValueError, match="window"):
        validate_incident(x)


def test_duplicate_export_dedup_and_conflict():
    x = case()
    x["events"].append(copy.deepcopy(x["events"][0]))
    assert len(normalize_incident(x)["events"]) == 3
    x["events"][-1]["message"] = "a different observation"
    with pytest.raises(ValueError, match="Conflicting"):
        normalize_incident(x)


def test_raw_schema_does_not_copy_counts_labels_or_cross():
    raw = {"full_link": {"task_info": {"task_id": "raw", "alarm_time": 1700000000},
           "task_topo": {"value": [[{"nodes": [{"mgmt_ip": "A"}, {"mgmt_ip": "B"}],
                                    "links": [{"src_ip": "A", "dst_ip": "B"}]}]]},
           "alarm_list": [{"alarm_id": 1, "alarm_ip_ad": "A", "alarm_name": "linkdown", "alarm_time": 1700000000, "score": 99}],
           "log_list": {"total": 99}, "cross": {"root": "SECRET"}, "groud_truth": "SECRET"}}
    x = from_raw(raw)
    assert len(x["events"]) == 1
    assert x["input_diagnostics"]["raw_log_rows"] == 0
    assert "SECRET" not in json.dumps(x)


def test_loader_round_trip_and_duplicate_inventory(tmp_path):
    x = case()
    path = tmp_path / "inputs.json"
    dump_json(path, {"incidents": [x]})
    assert input_fingerprint(load_incidents(path)[0]) == input_fingerprint(x)
    dump_json(path, [x, x])
    with pytest.raises(ValueError, match="Duplicate case_id"):
        load_incidents(path)


def test_processed_keeps_silent_isolated_topology_devices(tmp_path):
    dump_json(tmp_path / "info.json", {"alarm_time": 1700000000})
    dump_json(tmp_path / "nodes.json", [{"mgmt_ip": "A", "alarms": []}])
    dump_json(tmp_path / "topology_context.json", {"diagnostics": {"source": "raw_task_topo"},
              "nodes": [{"device_id": "B"}], "edges": []})
    (tmp_path / "label.json").write_text("invalid JSON; must not be opened")
    assert {d["id"] for d in from_processed(tmp_path)["devices"]} == {"A", "B"}


def test_schema_artifacts_match_normalized_inputs_and_runner():
    import jsonschema
    from Baseline.SkyNetVoting import SkyNetVoting
    schemas = Path(__file__).parents[1] / "Baseline/common/schemas"
    for filename, payload in (("incident", case()), ("label", label(case())),
                              ("prediction", predict_one(SkyNetVoting(), "skynet", case(), "root"))):
        jsonschema.validate(payload, json.loads((schemas / f"{filename}.schema.json").read_text()))


def test_unverified_groups_do_not_produce_confidence_intervals():
    cases, labels, _ = make_cases(2)
    for x in cases:
        x["group_verified"] = False
    rows = [evaluate_case(pred(x, task="root"), l, x) for x, l in zip(cases, labels)]
    assert summarize(rows)["metrics"]["top_1"]["ci95"] is None


def test_raw_zero_sentinel_is_unknown_not_a_1970_event():
    x = case()
    x["events"][0]["event_time"] = None
    x["events"][0]["alarm_time"] = 0
    x["events"][0]["occur_time"] = 0
    out = normalize_incident(x)
    assert len(out["events"]) == 3
    assert next(e for e in out["events"] if e["event_id"] == x["events"][0]["event_id"])["event_time"] is None
    assert out["input_diagnostics"]["time_fields"]["occur_time_zero_sentinel"] == 1


def test_projection_preserves_native_and_max_support_without_inventing_edges():
    x = case()
    x["physical_links"].append({"u": "A", "v": "C"})
    g = native([("A", "B", 1), ("A", "B", 2), ("B", "C", 3), ("C", "B", 0.5), ("C", "A", 4)])
    before = copy.deepcopy(g)
    result = adapt_graph(g, x, "A")
    assert g == before
    assert {(e["source"], e["target"]) for e in result["edges"]} == {("A", "B"), ("B", "C")}
    assert next(e["score"] for e in result["raw_projection"] if e["source"] == "A") == 2
    assert {r["reason"] for r in result["removed"]} == {"incoming_root", "cycle"}
    assert result["validity"]["root_reachable"] and result["validity"]["dag"]


def test_projection_event_fold_self_nonphysical_undirected_disconnected():
    x = case()
    g = {"status": "ok", "nodes": [{"id": "a1", "device_id": "A"}, {"id": "a2", "device_id": "A"}, {"id": "c", "device_id": "C"}],
         "edges": [{"source": "a1", "target": "a2", "score": 2}, {"source": "a2", "target": "c", "score": 3},
                   {"source": "A", "target": "B", "directed": False, "score": 9},
                   {"source": "C", "target": "B", "score": 1}]}
    out = adapt_graph(g, x, "A")
    assert out["nodes"] == ["A"] and out["edges"] == [] and len(out["undirected"]) == 1
    assert {r["reason"] for r in out["removed"]} == {"device_self_loop", "nonphysical", "not_root_reachable"}


def test_adapter_multiple_parents_and_empty_native_status():
    x = case()
    x["physical_links"].append({"u": "A", "v": "C"})
    out = adapt_graph(native([("A", "B", 2), ("A", "C", 3), ("B", "C", 1)]), x, "A")
    assert len(out["edges"]) == 3
    assert adapt_graph(native([]), x, "A")["status"] == "ok"
    assert adapt_graph({"status": "runtime_failure"}, x, "A")["status"] == "runtime_failure"
    assert adapt_graph(native([]), x, "Z")["status"] == "input_ineligible"
    assert not graph_validity({"nodes": ["A"], "edges": [{"source": "A", "target": "Z"}]}, x, "A")["known_nodes"]


def test_partial_labels_unknown_and_optional_edges_are_not_negatives():
    x = case()
    l = {**label(x, False), "positive_edges": [["A", "B"]], "known_edge_mask": [["A", "B"], ["B", "C"]],
         "allowed_edges": [["B", "C"]], "known_node_mask": list("ABC")}
    row = evaluate_case(pred(x), l, x, "full")
    assert row["metrics"]["edge_f1"] == 1
    assert "exact_graph" not in row["metrics"]
    l["known_edge_mask"] = [["A", "B"]]
    l["allowed_edges"] = []
    assert evaluate_case(pred(x), l, x, "full")["unknown_predictions"]["edges"] == 1


def test_no_known_scope_is_unavailable_not_perfect_graph():
    x = case()
    l = {"case_id": x["case_id"], "positive_edges": [], "graph_complete": False}
    out = evaluate_case(pred(x), l, x, "full")
    assert out["graph_label_status"] == "unavailable"
    assert "edge_f1" not in out["metrics"] and "node_f1" not in out["metrics"]


def test_failure_remains_in_denominator_and_joint_requires_root():
    x = case()
    failed = evaluate_case(pred(x, status="runtime_failure"), label(x), x, "full")
    assert failed["metrics"]["top_1"] == failed["metrics"]["edge_f1"] == 0
    wrong = evaluate_case(pred(x, root="B"), label(x), x, "full")
    assert wrong["metrics"]["joint_edge_f1"] == 0
    correct = evaluate_case(pred(x), label(x), x, "full")
    result = summarize([correct, failed])
    assert result["metrics"]["edge_f1"]["mean"] == 0.5
    assert result["metrics"]["edge_f1"]["successful_cases_mean"] == 1


def test_root_missing_candidate_and_ranking_not_repaired():
    x = case()
    l = {**label(x), "root_device": "Z"}
    out = evaluate_case(pred(x, task="root"), l, x)
    assert out["metrics"]["candidate_recall"] == 0
    assert out["metrics"]["mrr"] == 0


def test_root_condition_and_hash_mismatch_rejected():
    x = case()
    with pytest.raises(ValueError, match="task"):
        evaluate_case(pred(x), label(x), x, "oracle")
    bad = pred(x, root="B", task="oracle")
    with pytest.raises(ValueError, match="confirmed root"):
        evaluate_case(bad, label(x), x, "oracle")
    bad = pred(x)
    bad["input_hash"] = "modified"
    with pytest.raises(ValueError, match="different input"):
        evaluate_case(bad, label(x), x, "full")


def test_labels_require_explicit_known_masks(tmp_path):
    path = tmp_path / "labels.json"
    dump_json(path, [label(case(), False)])
    with pytest.raises(ValueError, match="known_edge_mask"):
        load_labels(path)
    dump_json(path, [label(case())])
    assert len(load_labels(path)) == 1


def test_unknown_collection_is_masked_and_zero_counts_are_observation_only():
    x = case()
    x["observation_coverage"] = None
    assert build_timeseries(x)["status"] == "input_ineligible"
    assumed = build_timeseries(x, require_coverage=False)
    assert assumed["status"] == "ok" and not any(any(r) for r in assumed["mask"])
    assert "zero_is_not_health" in assumed["diagnostics"]["coverage_assumption"]
    x["observation_coverage"] = {"intervals": [{"start": 1700000000, "end": 1700000020, "device_ids": ["A"]}]}
    partial = build_timeseries(x)
    assert partial["values"][0] == [1.0, None, None]
    assert partial["values"][2] == [None, None, None]


def test_timezone_is_consistent_and_cutoff_bin_inclusive():
    x = case()
    x["window"] = {"start": "2023-01-01T00:00:00", "end": "2023-01-01T00:01:00", "cutoff": "2023-01-01T00:01:00", "timezone": "UTC"}
    x["events"] = [{**x["events"][0], "event_time": "2023-01-01T00:01:00"}]
    assert build_timeseries(x)["values"][-1][0] == 1


def test_manifest_group_isolation_hash_and_duplicate_exports():
    cases, _, groups = make_cases()
    groups[cases[1]["case_id"]] = groups[cases[0]["case_id"]]
    manifest = build_manifest(cases, groups, folds=3)
    assert validate_manifest(manifest, cases) == manifest
    changed = copy.deepcopy(cases)
    changed[0]["events"][0]["message"] = "new input"
    with pytest.raises(ValueError, match="hash"):
        validate_manifest(manifest, changed)
    duplicate = {**cases[0], "case_id": "duplicate"}
    with pytest.raises(ValueError, match="Identical"):
        build_manifest([*cases, duplicate], {**groups, "duplicate": "other"}, folds=3)


def test_predict_one_preserves_failures_and_unsupported_cases():
    class Broken:
        def predict_root(self, _):
            raise RuntimeError("intentional test failure")
    out = predict_one(Broken(), "skynet", case(), "root")
    assert out["case_id"] == case()["case_id"] and out["status"] == "runtime_failure"
    assert predict_one(Broken(), "skynet", case(), "full")["status"] == "unsupported_task"


def test_crossvalidate_training_failure_keeps_every_test_case(tmp_path, monkeypatch):
    from Baseline.common import runner
    cases, _, groups = make_cases()
    inputs, manifest, output = [tmp_path / x for x in ("inputs.json", "folds.json", "output.json")]
    dump_json(inputs, cases)
    dump_json(manifest, build_manifest(cases, groups, folds=3))
    class BrokenTraining:
        def fit(self, *_args, **_kwargs):
            raise RuntimeError("intentional training failure")
    monkeypatch.setattr(runner, "make_model", lambda *a, **k: BrokenTraining())
    monkeypatch.setattr(sys, "argv", ["baseline", "crossvalidate", "--method", "nec", "--inputs", str(inputs),
                        "--manifest", str(manifest), "--output", str(output)])
    runner.main()
    payload = json.loads(output.read_text())
    assert {p["case_id"] for p in payload["predictions"]} == {c["case_id"] for c in cases}
    assert len(payload["predictions"]) == 6
    assert all(p["status"] == "runtime_failure" for p in payload["predictions"])
    assert len(payload["training"]) == 3


def test_oracle_only_adapter_changes_native_graph():
    class Discovery:
        def predict_raw_graph(self, c):
            return {"case_id": c["case_id"], **native([("A", "B", 1), ("B", "C", 1)])}
    x = case()
    a = predict_one(Discovery(), "pcmci", x, "oracle", "A")
    b = predict_one(Discovery(), "pcmci", x, "oracle", "B")
    assert a["native_graph"] == b["native_graph"]
    assert a["device_graph"] != b["device_graph"]


def test_cli_root_predictions_evaluation_and_label_rejection(tmp_path):
    cases, labels, _ = make_cases(2)
    ip, lp, op, ep = [tmp_path / name for name in ("inputs.json", "labels.json", "predictions.json", "evaluation.json")]
    dump_json(ip, {"incidents": cases})
    dump_json(lp, {"labels": labels})
    def run(*args):
        return subprocess.run([sys.executable, "-m", "Baseline.common", *map(str, args)], capture_output=True, text=True)
    result = run("predict", "--method", "skynet", "--inputs", ip, "--output", op)
    assert result.returncode == 0, result.stderr
    assert len(json.loads(op.read_text())["predictions"]) == 2
    result = run("evaluate", "--inputs", ip, "--labels", lp, "--predictions", op, "--output", ep)
    assert result.returncode == 0, result.stderr
    assert json.loads(ep.read_text())["summary"]["cases"] == 2
    result = run("predict", "--method", "skynet", "--inputs", ip, "--labels", lp, "--output", op)
    assert result.returncode != 0 and "Only Oracle" in result.stderr
