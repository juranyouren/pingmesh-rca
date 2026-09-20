"""Run on the server: python -m pytest Baseline/RQ1/tests -q."""
from copy import deepcopy
import os

import pytest

from Baseline.common.io import dump_json, read_json
from Baseline.common.splits import build_manifest
from Baseline.common.synthetic import make_cases
from Baseline.RQ1.graph import project
from Baseline.RQ1.metrics import aggregate, evaluate, label_sets
from Baseline.RQ1.models import Ours, PCMCI, THP, TimeOrder, timed_events, thp_device_edges
from Baseline.RQ1.runner import main, predict


@pytest.fixture
def sample():
    cases, labels, _ = make_cases()
    return cases[0], labels[0]


def scored(sample, edges, **label_overrides):
    case, label = sample
    return evaluate({"status": "ok", "device_graph": {"edges": edges}},
                    {**label, **label_overrides}, case)


def edge(u, v, directed=True):
    return {"source": u, "target": v, "directed": directed}


def test_reversal_cost_one(sample):
    row = scored(sample, [edge("B", "A"), edge("B", "C")])
    assert row["metrics"]["Adj-F1"] == 1
    assert row["metrics"]["AH-F1"] == 0.5
    assert row["metrics"]["SHD"] == 1


def test_undirected_hits_only_adjacency(sample):
    row = scored(sample, [edge("A", "B", False), edge("B", "C", False)])
    assert row["metrics"]["Adj-F1"] == 1
    assert row["metrics"]["AH-F1"] == 0
    assert row["metrics"]["SHD"] == 2


def test_two_arrowheads_are_not_one_correct_directed_edge(sample):
    row = scored(sample, [edge("A", "B"), edge("B", "A"), edge("B", "C")])
    assert row["metrics"]["AH-P"] == pytest.approx(2 / 3)
    assert row["metrics"]["AH-R"] == 1
    assert row["metrics"]["SHD"] == 1


def test_missing_edge_and_empty_success(sample):
    assert scored(sample, [edge("A", "B")])["metrics"]["SHD"] == 1
    assert scored(sample, [])["metrics"]["SHD"] == 2
    row = scored(sample, [], positive_edges=[], positive_nodes=[])
    assert row["metrics"]["Adj-F1"] == row["metrics"]["AH-F1"] == 1
    assert row["metrics"]["SHD"] == 0


def test_failed_is_not_successful_empty(sample):
    case, label = sample
    row = evaluate({"status": "runtime_failure"}, {**label, "positive_edges": []}, case)
    assert row["metrics"]["Adj-F1"] == 0
    assert "SHD" not in row["metrics"]
    assert row["counts"]["Adj"] is None


def test_partial_masks_are_independent(sample):
    row = scored(sample, [edge("B", "A"), edge("B", "C")], graph_complete=False,
                 positive_edges=[], known_edge_mask=[["A", "B"]],
                 positive_adjacencies=[["A", "B"]], known_adjacency_mask=[["A", "B"]])
    assert row["metrics"]["Adj-F1"] == 1
    assert row["unknown_predictions"] == {"adjacencies": 1, "arrowheads": 2}
    assert "SHD" not in row["metrics"]


def test_one_negative_direction_does_not_make_negative_adjacency(sample):
    row = scored(sample, [edge("B", "A")], graph_complete=False,
                 positive_edges=[], known_edge_mask=[["A", "B"]])
    assert "Adj-F1" not in row["metrics"]


def test_allowed_pair_is_neutral(sample):
    row = scored(sample, [edge("A", "B"), edge("B", "C")], graph_complete=False,
                 positive_edges=[["A", "B"]],
                 known_edge_mask=[["A", "B"], ["B", "C"], ["C", "B"]], allowed_edges=[["B", "C"]])
    assert row["metrics"]["Adj-F1"] == row["metrics"]["AH-F1"] == 1
    assert row["unknown_predictions"] == {"adjacencies": 0, "arrowheads": 0}
    assert row["neutral_predictions"] == {"adjacencies": 1, "arrowheads": 1}


