"""Fold-local NEC training, evidence-only incident encoding, and native predictions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import time
from typing import Any

import torch

from .model import ODERNNPointProcess

METHOD = "NetEventCause-ODE-reimpl-Device-prior-calibrated-adapt"
VERSION = "0.1.0"


@dataclass
class NECConfig:
    hidden_size: int = 32
    embedding_size: int = 16
    time_unit_seconds: float = 60.0
    ode_step: float = 0.25
    max_ode_steps: int = 4096
    epochs: int = 30
    learning_rate: float = 0.001
    regularization_weight: float = 1.0
    gradient_clip: float = 5.0
    rho: float = 0.1
    root_threshold: float = 0.2
    top_k_causes: int = 5
    ig_steps: int = 32
    seed: int = 2027
    max_events: int = 2000
    sources: tuple[str, ...] = ("alarm", "alert")

    def validate(self):
        for name in ("time_unit_seconds", "ode_step", "learning_rate", "gradient_clip"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("epochs", "hidden_size", "embedding_size", "max_ode_steps",
                     "top_k_causes", "ig_steps", "max_events"):
            if not isinstance(getattr(self, name), int) or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not (0 < self.rho <= 1) or not (0 <= self.root_threshold <= 1):
            raise ValueError("rho must be in (0,1]; root_threshold in [0,1]")
        if not math.isfinite(self.regularization_weight) or self.regularization_weight <= 0:
            raise ValueError("The NEC empty-history regularizer must be enabled")
        if not self.sources:
            raise ValueError("At least one event source must be declared")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _timestamp(value: Any, timezone: str):
    # Public contract; labels and model-derived evidence are never read here.
    from Baseline.common.schema import parse_timestamp
    return parse_timestamp(value, timezone)


def _type_key(event_type: Any, device_type: Any) -> str:
    return json.dumps([str(event_type or "UNK"), str(device_type or "UNK")],
                      ensure_ascii=False, separators=(",", ":"))


class NetEventCauseDevice:
    """Cross-incident learner; fit is the only operation that changes parameters.

    Root/device labels are deliberately unused. rho is an engineering prior set
    before fit. No event-root supervision or root-label-to-alarm conversion occurs.
    """
    method = METHOD
    version = VERSION
    capabilities = {"root": True, "native_graph": True,
                    "device_graph": "requires common device adapter"}

    def __init__(self, config: NECConfig | dict | None = None, device: str = "cpu"):
        self.config = config if isinstance(config, NECConfig) else NECConfig(**(config or {}))
        self.config.validate()
        self.device = torch.device(device)
        self.vocabulary: dict[str, int] = {"<UNK>": 0}
        self.model: ODERNNPointProcess | None = None
        self.prior: torch.Tensor | None = None
        self.training_report: dict = {}
        self._fitted = False

    def _encode_observations(self, incident: dict) -> dict:
        window = incident.get("window", {})
        timezone = window.get("timezone", "Asia/Shanghai")
        start = _timestamp(window.get("start"), timezone)
        end = _timestamp(window.get("end"), timezone)
        cutoff = _timestamp(window.get("cutoff"), timezone)
        if start is None or end is None or cutoff is None:
            raise ValueError("Valid observation start, end, and cutoff timestamps are required")
        end = min(end, cutoff)
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            raise ValueError("Observation interval is empty or invalid")
        devices = {str(d["id"]): d.get("type") for d in incident.get("devices", [])}
        if not devices:
            raise ValueError("Candidate device set is empty")
        events = []
        skipped = []
        seen = set()
        missing_record_time = 0
        for event in incident.get("events", []):
            event_id = str(event.get("event_id", ""))
            device_id = str(event.get("device_id", ""))
            reason = None
            if event.get("source") not in self.config.sources:
                reason = "source_not_enabled"
            elif not event_id:
                reason = "missing_event_id"
            elif event_id in seen:
                reason = "duplicate_event_id"
            elif device_id not in devices:
                reason = "device_outside_candidate_set"
            event_time = _timestamp(event.get("event_time"), timezone)
            record_time = _timestamp(event.get("record_time"), timezone)
            if reason is None and event_time is None:
                reason = "missing_or_invalid_event_time"
            if reason is None and not (start <= event_time <= end):
                reason = "event_outside_allowed_window"
            if reason is None and record_time is not None and record_time > cutoff:
                reason = "recorded_after_cutoff"
            if reason:
                skipped.append({"event_id": event_id, "reason": reason})
                continue
            seen.add(event_id)
            missing_record_time += int(record_time is None)
            events.append({"event_id": event_id, "device_id": device_id,
                           "time": (event_time - start) / self.config.time_unit_seconds,
                           "event_time": event.get("event_time"),
                           "record_time": event.get("record_time"),
                           "type_key": _type_key(event.get("event_type"), devices[device_id])})
        if len(events) > self.config.max_events:
            raise ValueError(f"{len(events)} events exceed declared max_events={self.config.max_events}; no truncation")
        events.sort(key=lambda e: (e["time"], e["event_id"]))
        counts: dict[float, int] = {}
        for event in events:
            counts[event["time"]] = counts.get(event["time"], 0) + 1
        simultaneous = sum(count for count in counts.values() if count > 1)
        return {"case_id": str(incident.get("case_id", "")),
                "group_id": str(incident.get("group_id", incident.get("case_id", ""))),
                "devices": sorted(devices), "events": events,
                "duration": (end - start) / self.config.time_unit_seconds,
                "diagnostics": {"skipped_events": skipped, "valid_events": len(events),
                                "missing_record_time": missing_record_time,
                                "simultaneous_events": simultaneous,
                                "simultaneous_fraction": simultaneous / max(1, len(events)),
                                "source_policy": list(self.config.sources),
                                "coverage_interpretation": "absence of events is not evidence of normality"}}

    def _tensors(self, encoded: dict):
        events = encoded["events"]
        types = torch.tensor([self.vocabulary.get(e["type_key"], 0) for e in events],
                             dtype=torch.long, device=self.device)
        return [e["time"] for e in events], types

    def _make_model(self):
        c = self.config
        return ODERNNPointProcess(len(self.vocabulary), c.hidden_size, c.embedding_size,
                                  c.ode_step, c.max_ode_steps).to(self.device)

    def fit(self, train_cases, train_labels=None, validation_cases=None, validation_labels=None):
        started = time.perf_counter()
        self._fitted = False
        self.training_report = {}
        c = self.config
        train = [self._encode_observations(case) for case in train_cases]
        validation = [self._encode_observations(case) for case in (validation_cases or [])]
        if not train or not sum(len(case["events"]) for case in train):
            raise ValueError("Training requires at least one eligible observed event")
        ids = [case["case_id"] for case in train]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate training case_id")
        if {x["group_id"] for x in train} & {x["group_id"] for x in validation}:
            raise ValueError("Train and validation incident groups overlap")
        keys = sorted({event["type_key"] for case in train for event in case["events"]})
        self.vocabulary = {"<UNK>": 0, **{key: i + 1 for i, key in enumerate(keys)}}
        duration = sum(case["duration"] for case in train)
        counts = torch.zeros(len(self.vocabulary), dtype=torch.float32, device=self.device)
        for case in train:
            for event in case["events"]:
                counts[self.vocabulary[event["type_key"]]] += 1
        self.prior = c.rho * counts / duration
        # Model initialization and case shuffle are fold-local and reproducible.
        torch.manual_seed(c.seed)
        self.model = self._make_model()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=c.learning_rate)
        rng = random.Random(c.seed)
        history = []
        best_nll = math.inf
        best_state = None
        for epoch in range(c.epochs):
            order = list(range(len(train)))
            rng.shuffle(order)
            values = {"loss": 0.0, "nll": 0.0, "empty_history_regularizer": 0.0}
            self.model.train()
            for index in order:
                case = train[index]
                times, types = self._tensors(case)
                optimizer.zero_grad(set_to_none=True)
                loss, terms = self.model.loss(times, types, case["duration"], self.prior,
                                              c.regularization_weight)
                loss.backward()
                norm = torch.nn.utils.clip_grad_norm_(self.model.parameters(), c.gradient_clip,
                                                     error_if_nonfinite=True)
                if not torch.isfinite(norm):
                    raise FloatingPointError("Non-finite training gradient")
                optimizer.step()
                values["loss"] += float(loss.detach())
                for key in ("nll", "empty_history_regularizer"):
                    values[key] += float(terms[key].detach())
            record = {"epoch": epoch + 1, **{k: v / len(train) for k, v in values.items()}}
            if validation:
                self.model.eval()
                with torch.no_grad():
                    nll = sum(float(self.model.loss(*self._tensors(case), case["duration"],
                                                   self.prior, c.regularization_weight)[1]["nll"])
                              for case in validation) / len(validation)
                record["validation_nll"] = nll
                if nll < best_nll:
                    best_nll = nll
                    best_state = copy.deepcopy(self.model.state_dict())
            history.append(record)
        if best_state is not None:
            self.model.load_state_dict(best_state)
        self.model.eval()
        self.training_report = {
            "method": METHOD, "version": VERSION, "config": asdict(c),
            "train_case_ids": ids, "train_group_ids": sorted({x["group_id"] for x in train}),
            "validation_case_ids": [x["case_id"] for x in validation],
            "input_manifest_sha256": _hash(train),
            "vocabulary_sha256": _hash(self.vocabulary),
            "train_duration_model_units": duration,
            "observed_type_counts": counts.cpu().tolist(),
            "prior": self.prior.cpu().tolist(),
            "prior_source": "fixed_rho_times_train_event_count_over_observed_duration",
            "supervision": "none; root and device labels are not used",
            "selection": "minimum validation NLL" if validation else "last training epoch",
            "history": history, "seconds": time.perf_counter() - started,
            "torch_version": str(torch.__version__),
            "source_hashes": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                              for name in ("model.py", "predictor.py")}}
        self._fitted = True
        return self

    def _base(self, incident):
        return {"case_id": str(incident.get("case_id", "")), "method": METHOD,
                "version": VERSION, "seed": self.config.seed}

    def _event_predictions(self, encoded: dict, with_graph: bool):
        if not self._fitted or self.model is None or self.prior is None:
            raise RuntimeError("No fitted checkpoint; call fit or load before prediction")
        times, types = self._tensors(encoded)
        self.model.eval()
        with torch.no_grad():
            logs, _, _ = self.model.trajectory(times, self.model.embedding(types),
                                               encoded["duration"], False)
        events = encoded["events"]
        nodes, edges, anomalies = [], [], []
        for i, event in enumerate(events):
            event_type = int(types[i])
            node = {"id": event["event_id"], "device_id": event["device_id"],
                    "event_time": event["event_time"], "record_time": event["record_time"],
                    "type_key": event["type_key"], "type_id": event_type,
                    "conditional_intensity": None, "root_score": None,
                    "event_class": "unscored_unknown_type", "causes": []}
            if event_type == 0:
                nodes.append(node)
                continue
            log_intensity = float(logs[i, event_type])
            intensity = math.exp(log_intensity)
            score = float(self.prior[event_type]) / intensity
            if not math.isfinite(intensity) or intensity <= 0 or not math.isfinite(score):
                raise FloatingPointError("Non-finite/zero intensity or root ratio")
            node.update(conditional_intensity=intensity, root_score=score,
                        prior_intensity=float(self.prior[event_type]),
                        event_class="root" if score >= self.config.root_threshold else "derivative")
            if score > 1:
                anomalies.append({"event_id": event["event_id"],
                                  "reason": "prior_exceeds_conditional_intensity", "raw_ratio": score})
            if with_graph and node["event_class"] == "derivative":
                history_indices = [j for j in range(i) if times[j] < times[i]]
                contributions, ig_info = self.model.integrated_gradients(
                    [times[j] for j in history_indices], types[history_indices],
                    times[i], event_type, self.config.ig_steps)
                node["ig_diagnostics"] = ig_info
                node["history_contributions"] = [
                    {"event_id": events[j]["event_id"], "score": value}
                    for j, value in zip(history_indices, contributions)]
                positive = [(value, j) for j, value in zip(history_indices, contributions) if value > 0]
                positive.sort(key=lambda pair: (-pair[0], events[pair[1]]["event_id"]))
                for value, j in positive[:self.config.top_k_causes]:
                    cause_id = events[j]["event_id"]
                    node["causes"].append({"event_id": cause_id, "score": value})
                    edges.append({"source": cause_id, "target": event["event_id"],
                                  "score": value, "directed": True,
                                  "evidence_ids": [cause_id, event["event_id"]],
                                  "score_semantics": "positive signed IG of target log intensity"})
                if not node["causes"]:
                    node["diagnostic"] = "derivative_without_positive_attributed_history"
            nodes.append(node)
        return nodes, edges, anomalies

    def _predict(self, incident: dict, with_graph: bool):
        started = time.perf_counter()
        output = {**self._base(incident), "status": "ok", "root_ranking": [],
                  "diagnostics": {}, "timing": {}}
        if with_graph:
            output.update(nodes=[], edges=[], graph_kind="event_dependency_hypotheses")
        try:
            encoded = self._encode_observations(incident)
            output["diagnostics"] = encoded["diagnostics"]
            nodes, edges, anomalies = self._event_predictions(encoded, with_graph)
            scored = {}
            support = {}
            for node in nodes:
                score = node["root_score"]
                if score is not None:
                    d = node["device_id"]
                    if d not in scored or score > scored[d]:
                        scored[d] = score
                        support[d] = node["id"]
            order = sorted(encoded["devices"], key=lambda d: (d not in scored, -scored.get(d, 0), d))
            output["root_ranking"] = [
                {"device_id": d, "score": scored.get(d),
                 "score_semantics": "max raw prior/intensity ratio; uncalibrated",
                 "support_event_id": support.get(d),
                 "scorable": d in scored} for d in order]
            if not scored:
                output["status"] = "abstained"
                output["diagnostics"]["reason"] = "no_events_with_train_known_types"
            output["diagnostics"].update(
                intensity_unit=f"events per {self.config.time_unit_seconds:g} seconds",
                prior_source="fixed_rho_from_training_only",
                ratio_anomalies=anomalies,
                unknown_type_events=sum(n["type_id"] == 0 for n in nodes),
                unscored_devices=[d for d in order if d not in scored],
                root_threshold=self.config.root_threshold,
                top_k_causes=self.config.top_k_causes,
                ig_steps=self.config.ig_steps,
                evidence_sha256=_hash(encoded))
            if with_graph:
                output.update(nodes=nodes, edges=edges)
            else:
                output["event_scores"] = nodes
        except ValueError as exc:
            output["status"] = "input_ineligible"
            output["diagnostics"]["reason"] = str(exc)
        except (RuntimeError, FloatingPointError, OverflowError, ZeroDivisionError) as exc:
            output["status"] = "runtime_failure"
            output["diagnostics"]["reason"] = str(exc)
        output["timing"]["prediction_seconds"] = time.perf_counter() - started
        return output

    def predict_root(self, incident: dict):
        return self._predict(incident, False)

    def predict_raw_graph(self, incident: dict):
        return self._predict(incident, True)

    def save(self, path: str | Path):
        if not self._fitted or self.model is None or self.prior is None:
            raise RuntimeError("Cannot save an unfitted model")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"version": VERSION, "method": METHOD, "config": asdict(self.config),
                    "vocabulary": self.vocabulary, "prior": self.prior.detach().cpu(),
                    "state_dict": {k: v.detach().cpu() for k, v in self.model.state_dict().items()},
                    "training_report": self.training_report}, path)
        path.with_suffix(path.suffix + ".json").write_text(
            json.dumps(self.training_report, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path, device: str = "cpu"):
        state = torch.load(path, map_location=device, weights_only=True)
        if state.get("version") != VERSION or state.get("method") != METHOD:
            raise ValueError("Unsupported NEC checkpoint identity/version")
        instance = cls(state["config"], device=device)
        instance.vocabulary = state["vocabulary"]
        instance.prior = state["prior"].to(instance.device)
        instance.model = instance._make_model()
        instance.model.load_state_dict(state["state_dict"])
        instance.model.eval()
        instance.training_report = state["training_report"]
        instance._fitted = True
        return instance
