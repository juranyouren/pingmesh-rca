from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.metadata
import time

from Baseline.common.timeseries import dense_input


@dataclass
class PCMCIConfig:
    bin_seconds: float = 10
    mode: str = "log1p"
    min_bins: int = 30
    max_variables: int = 50
    tau_max: int = 2
    pc_alpha: float = 0.01
    max_conds_dim: int = 3
    require_coverage: bool = True


class PCMCIPlus:
    method = "PCMCI+-ParCorr-incident-graph-adapt"
    version = "0.1.0"

    def __init__(self, config=None):
        self.config = PCMCIConfig(**(config or {}))
        if self.config.tau_max < 1 or not 0 < self.config.pc_alpha < 1 or self.config.max_conds_dim < 0:
            raise ValueError("Invalid lag, CI threshold or conditioning-set size")

    def discover_matrix(self, matrix, device_ids):
        """Public numerical entrypoint for original/synthetic continuous series QA."""
        import numpy as np
        from tigramite import data_processing as pp
        from tigramite.pcmci import PCMCI
        from tigramite.independence_tests.parcorr import ParCorr
        matrix = np.asarray(matrix, dtype=float)
        if matrix.ndim != 2 or matrix.shape[1] != len(device_ids) or not np.isfinite(matrix).all():
            raise ValueError("Invalid finite time-by-variable matrix")
        if len(matrix) <= 2 * self.config.tau_max + 4 or np.any(matrix.var(axis=0) < 1e-12):
            raise ValueError("Insufficient nonconstant time series")
        pcmci = PCMCI(dataframe=pp.DataFrame(matrix, var_names=device_ids), cond_ind_test=ParCorr(), verbosity=0)
        result = pcmci.run_pcmciplus(tau_min=0, tau_max=self.config.tau_max,
                                    pc_alpha=self.config.pc_alpha, max_conds_dim=self.config.max_conds_dim,
                                    conflict_resolution=True, fdr_method="none")
        graph, values, pvalues = result["graph"], result["val_matrix"], result["p_matrix"]
        edges = []
        for i, u in enumerate(device_ids):
            for j, v in enumerate(device_ids):
                for lag in range(self.config.tau_max + 1):
                    mark = str(graph[i, j, lag])
                    if not mark or (lag == 0 and (mark == "<--" or mark != "-->" and j <= i)):
                        continue
                    if mark != "-->" and lag > 0:
                        # Unexpected lagged ambiguity stays undirected, never guessed.
                        directed = False
                    else:
                        directed = mark == "-->"
                    val, pval = float(values[i, j, lag]), float(pvalues[i, j, lag])
                    if not np.isfinite(val) or not np.isfinite(pval):
                        raise FloatingPointError("Non-finite CI statistic on selected relation")
                    edges.append({"source": u, "target": v, "directed": directed, "lag": lag,
                                  "score": abs(val), "signed_statistic": val, "p_value": pval,
                                  "orientation_mark": mark, "evidence_ids": [f"series:{u}", f"series:{v}"],
                                  "score_semantics": "absolute ParCorr statistic, not probability"})
        return {"nodes": [{"id": d, "device_id": d} for d in device_ids], "edges": edges,
                "native_arrays": {"graph": graph.tolist(), "val_matrix": values.tolist(), "p_matrix": pvalues.tolist()},
                "diagnostics": {"tigramite_version": importlib.metadata.version("tigramite"), "unoriented_edges": sum(not e["directed"] for e in edges),
                                "rows": len(matrix), "variables": len(device_ids), "ci_test": "ParCorr linear continuous approximation"}}

    def predict_raw_graph(self, incident):
        start = time.perf_counter()
        result = {"case_id": incident["case_id"], "method": self.method, "version": self.version, "status": "ok", "nodes": [], "edges": [], "root_ranking": [], "diagnostics": {"config": asdict(self.config), "input_contract_version": "baseline-incident-v1"}}
        try:
            c = self.config
            matrix, ids, audit = dense_input(incident, bin_seconds=c.bin_seconds, mode=c.mode,
                                           min_bins=c.min_bins, max_variables=c.max_variables, require_coverage=c.require_coverage)
            result["diagnostics"].update(input_audit=audit, fit_protocol="per_incident_unlabeled")
            found = self.discover_matrix(matrix, ids)
            result.update(found)
            result["diagnostics"].update(config=asdict(c), input_audit=audit, fit_protocol="per_incident_unlabeled", input_contract_version="baseline-incident-v1")
        except ValueError as exc:
            result.update(status="input_ineligible", reason=str(exc))
        except (ImportError, RuntimeError, FloatingPointError) as exc:
            result.update(status="runtime_failure", reason=f"{type(exc).__name__}: {exc}")
        result["timing"] = {"prediction_seconds": time.perf_counter() - start}
        return result
