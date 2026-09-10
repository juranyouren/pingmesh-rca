"""Numerical mechanism checks, not production quality measurements."""

import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import warnings
from typing import List, Tuple

import numpy as np
import pytest
import scipy.linalg
import scipy.optimize

from Baseline.DYNOTEARS import DYNOTEARS
from Baseline.DYNOTEARS import author_kernel
from Baseline.DYNOTEARS.predictor import ConvergenceFailure
from Baseline.PCMCIPlus import PCMCIPlus


ROOT = Path(__file__).resolve().parents[1]


def continuous_causal_series(rows=500):
    rng = np.random.default_rng(123)
    values = np.zeros((rows, 3))
    for t in range(2, rows):
        values[t, 0] = 0.4 * values[t - 1, 0] + rng.normal()
        values[t, 1] = 0.9 * values[t - 1, 0] + 0.2 * values[t - 1, 1] + rng.normal(scale=0.6)
        values[t, 2] = -0.8 * values[t - 1, 1] + rng.normal(scale=0.6)
    return values


def count_incident(coverage=True):
    rng = np.random.default_rng(937)
    rows = 180
    a = rng.poisson(2, size=rows)
    b = np.concatenate([[0], a[:-1]]) + rng.poisson(0.5, size=rows)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(seconds=10 * rows)
    events = []
    for index in range(rows):
        for device, count in (("A", a[index]), ("B", b[index])):
            for ordinal in range(int(count)):
                events.append({"event_id": f"{device}-{index}-{ordinal}", "device_id": device,
                               "event_type": "synthetic-alarm", "source": "alarm",
                               "event_time": (start + timedelta(seconds=10 * index + 1)).isoformat()})
    return {"case_id": "synthetic-count-chain", "group_id": "synthetic-group",
            "window": {"start": start.isoformat(), "end": end.isoformat(), "cutoff": end.isoformat(), "timezone": "UTC"},
            "devices": [{"id": d, "type": "synthetic"} for d in ("A", "B", "constant-C")],
            "physical_links": [{"u": "A", "v": "B"}], "events": events,
            "observation_coverage": {"complete": True} if coverage else None, "endpoint_context": {}}


def test_pcmciplus_actual_lag_direction_signed_statistic_and_autoregression():
    result = PCMCIPlus({"tau_max": 1}).discover_matrix(continuous_causal_series(), ["A", "B", "C"])
    edges = {(e["source"], e["target"], e["lag"]): e for e in result["edges"]}
    assert edges[("A", "B", 1)]["directed"] is True
    assert edges[("B", "C", 1)]["signed_statistic"] < 0
    assert edges[("B", "C", 1)]["score"] > 0
    assert ("A", "A", 1) in edges  # Native self-lag is preserved for the adapter.
    assert ("B", "A", 1) not in edges
    assert len(result["native_arrays"]["graph"]) == 3


def test_pcmciplus_actual_contemporaneous_ambiguity_remains_undirected():
    rng = np.random.default_rng(811)
    x = rng.normal(size=600)
    values = np.column_stack([x, 0.9 * x + rng.normal(scale=0.4, size=len(x))])
    result = PCMCIPlus({"tau_max": 1}).discover_matrix(values, ["A", "B"])
    contemporaneous = [e for e in result["edges"] if e["lag"] == 0]
    assert len(contemporaneous) == 1
    assert contemporaneous[0]["directed"] is False
    assert contemporaneous[0]["orientation_mark"] in {"o-o", "x-x"}


def test_dynotears_actual_signed_lag_direction_and_convergence():
    result = DYNOTEARS({"p": 1, "lambda_w": 0.05, "lambda_a": 0.05}).discover_matrix(
        continuous_causal_series(), ["A", "B", "C"])
    edges = {(e["source"], e["target"], e["lag"]): e for e in result["edges"]}
    assert edges[("A", "B", 1)]["coefficient"] > 0.5
    assert edges[("B", "C", 1)]["coefficient"] < -0.5
    assert edges[("B", "C", 1)]["score"] > 0
    assert ("A", "A", 1) in edges
    assert result["diagnostics"]["converged"] is True
    assert all(run["success"] for run in result["diagnostics"]["optimizer_runs"])
    assert result["diagnostics"]["h_W"] <= 1e-8