@pytest.mark.parametrize("change", [
    {"positive_edges": [["A", "D"]]},
    {"positive_edges": [["A", "C"]]},
    {"positive_edges": [["A", "B"], ["B", "A"]]},
    {"graph_complete": False, "known_edge_mask": []},
])
def test_bad_labels_rejected(sample, change):
    case, label = sample
    with pytest.raises(ValueError):
        label_sets({**label, **change}, case)


def test_incident_macro_not_window_macro():
    rows = [{"group_id": "g1", "status": "ok", "metrics": {"Adj-F1": 1}},
            {"group_id": "g1", "status": "ok", "metrics": {"Adj-F1": 1}},
            {"group_id": "g2", "status": "ok", "metrics": {"Adj-F1": 0}}]
    assert aggregate(rows, bootstrap_samples=0)["metrics"]["Adj-F1"]["mean"] == 0.5


def test_shd_withheld_if_any_failure():
    rows = [{"group_id": "a", "status": "ok", "metrics": {"SHD": 0}},
            {"group_id": "b", "status": "runtime_failure", "metrics": {}}]
    metric = aggregate(rows)["metrics"]["SHD"]
    assert metric["mean"] is None
    assert metric["successful_only_mean"] == 0


def test_timeorder_topology_and_ties(sample):
    case, _ = sample
    output = TimeOrder().predict_raw_graph(case)
    assert {(e["source"], e["target"]) for e in output["edges"]} == {("A", "B"), ("B", "C")}
    case = deepcopy(case)
    case["events"][1]["event_time"] = case["events"][0]["event_time"]
    output = TimeOrder().predict_raw_graph(case)
    assert output["edges"][0]["directed"] is False


def test_thp_mapping_direction_diagonal_ties_and_topology(sample):
    case, _ = sample
    events = timed_events(case)
    matrix = [[1, 1, 1], [0, 1, 1], [0, 0, 1]]
    edges = thp_device_edges(case, events, ["alarm-A", "alarm-B", "alarm-C"], matrix, 60)
    assert {(e["source"], e["target"]) for e in edges} == {("A", "B"), ("B", "C")}
    assert thp_device_edges(case, events, ["alarm-A", "alarm-B", "alarm-C"], matrix, 5) == []
    all_same = [(events[0][0], {**e, "event_type": "same"}) for _, e in events]
    assert thp_device_edges(case, all_same, ["same"], [[1]], 60) == []
    same_type = [(t, {**e, "event_type": "same"}) for t, e in events]
    assert thp_device_edges(case, same_type, ["same"], [[1]], 60) == []


def test_event_device_projection_keeps_undecided_and_removes_nonphysical(sample):
    case, _ = sample
    native = {"nodes": [{"id": "e1", "device_id": "A"}, {"id": "e2", "device_id": "B"}],
              "edges": [edge("e1", "e2", False), edge("A", "C"), edge("A", "A")]}
    graph = project(native, case)
    assert len(graph["edges"]) == 1 and graph["edges"][0]["directed"] is False
    assert {r["reason"] for r in graph["removed"]} == {"nonphysical", "device_self_loop"}


def test_ours_uses_existing_pipeline_and_never_nonphysical(sample):
    case, _ = sample
    output = predict(Ours(), "ours", case, 0, "shared_prediction", "A")
    assert output["status"] == "ok", output.get("reason")
    assert "stage2" in output["native_graph"]
    assert output["graphs"]["rooted"]["root"] == "A"
    assert "A" in output["graphs"]["rooted"]["nodes"]


def files(tmp_path):
    cases, labels, groups = make_cases(4)
    manifest = build_manifest(cases, groups, folds=2)
    dump_json(tmp_path / "inputs.json", {"incidents": cases})
    dump_json(tmp_path / "labels.json", {"labels": labels})
    dump_json(tmp_path / "manifest.json", manifest)
    dump_json(tmp_path / "roots.json", {"manifest_hash": manifest["manifest_hash"],
              "source": "synthetic fixed roots only", "roots": {c["case_id"]: "A" for c in cases}})
    return ["--inputs", str(tmp_path / "inputs.json"), "--labels", str(tmp_path / "labels.json"),
            "--manifest", str(tmp_path / "manifest.json"), "--roots", str(tmp_path / "roots.json")], cases, labels


