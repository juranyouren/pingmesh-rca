"""Numerical and evidence-isolation checks for the NEC mechanism reimplementation."""

import math
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys

import pytest

torch = pytest.importorskip("torch")
from torch import nn

from Baseline.NetEventCauseDevice import NECConfig, NetEventCauseDevice
from Baseline.NetEventCauseDevice.model import ODERNNPointProcess


def incident(case_id="train", event_types=("A", "B", "A"), times=(1, 2, 3)):
    return {"case_id": case_id, "group_id": case_id,
            "window": {"start": "2026-01-01T00:00:00+00:00",
                       "end": "2026-01-01T00:00:05+00:00",
                       "cutoff": "2026-01-01T00:00:05+00:00", "timezone": "UTC"},
            "devices": [{"id": d, "type": "switch"} for d in ("dA", "dB", "silent")],
            "physical_links": [{"u": "dA", "v": "dB", "evidence_ids": ["topo"]}],
            "events": [{"event_id": f"e{i}", "device_id": "dA" if t == "A" else "dB",
                        "event_type": t, "event_time": f"2026-01-01T00:00:0{s}+00:00",
                        "record_time": f"2026-01-01T00:00:0{s}+00:00", "source": "alarm"}
                       for i, (t, s) in enumerate(zip(event_types, times))]}


def config(**kwargs):
    values = {"hidden_size": 4, "embedding_size": 4, "epochs": 2,
              "time_unit_seconds": 1, "ode_step": 1, "ig_steps": 12,
              "learning_rate": 0.01}
    values.update(kwargs)
    return NECConfig(**values)


class ConstantProcess(ODERNNPointProcess):
    def __init__(self):
        super().__init__(2, 2, 2, ode_step=0.5)
        self.log_rate = nn.Parameter(torch.tensor(math.log(0.7), dtype=torch.double))
        self.double()

    def log_rates(self, state):
        return self.log_rate.expand(self.n_types)


def test_nll_includes_start_interevent_tail_and_correct_rate_gradient():
    process = ConstantProcess()
    types = torch.tensor([0, 1])
    _, terms = process.loss([1.0, 3.0], types, 5.0,
                            torch.tensor([0.7, 0.7], dtype=torch.double))
    assert float(terms["integral"].detach()) == pytest.approx(2 * 0.7 * 5, abs=1e-10)
    assert float(terms["nll"].detach()) == pytest.approx(7 - 2 * math.log(0.7), abs=1e-10)
    assert float(terms["empty_history_regularizer"].detach()) == pytest.approx(0, abs=1e-20)
    terms["nll"].backward()
    assert float(process.log_rate.grad) == pytest.approx(7 - 2, abs=1e-10)
    _, no_events = process.loss([], torch.tensor([], dtype=torch.long), 5.0,
                                torch.tensor([0.7, 0.7], dtype=torch.double))
    assert float(no_events["nll"].detach()) == pytest.approx(7, abs=1e-10)


class UnitDrift(nn.Module):
    def forward(self, state):
        return torch.ones_like(state)


class AddOneJump(nn.Module):
    def forward(self, embedding, state):
        return state + 1


class ExponentialProcess(ODERNNPointProcess):
    def __init__(self, step):
        super().__init__(2, 1, 1, ode_step=step)
        self.dynamics, self.jump = UnitDrift(), AddOneJump()
        self.double()

    def log_rates(self, state):
        return state[0].expand(2)


def test_rk4_joint_integral_tracks_jumps_and_converges_to_analytic_solution():
    exact = 2 * (math.e - 1) + 2 * (math.exp(4) - math.exp(2))
    errors = []
    for step in (0.5, 0.1):
        process = ExponentialProcess(step)
        logs, integral, _ = process.trajectory([1.0], process.embedding(torch.tensor([1])), 3.0)
        assert float(logs[0, 1]) == pytest.approx(1, abs=1e-10)
        errors.append(abs(float(integral) - exact))
    assert errors[1] < errors[0] / 100
    assert errors[1] < 0.00001


