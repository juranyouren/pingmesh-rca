"""Paper algorithms and explicit device-level adaptations for RQ1."""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
import math

from Baseline.common.schema import parse_timestamp


class InputIneligible(ValueError):
    """Observed input cannot support this method; never silently fill with zeros."""


def result(case, edges, **extra):
    return {"case_id": case["case_id"], "status": "ok",
            "nodes": [{"id": d["id"], "device_id": d["id"]} for d in case["devices"]],
            "edges": edges, **extra}


def timed_events(case):
    tz = case["window"].get("timezone", "Asia/Shanghai")
    return [(t, e) for e in case["events"]
            if (t := parse_timestamp(e.get("event_time"), tz)) is not None]


class TimeOrder:
    method = "TimeOrder-first-observed-event"

    def __init__(self, config=None):
        self.config = {"tie_seconds": 0.0, "max_lag_seconds": 600.0, **(config or {})}
        if set(self.config) != {"tie_seconds", "max_lag_seconds"}:
            raise ValueError("Unknown TimeOrder configuration")
        if not (math.isfinite(self.config["tie_seconds"]) and
                math.isfinite(self.config["max_lag_seconds"]) and
                0 <= self.config["tie_seconds"] < self.config["max_lag_seconds"]):
            raise ValueError("Require 0 <= tie_seconds < finite max_lag_seconds")

    def predict_raw_graph(self, case):
        first = {}
        for t, event in sorted(timed_events(case), key=lambda x: (x[0], x[1]["event_id"])):
            first.setdefault(event["device_id"], (t, event["event_id"]))
        if len(first) < 2:
            raise InputIneligible("Fewer than two devices have timestamped observations")
        edges = []
        for link in case["physical_links"]:
            u, v = link["u"], link["v"]
            if u not in first or v not in first:
                continue
            if first[u][0] > first[v][0]:
                u, v = v, u
            lag = first[v][0] - first[u][0]
            if lag > self.config["max_lag_seconds"]:
                continue
            edges.append({"source": u, "target": v, "directed": lag > self.config["tie_seconds"],
                          "score": 1.0, "lag_seconds": lag,
                          "evidence_ids": [first[u][1], first[v][1]]})
        return result(case, edges, method=self.method,
                      diagnostics={"onset": "first timestamped observed alarm/log; not proven fault onset",
                                   "devices_with_time": len(first)})


class PCMCI:
    """Actual PCMCI, using lagged links only; distinct from repository PCMCI+."""
    method = "PCMCI-ParCorr-lagged-device-adapt"

    def __init__(self, config=None):
        self.config = {"bin_seconds": 10.0, "mode": "log1p", "min_bins": 30,
                       "max_variables": 50, "tau_max": 2, "pc_alpha": 0.05,
                       "alpha_level": 0.01, "max_conds_dim": 3,
                       "require_coverage": True, **(config or {})}
        allowed = {"bin_seconds", "mode", "min_bins", "max_variables", "tau_max",
                   "pc_alpha", "alpha_level", "max_conds_dim", "require_coverage"}
        if set(self.config) != allowed:
            raise ValueError("Unknown PCMCI configuration")
        c = self.config
        if c["tau_max"] < 1 or not 0 < c["pc_alpha"] < 1 or not 0 < c["alpha_level"] < 1 or c["max_conds_dim"] < 0:
            raise ValueError("Invalid PCMCI lag/threshold/conditioning size")

    def predict_raw_graph(self, case):
        import numpy as np
        from tigramite import data_processing as pp
        from tigramite.pcmci import PCMCI as TigramitePCMCI
        from tigramite.independence_tests.parcorr import ParCorr
        from Baseline.common.timeseries import dense_input

        c = self.config
        try:
            matrix, ids, audit = dense_input(case, **{k: c[k] for k in
                ("bin_seconds", "mode", "min_bins", "max_variables", "require_coverage")})
        except ValueError as exc:
            raise InputIneligible(str(exc)) from exc
        if len(matrix) <= 2 * c["tau_max"] + 4:
            raise InputIneligible("Too few time bins for configured lag")
        model = TigramitePCMCI(dataframe=pp.DataFrame(matrix, var_names=ids),
                              cond_ind_test=ParCorr(), verbosity=0)
        found = model.run_pcmci(tau_min=1, tau_max=c["tau_max"], pc_alpha=c["pc_alpha"],
                               alpha_level=c["alpha_level"], max_conds_dim=c["max_conds_dim"],
                               fdr_method="none")
        p, val = found["p_matrix"], found["val_matrix"]
        if not np.isfinite(p).all() or not np.isfinite(val).all():
            raise FloatingPointError("Non-finite PCMCI statistics")
        edges = [{"source": u, "target": v, "directed": True, "lag": lag,
                  "p_value": float(p[i, j, lag]), "score": abs(float(val[i, j, lag])),
                  "evidence_ids": [f"series:{u}", f"series:{v}"]}
                 for i, u in enumerate(ids) for j, v in enumerate(ids) if i != j
                 for lag in range(1, c["tau_max"] + 1) if p[i, j, lag] <= c["alpha_level"]]
        return result(case, edges, method=self.method,
                      native_arrays={"variables": ids, "p_matrix": p.tolist(), "val_matrix": val.tolist()},
                      diagnostics={"input_audit": audit, "fit_protocol": "per_incident_unlabeled",
                                   "tau_min": 1, "contemporaneous_edges": "excluded", "fdr_method": "none"})