def test_dynotears_author_source_lock_and_numerical_parity():
    source = (ROOT / "Baseline/DYNOTEARS/upstream/dynotears.py").read_bytes()
    provenance = json.loads((ROOT / "Baseline/DYNOTEARS/provenance.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(source).hexdigest() == provenance["source_sha256"]
    selected = set(provenance["extracted_functions"])
    original = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name in selected]
    vendored = [node for node in ast.parse(Path(author_kernel.__file__).read_text(encoding="utf-8")).body
                if isinstance(node, ast.FunctionDef) and node.name in selected]
    assert [ast.dump(node) for node in original] == [ast.dump(node) for node in vendored]
    namespace = {"np": np, "slin": scipy.linalg, "sopt": scipy.optimize,
                 "warnings": warnings, "List": List, "Tuple": Tuple}
    exec(compile(ast.Module(body=original, type_ignores=[]), "locked-upstream-functions", "exec"), namespace)
    values = continuous_causal_series(320)
    standard = (values - values.mean(axis=0)) / values.std(axis=0)
    p, d = 2, values.shape[1]
    x = standard[p:]
    lags = np.concatenate([standard[p - lag:len(standard) - lag] for lag in range(1, p + 1)], axis=1)
    bounds = 2 * [(0, 0) if i == j else (0, None) for i in range(d) for j in range(d)]
    bounds += [(0, None)] * (2 * p * d * d)
    expected_w, expected_a = namespace["_learn_dynamic_structure"](x, lags, bounds, 0.1, 0.1, 100, 1e-8)
    actual = DYNOTEARS({"p": p}).discover_matrix(values, ["A", "B", "C"])
    np.testing.assert_allclose(actual["native_arrays"]["W"], expected_w, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(actual["native_arrays"]["A"], expected_a, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("baseline", [PCMCIPlus, DYNOTEARS])
def test_coverage_unknown_is_input_ineligible_without_fitting(baseline):
    result = baseline().predict_raw_graph(count_incident(coverage=False))
    assert result["status"] == "input_ineligible"
    assert result["reason"] == "collection_coverage_unknown"
    assert result["edges"] == []


@pytest.mark.parametrize("baseline", [PCMCIPlus, DYNOTEARS])
def test_count_incident_pipeline_and_labels_do_not_change_native_graph(baseline):
    cfg = {"mode": "count", "tau_max": 1} if baseline is PCMCIPlus else {"mode": "count", "p": 1}
    case = count_incident()
    altered = deepcopy(case)
    altered.update(root_device="B", positive_edges=[["B", "A"]], root_condition="B")
    first = baseline(cfg).predict_raw_graph(case)
    second = baseline(cfg).predict_raw_graph(altered)
    assert first["status"] == second["status"] == "ok"
    assert first["native_arrays"] == second["native_arrays"]
    assert first["edges"] == second["edges"]
    assert first["diagnostics"]["input_audit"]["constant_devices"] == ["constant-C"]
    assert any(e["source"] == "A" and e["target"] == "B" and e["lag"] == 1 for e in first["edges"])
    assert first["root_ranking"] == []


def test_dynotears_real_outer_nonconvergence_is_not_a_successful_empty_graph():
    model = DYNOTEARS({"p": 1, "lambda_w": 0.01, "lambda_a": 0.01, "max_iter": 1, "h_tol": 1e-16})
    with pytest.raises(ConvergenceFailure) as caught:
        model.discover_matrix(continuous_causal_series(), ["A", "B", "C"])
    assert caught.value.diagnostics["converged"] is False
    assert caught.value.native_arrays["W"]


def test_dynotears_failed_optimizer_with_acyclic_iterate_is_not_success(monkeypatch):
    real_minimize = scipy.optimize.minimize
    def failed_minimize(*args, **kwargs):
        result = real_minimize(*args, **kwargs)
        result.success = False
        result.status = 9
        result.message = "synthetic optimizer failure marker"
        return result
    monkeypatch.setattr(scipy.optimize, "minimize", failed_minimize)
    result = DYNOTEARS({"p": 1}).predict_raw_graph(count_incident())
    assert result["status"] == "runtime_failure"
    assert result["edges"] == []
    assert result["native_arrays"]["W"]
    assert result["diagnostics"]["converged"] is False
    assert any(not run["success"] for run in result["diagnostics"]["optimizer_runs"])