def test_null_history_regularizer_keeps_timestamps_and_all_type_terms():
    torch.manual_seed(9)
    process = ODERNNPointProcess(3, 4, 4, ode_step=0.5)
    times, types = [0.5, 1.5], torch.tensor([1, 2])
    prior = torch.tensor([0.0, 0.1, 0.3])
    loss, terms = process.loss(times, types, 2.0, prior, 2.0)
    null_logs, _, _ = process.trajectory(times, torch.zeros_like(process.embedding(types)), 2.0, False)
    expected = ((null_logs.exp() - prior) ** 2).sum()
    assert torch.allclose(terms["empty_history_regularizer"], expected)
    assert torch.allclose(loss, terms["nll"] + 2 * expected)
    empty_state_rate = process.log_rates(process.initial_state())
    assert not torch.allclose(null_logs[1], empty_state_rate)


def test_pre_event_intensity_ignores_future_and_simultaneous_embeddings():
    torch.manual_seed(8)
    process = ODERNNPointProcess(3, 4, 4, ode_step=0.5)
    types = torch.tensor([1, 2, 1, 2])
    logs, _, _ = process.trajectory([1, 2, 2, 3], process.embedding(types), 4, False)
    changed = process.embedding(types).detach().clone()
    changed[1:] += 100
    altered, _, _ = process.trajectory([1, 2, 2, 3], changed, 4, False)
    assert torch.equal(logs[:3], altered[:3])
    assert torch.equal(logs[1], logs[2])


def test_ig_completeness_signed_contributions_and_strict_history():
    torch.manual_seed(4)
    process = ODERNNPointProcess(3, 4, 4, ode_step=0.5).double()
    scores, detail = process.integrated_gradients([0.5, 1.0], torch.tensor([1, 2]), 2.0, 2, 64)
    assert abs(detail["completeness_residual"]) < 1e-7
    assert sum(scores) == pytest.approx(detail["log_intensity_delta"], abs=1e-7)
    assert len(scores) == 2
    with pytest.raises(ValueError, match="strictly"):
        process.integrated_gradients([1.0, 2.0], torch.tensor([1, 2]), 2.0, 2, 4)


@pytest.fixture
def fitted():
    return NetEventCauseDevice(config()).fit([incident()])


def test_fit_is_fold_local_checkpoint_roundtrip_and_labels_are_ignored(fitted, tmp_path):
    heldout = incident("heldout")
    plain = fitted.predict_raw_graph(heldout)
    heldout["root_device"] = "silent"
    heldout["groud_truth"] = {"anything": "dB"}
    heldout["labels"] = {"root_device": "dA", "positive_edges": [["dB", "dA"]]}
    changed = fitted.predict_raw_graph(heldout)
    plain.pop("timing")
    changed.pop("timing")
    assert plain == changed
    assert fitted.training_report["train_case_ids"] == ["train"]
    assert fitted.training_report["train_duration_model_units"] == 5
    assert fitted.prior.tolist() == pytest.approx([0, 0.04, 0.02])
    checkpoint = tmp_path / "nec.pt"
    fitted.save(checkpoint)
    loaded = NetEventCauseDevice.load(checkpoint)
    rerun = loaded.predict_raw_graph(incident("heldout"))
    rerun.pop("timing")
    assert rerun == plain
    assert checkpoint.with_suffix(".pt.json").exists()


def test_unknown_type_silent_device_and_cutoff_policy(fitted):
    case = incident("heldout")
    case["events"][1]["event_type"] = "NEVER_SEEN"
    case["events"][2]["record_time"] = "2026-01-01T00:00:06+00:00"
    result = fitted.predict_root(case)
    assert result["status"] == "ok"
    assert result["diagnostics"]["unknown_type_events"] == 1
    assert result["diagnostics"]["skipped_events"] == [{"event_id": "e2", "reason": "recorded_after_cutoff"}]
    assert len(result["root_ranking"]) == 3
    assert {row["device_id"]: row["score"] for row in result["root_ranking"]}["silent"] is None
    assert "NEVER_SEEN" not in str(fitted.vocabulary)
    case["events"] = []
    empty = fitted.predict_root(case)
    assert empty["status"] == "abstained"
    assert all(row["score"] is None for row in empty["root_ranking"])


def test_graph_keeps_event_direction_and_excludes_tied_causes(fitted):
    # Inspect only actual model-selected edges; every cause must be historical.
    fitted.config.root_threshold = 1.0
    result = fitted.predict_raw_graph(incident("heldout", times=(1, 2, 2)))
    assert result["status"] == "ok"
    by_id = {node["id"]: node for node in result["nodes"]}
    for edge in result["edges"]:
        assert by_id[edge["source"]]["event_time"] < by_id[edge["target"]]["event_time"]
        assert edge["score"] > 0 and edge["directed"]
        assert edge["evidence_ids"] == [edge["source"], edge["target"]]
    for node in result["nodes"]:
        for term in node.get("history_contributions", []):
            assert by_id[term["event_id"]]["event_time"] < node["event_time"]


