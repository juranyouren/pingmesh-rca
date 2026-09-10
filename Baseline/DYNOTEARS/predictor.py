from __future__ import annotations

from dataclasses import asdict, dataclass
from types import FunctionType, SimpleNamespace
import time
import warnings

from Baseline.common.timeseries import dense_input


class ConvergenceFailure(RuntimeError):
    def __init__(self, message, native_arrays, diagnostics):
        super().__init__(message)
        self.native_arrays = native_arrays
        self.diagnostics = diagnostics


@dataclass
class DYNOTEARSConfig:
    bin_seconds: float = 10
    mode: str = "log1p"
    min_bins: int = 30
    max_variables: int = 30
    p: int = 2
    lambda_w: float = 0.1
    lambda_a: float = 0.1
    max_iter: int = 100
    h_tol: float = 1e-8
    w_threshold: float = 0.05
    require_coverage: bool = True


class DYNOTEARS:
    method = "DYNOTEARS-CausalNex-kernel-incident-graph-adapt"
    version = "0.1.0"

    def __init__(self, config=None):
        self.config = DYNOTEARSConfig(**(config or {}))
        c = self.config
        if c.p < 1 or c.max_iter < 1 or min(c.lambda_w, c.lambda_a, c.w_threshold) < 0 or c.h_tol <= 0:
            raise ValueError("Invalid DYNOTEARS configuration")

    def discover_matrix(self, matrix, device_ids):
        import numpy as np
        import scipy.linalg
        import scipy.optimize
        from .author_kernel import _learn_dynamic_structure
        data = np.asarray(matrix, dtype=float)
        c = self.config
        if data.ndim != 2 or data.shape[1] != len(device_ids) or len(data) <= c.p + 2 or not np.isfinite(data).all():
            raise ValueError("Invalid finite time-by-variable matrix")
        std = data.std(axis=0)
        if np.any(std <= 1e-12):
            raise ValueError("Constant input variable")
        data = (data - data.mean(axis=0)) / std
        n, d = data.shape
        X = data[c.p:]
        Xlags = np.concatenate([data[c.p - lag:n - lag] for lag in range(1, c.p + 1)], axis=1)
        bounds_w = 2 * [(0, 0) if i == j else (0, None) for i in range(d) for j in range(d)]
        bounds_a = [(0, None)] * (2 * c.p * d * d)
        optimizer_runs = []
        def observed_minimize(*args, **kwargs):
            fit = scipy.optimize.minimize(*args, **kwargs)
            optimizer_runs.append({"success": bool(fit.success), "status": int(fit.status),
                                   "message": str(fit.message), "iterations": int(fit.nit),
                                   "objective": float(fit.fun)})
            return fit
        # The upstream function discards OptimizeResult and retains only .x.
        # Clone its globals to observe calls without changing the vendored body
        # or monkeypatching scipy/shared module state across concurrent fits.
        observed_kernel = FunctionType(
            _learn_dynamic_structure.__code__,
            {**_learn_dynamic_structure.__globals__, "sopt": SimpleNamespace(minimize=observed_minimize)},
            _learn_dynamic_structure.__name__, _learn_dynamic_structure.__defaults__,
            _learn_dynamic_structure.__closure__,
        )
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter("always")
            W, A = observed_kernel(X, Xlags, bounds_w + bounds_a, c.lambda_w, c.lambda_a, c.max_iter, c.h_tol)
        h = float(np.trace(scipy.linalg.expm(W * W)) - d)
        if not np.isfinite(W).all() or not np.isfinite(A).all() or not np.isfinite(h):
            raise FloatingPointError("Non-finite dynamic structure fit")
        warning_texts = [str(w.message) for w in observed]
        loss = float(0.5 / len(X) * np.linalg.norm(X - X @ W - Xlags @ A, "fro") ** 2)
        native_arrays = {"W": W.tolist(), "A": A.tolist()}
        diagnostics = {"h_W": h, "least_squares_loss": loss, "warnings": warning_texts,
                       "n_rows": len(X), "variables": d, "lagged_design_rank": int(np.linalg.matrix_rank(Xlags)),
                       "standardization": "within_current_incident_no_labels",
                       "solver": "unmodified CausalNex numerical kernel with call observation",
                       "optimizer_runs": optimizer_runs,
                       "converged": h <= c.h_tol and all(run["success"] for run in optimizer_runs)
                                    and not any("Failed to converge" in text for text in warning_texts)}
        if not diagnostics["converged"]:
            raise ConvergenceFailure(
                f"DYNOTEARS not converged: h={h:g}, tolerance={c.h_tol:g}, "
                f"failed_subproblems={sum(not run['success'] for run in optimizer_runs)}",
                native_arrays, diagnostics,
            )
        edges = []
        for lag in range(c.p + 1):
            weights = W if lag == 0 else A[(lag - 1) * d:lag * d]
            for i, u in enumerate(device_ids):
                for j, v in enumerate(device_ids):
                    weight = float(weights[i, j])
                    if weight == 0 or abs(weight) < c.w_threshold:
                        continue
                    edges.append({"source": u, "target": v, "lag": lag, "directed": True,
                                  "score": abs(weight), "coefficient": weight, "evidence_ids": [f"series:{u}", f"series:{v}"],
                                  "score_semantics": "absolute standardized SVAR coefficient, not probability"})
        return {"nodes": [{"id": d, "device_id": d} for d in device_ids], "edges": edges,
                "native_arrays": native_arrays, "diagnostics": diagnostics}

    def predict_raw_graph(self, incident):
        start = time.perf_counter()
        result = {"case_id": incident["case_id"], "method": self.method, "version": self.version, "status": "ok", "nodes": [], "edges": [], "root_ranking": [], "diagnostics": {"config": asdict(self.config), "input_contract_version": "baseline-incident-v1"}}
        try:
            c = self.config
            matrix, ids, audit = dense_input(incident, bin_seconds=c.bin_seconds, mode=c.mode,
                                           min_bins=c.min_bins, max_variables=c.max_variables, require_coverage=c.require_coverage)
            result["diagnostics"].update(input_audit=audit, fit_protocol="per_incident_unlabeled")
            result.update(self.discover_matrix(matrix, ids))
            result["diagnostics"].update(config=asdict(c), input_audit=audit, fit_protocol="per_incident_unlabeled", input_contract_version="baseline-incident-v1")
        except ValueError as exc:
            result.update(status="input_ineligible", reason=str(exc))
        except ConvergenceFailure as exc:
            result.update(status="runtime_failure", reason=str(exc), native_arrays=exc.native_arrays)
            result["diagnostics"].update(exc.diagnostics)
        except (ImportError, RuntimeError, FloatingPointError) as exc:
            result.update(status="runtime_failure", reason=f"{type(exc).__name__}: {exc}")
        result["timing"] = {"prediction_seconds": time.perf_counter() - start}
        return result