def test_cli_outputs_re_evaluate_and_no_overwrite(tmp_path):
    args, _, _ = files(tmp_path)
    run = tmp_path / "run"
    main(["run", *args, "--methods", "timeorder", "ours", "--output", str(run), "--bootstrap-samples", "0"])
    summary = read_json(run / "summary.json")
    assert summary["tables"]["rooted"]["complete_all"]["timeorder"]["metrics"]["AH-F1"]["mean"] == 1
    assert (run / "table.csv").exists()
    main(["evaluate", *args, "--methods", "timeorder", "ours", "--predictions", str(run / "predictions.json"),
          "--output", str(tmp_path / "rescore"), "--bootstrap-samples", "0"])
    assert read_json(tmp_path / "rescore" / "summary.json") == summary
    with pytest.raises(ValueError, match="already exists"):
        main(["run", *args, "--methods", "timeorder", "--output", str(run)])


def test_graph_labels_do_not_change_predictions(tmp_path):
    args, _, labels = files(tmp_path)
    main(["run", *args, "--methods", "timeorder", "ours", "--output", str(tmp_path / "a")])
    dump_json(tmp_path / "labels.json", {"labels": [{**l, "positive_edges": [], "positive_nodes": []} for l in labels]})
    main(["run", *args, "--methods", "timeorder", "ours", "--output", str(tmp_path / "b")])
    a, b = [read_json(tmp_path / d / "predictions.json")["predictions"] for d in ("a", "b")]
    for x, y in zip(a, b):
        x.pop("timing_seconds")
        y.pop("timing_seconds")
        assert x == y


def test_nec_training_cannot_see_test_groups_or_labels(tmp_path, monkeypatch):
    import Baseline.RQ1.runner as runner
    args, cases, _ = files(tmp_path)
    train_groups = set()

    class FakeNEC(TimeOrder):
        training_report = {}

        def fit(self, train, validation_cases):
            train_groups.clear()
            train_groups.update(c["group_id"] for c in train + validation_cases)
            assert all("positive_edges" not in c and "root_device" not in c for c in train)

        def save(self, path):
            path.write_text("synthetic fixture")

        def predict_raw_graph(self, case):
            assert case["group_id"] not in train_groups
            return super().predict_raw_graph(case)

    monkeypatch.setattr(runner, "make_model", lambda *args: FakeNEC())
    main(["run", *args, "--methods", "nec", "--output", str(tmp_path / "run")])
    assert len(read_json(tmp_path / "run" / "predictions.json")["predictions"]) == len(cases)


def test_failed_backend_retains_all_cases_and_nonzero_exit(tmp_path, monkeypatch):
    import Baseline.RQ1.runner as runner
    args, cases, _ = files(tmp_path)

    def broken(*args):
        raise ImportError("backend deliberately unavailable")

    monkeypatch.setattr(runner, "make_model", broken)
    with pytest.raises(SystemExit) as exc:
        main(["run", *args, "--methods", "thp", "--output", str(tmp_path / "run")])
    assert exc.value.code == 2
    payload = read_json(tmp_path / "run" / "predictions.json")
    assert len(payload["predictions"]) == len(cases)
    assert all(p["status"] == "runtime_failure" for p in payload["predictions"])
    assert (tmp_path / "run" / "table.md").exists()


@pytest.mark.skipif(os.environ.get("RQ1_NUMERICAL_SMOKE") != "1", reason="opt-in real scientific backends on server")
def test_real_pcmci_and_thp(sample):
    case, _ = sample
    # Small interface checks, not method accuracy claims.
    pcmci = predict(PCMCI({"bin_seconds": 1, "min_bins": 30}), "pcmci", case, 0, "oracle", "A")
    assert pcmci["status"] == "ok", pcmci["reason"]
    thp = predict(THP({"max_iter": 1}), "thp", case, 0, "oracle", "A")
    assert thp["status"] == "ok", thp["reason"]


def test_shared_root_manifest_mismatch_rejected(tmp_path):
    args, _, _ = files(tmp_path)
    roots = read_json(tmp_path / "roots.json")
    roots["manifest_hash"] = "wrong"
    dump_json(tmp_path / "roots.json", roots)
    with pytest.raises(ValueError, match="manifest_hash"):
        main(["run", *args, "--methods", "timeorder", "--output", str(tmp_path / "bad"), "--dry-run"])