def thp_device_edges(case, events, event_types, matrix, max_lag_seconds):
    """Learned type i->j + observed earlier i on adjacent u supports u->v.

    TTPM's diagonal is forced to one, not a selected causal relation. Exclude
    diagonal links to avoid inventing same-type device propagation.
    """
    by_device = defaultdict(lambda: defaultdict(list))
    for t, event in events:
        by_device[event["device_id"]][event["event_type"]].append((t, event["event_id"]))
    for types in by_device.values():
        for rows in types.values():
            rows.sort()
    index = {name: i for i, name in enumerate(event_types)}
    edges = []
    for link in case["physical_links"]:
        for u, v in ((link["u"], link["v"]), (link["v"], link["u"])):
            evidence, relations, count = set(), set(), 0
            for source_type, sources in by_device[u].items():
                i = index[source_type]
                times = [r[0] for r in sources]
                for target_type, targets in by_device[v].items():
                    j = index[target_type]
                    if i == j or matrix[i][j] != 1:
                        continue
                    for target_time, target_id in targets:
                        pos = bisect_left(times, target_time) - 1
                        if pos >= 0 and target_time - times[pos] <= max_lag_seconds:
                            count += 1
                            evidence.update((sources[pos][1], target_id))
                            relations.add((source_type, target_type))
            if count:
                edges.append({"source": u, "target": v, "directed": True, "score": float(count),
                              "score_semantics": "number of supported target-event/type pairs; not probability",
                              "evidence_ids": sorted(evidence), "type_relations": sorted(relations)})
    return edges