def test_a_b_a_event_chain_exposes_device_projection_cycle(fitted):
    # Set an actual ODE-RNN to monotone excitation for a deterministic direction
    # check. This fixture is not used by any production fitting/inference path.
    model = ODERNNPointProcess(3, 1, 1, ode_step=1)
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        model.embedding.weight[1:].fill_(1)
        model.jump.weight_ih[2].fill_(1)
        model.query = nn.Linear(1, 1, bias=False)
        model.query.weight.fill_(1)
        model.type_features.weight.fill_(1)
    fitted.model = model
    fitted.prior.fill_(0.001)
    fitted.config.top_k_causes = 1
    result = fitted.predict_raw_graph(incident("heldout"))
    assert result["status"] == "ok"
    assert {(edge["source"], edge["target"]) for edge in result["edges"]} == {
        ("e0", "e1"), ("e1", "e2")}
    device_by_event = {node["id"]: node["device_id"] for node in result["nodes"]}
    projected = {(device_by_event[edge["source"]], device_by_event[edge["target"]])
                 for edge in result["edges"]}
    assert projected == {("dA", "dB"), ("dB", "dA")}
    assert result["graph_kind"] == "event_dependency_hypotheses"


def test_training_and_validation_groups_cannot_overlap():
    with pytest.raises(ValueError, match="overlap"):
        NetEventCauseDevice(config()).fit([incident()], validation_cases=[incident()])


def test_failed_refit_cannot_publish_partial_or_previous_training(fitted):
    with pytest.raises(ValueError):
        fitted.fit([])
    assert fitted.predict_root(incident("heldout"))["status"] == "runtime_failure"


def test_numerical_budget_and_missing_checkpoint_do_not_return_success():
    assert NetEventCauseDevice(config()).predict_root(incident())["status"] == "runtime_failure"
    with pytest.raises(ValueError, match="budget"):
        ExponentialProcess(0.01).evolve(torch.zeros(1), 100)


def test_unclipped_prior_ratio_is_diagnosed(fitted):
    fitted.prior.fill_(100)
    result = fitted.predict_root(incident("heldout"))
    assert result["diagnostics"]["ratio_anomalies"]
    assert max(row["score"] for row in result["root_ranking"] if row["score"] is not None) > 1


def test_loss_decreases_on_repeated_training_sequences():
    model = NetEventCauseDevice(config(epochs=12)).fit([incident()])
    history = model.training_report["history"]
    assert history[-1]["loss"] < history[0]["loss"]
    assert history[-1]["nll"] < history[0]["nll"]


def test_actual_cli_train_predict_and_failed_case_is_retained(tmp_path):
    train_file, predict_file = tmp_path / "train.jsonl", tmp_path / "test.jsonl"
    config_file, checkpoint = tmp_path / "config.json", tmp_path / "model.pt"
    output = tmp_path / "output.jsonl"
    train_file.write_text(json.dumps(incident()), encoding="utf-8")
    invalid = incident("invalid")
    invalid["window"]["start"] = "invalid-time"
    predict_file.write_text("\n".join(json.dumps(x) for x in [incident("heldout"), invalid]), encoding="utf-8")
    config_file.write_text(json.dumps(asdict(config(epochs=1))), encoding="utf-8")
    prefix = [sys.executable, "-m", "Baseline.NetEventCauseDevice"]
    cwd = str(Path(__file__).resolve().parents[1])
    subprocess.run(prefix + ["train", "--inputs", str(train_file), "--config", str(config_file),
                            "--checkpoint", str(checkpoint)], cwd=cwd, check=True,
                   capture_output=True, text=True)
    subprocess.run(prefix + ["predict", "--inputs", str(predict_file), "--checkpoint", str(checkpoint),
                            "--output", str(output), "--graph"], cwd=cwd, check=True,
                   capture_output=True, text=True)
    predictions = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [(p["case_id"], p["status"]) for p in predictions] == [
        ("heldout", "ok"), ("invalid", "input_ineligible")]
    assert predictions[0]["nodes"]
    assert len(predictions[0]["root_ranking"]) == 3