class THP:
    """Cai et al. THP through gCastle TTPM, followed by explicit device mapping."""
    method = "THP-gCastle-TTPM-incident-type-to-device-adapt"

    def __init__(self, config=None):
        self.config = {"delta": 0.1, "epsilon": 1.0, "max_hop": 1, "penalty": "BIC",
                       "max_iter": 20, "max_event_types": 30, "max_events": 5000, "max_devices": 500,
                       "max_lag_seconds": 600.0, "seed": 20260920, **(config or {})}
        c = self.config
        if set(c) != {"delta", "epsilon", "max_hop", "penalty", "max_iter",
                      "max_event_types", "max_events", "max_devices", "max_lag_seconds", "seed"}:
            raise ValueError("Unknown THP configuration")
        if any(not math.isfinite(c[k]) or c[k] <= 0 for k in ("delta", "epsilon", "max_lag_seconds")):
            raise ValueError("THP requires positive finite decay, penalty and device mapping lag")
        if any(not isinstance(c[k], int) or c[k] < 1 for k in ("max_hop", "max_iter", "max_event_types", "max_events", "max_devices")) or c["penalty"] not in {"BIC", "AIC"}:
            raise ValueError("Invalid THP topology/search/size configuration")

    def predict_raw_graph(self, case):
        import numpy as np
        import pandas as pd
        from castle.algorithms import TTPM

        events = timed_events(case)
        types = sorted({e["event_type"] for _, e in events})
        if len(events) < 3 or len(types) < 2 or len({t for t, _ in events}) < 2:
            raise InputIneligible("THP needs >=3 timed events, >=2 types and nonzero time span")
        if len(types) > self.config["max_event_types"] or len(events) > self.config["max_events"]:
            raise InputIneligible("THP search size guard exceeded; no silent truncation")
        devices = [d["id"] for d in case["devices"]]
        if len(devices) > self.config["max_devices"]:
            raise InputIneligible("THP dense topology size guard exceeded; no silent truncation")
        index = {d: i for i, d in enumerate(devices)}
        topology = np.zeros((len(devices), len(devices)), dtype=int)
        for edge in case["physical_links"]:
            i, j = index[edge["u"]], index[edge["v"]]
            topology[i, j] = topology[j, i] = 1
        start = min(t for t, _ in events)
        data = pd.DataFrame([{"event": e["event_type"], "timestamp": t - start,
                              "node": index[e["device_id"]]} for t, e in events])
        model = TTPM(topology_matrix=topology, **{k: self.config[k] for k in
                     ("delta", "epsilon", "max_hop", "penalty", "max_iter")})
        state = np.random.get_state()
        try:
            np.random.seed(self.config["seed"])
            model.learn(data)
        finally:
            np.random.set_state(state)
        matrix = np.asarray(model.causal_matrix)
        names = [str(x) for x in model.causal_matrix.columns]
        if set(names) != set(types) or matrix.shape != (len(types), len(types)) or not np.isin(matrix, [0, 1]).all():
            raise RuntimeError("Unexpected gCastle TTPM matrix contract")
        edges = thp_device_edges(case, events, names, matrix, self.config["max_lag_seconds"])
        return result(case, edges, method=self.method,
                      type_graph={"event_types": names, "causal_matrix": matrix.astype(int).tolist()},
                      diagnostics={"fit_protocol": "per_incident_unlabeled", "time_unit": "seconds",
                                   "event_span_seconds": max(t for t, _ in events) - start,
                                   "type_graph_diagonal": "forced by upstream; excluded from device mapping",
                                   "device_adapter": "learned type edge + strict temporal order + raw adjacency",
                                   "upstream_limitations": "event-span exposure; topology restricted to event-bearing nodes"})


class Ours:
    """Current deterministic P0 stage 2, fed the same whitelisted observations."""
    method = "RPG-Recon-P0-common-input-fixed-root"

    def __init__(self, config=None):
        from Sys.RootCauseAnalyze.propagation.schema import normalize_config
        self.config = normalize_config(config).to_dict()
        if self.config["edge_probability_method"] != "deterministic_evidence_v1":
            raise ValueError("RQ1 Ours uses deterministic P0; supervised checkpoints need a separate OOF protocol")

    def predict_raw_graph(self, case, root):
        from Sys.RootCauseAnalyze.propagation.reconstruct import reconstruct_propagation
        from Sys.RootCauseAnalyze.propagation.topology_context import build_topology_context

        nodes = {d["id"]: {"mgmt_ip": d["id"], "devicetype": d.get("type", "UNK"),
                            "alarms": [], "logs": []} for d in case["devices"]}
        for event in case["events"]:
            row = {"alarm_name": event["event_type"], "alarm_time": event.get("event_time"),
                   "message": event.get("message"), "event_id": event["event_id"]}
            peers = event.get("related_device_ids", [])
            if peers:
                row["message"] = (row["message"] or "") + " peer=" + peers[0]
            key = "logs" if event["source"] == "log" else "alarms"
            nodes[event["device_id"]][key].append(row)
        info = dict(case["endpoint_context"])
        trigger = parse_timestamp(info.get("alarm_time"), case["window"].get("timezone", "Asia/Shanghai"))
        if trigger is not None:
            info["alarm_time"] = int(trigger * 1000)
        segment = {"nodes": list(nodes.values()), "links": [
            {"src_ip": e["u"], "dst_ip": e["v"]} for e in case["physical_links"]]}
        context = build_topology_context([[segment]], info)
        output = reconstruct_propagation(nodes=list(nodes.values()), info=info,
                                         topology_context=context, root_rankings=[root], config=self.config)
        graph = output["stage2"]["m2"]["selected_propagation_graph"]
        edges = [{**e, "source": e["from"], "target": e["to"], "directed": True,
                  "score": e.get("support_score", 1.0)} for e in graph.get("edges", [])]
        return result(case, edges, method=self.method, stage2=output["stage2"],
                      diagnostics={"input_adapter": "common whitelisted observations; raw device adjacency",
                                   "root_condition": root, "variant": "deterministic P0, no external LLM"})
