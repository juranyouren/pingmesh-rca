"""One shared decision about whether incident timestamps can order events.

A raw timestamp being present does not make it usable for causal ordering.
Source stamps are frequently written at *collection* time: one collector read
stamps the same instant onto every record it ingests, so a "gap" between two
records' timestamps measures the collector's polling cadence, not the fault.

Both evidence paths - the LLM encoder and the rule-based canonicaliser - consume
the assessment produced here, so the two cannot disagree about the same field.

The assessment is deliberately **one-sided**: it may downgrade timestamps to
unusable, but it can never promote an unverified timestamp to verified. Only an
explicit source declaration does that, and even a declaration loses to a
detected batch signature. This asymmetry is what makes a heuristic detector
acceptable - a false positive costs nothing, because the temporal axis is
already off, while a false negative merely preserves the conservative default.

Verified event times are represented but not granted by default: no source in
this repository currently declares them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Sequence

TIME_QUALITY_VERIFIED = "verified_event_timestamp"
TIME_QUALITY_BATCH = "batch_snapshot"
TIME_QUALITY_UNVERIFIED = "unverified_source_timestamp"
TIME_QUALITY_MISSING = "missing"

REASON_BATCH = "batch_snapshot_timestamps"
REASON_UNVERIFIED = "unverified_source_timestamp"
REASON_MISSING = "timestamp_missing"
REASON_VERIFIED = "source_declares_event_times"

VERIFIED_TIME_SCORE = 1.0

# A stamp repeated this many times on one device is a write, not a coincidence.
DEFAULT_DUPLICATE_MIN_RECORDS = 2
# Independent devices failing within this window of each other is a collector.
DEFAULT_COINCIDENCE_WINDOW_MS = 1_000
DEFAULT_COINCIDENCE_MIN_DEVICES = 3
# Devices must cluster this many times more tightly than the incident's own
# extent before the clustering reads as a shared write rather than a fault.
DEFAULT_COINCIDENCE_SPAN_RATIO = 20.0


@dataclass(frozen=True)
class TimeObservation:
    """One raw record's timestamp, contextualised by its device."""

    time_ms: int | None
    device_id: str = ""
    key: str = ""


@dataclass(frozen=True)
class TimeQualityAssessment:
    quality: str
    score: float
    reason: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return float(self.score) > 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time_quality": self.quality,
            "time_reason": self.reason,
            "time_score": round(float(self.score), 6),
            "usable": self.usable,
            "evidence": dict(self.evidence),
        }


def _coerce(observation: Any) -> TimeObservation | None:
    if isinstance(observation, TimeObservation):
        return observation
    if isinstance(observation, Mapping):
        return TimeObservation(
            time_ms=observation.get("time_ms"),
            device_id=str(observation.get("device_id", "") or ""),
            key=str(observation.get("key", "") or ""),
        )
    return None


def _coerce_time(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _duplicate_signature(
    by_device: Mapping[str, Sequence[int]], min_records: int
) -> Dict[str, Any] | None:
    """A device stamping several records with one instant is being batch-written.

    A device with fewer distinct stamps than records cannot have observed each
    of them separately. This is a downgrade only: two alarms genuinely sharing a
    millisecond costs us a temporal axis that was already switched off.
    """

    for device_id in sorted(by_device):
        times = by_device[device_id]
        counts: Dict[int, int] = {}
        for value in times:
            counts[value] = counts.get(value, 0) + 1
        repeated = sorted(value for value, count in counts.items() if count >= min_records)
        if repeated:
            return {
                "detector": "repeated_timestamp_within_device",
                "device_id": device_id,
                "repeated_time_ms": repeated[0],
                "repeated_count": counts[repeated[0]],
                "distinct_times_on_device": len(counts),
            }
    return None


def _coincidence_signature(
    timed: Sequence[TimeObservation],
    window_ms: int,
    min_devices: int,
    span_ratio: float,
) -> Dict[str, Any] | None:
    """Several devices sharing one instant is a collector, not a fault.

    The test is relative, not absolute: devices are flagged when they cluster
    far more tightly than the incident's own time extent. An incident that is
    itself contained in a single instant carries no evidence either way.
    """

    ordered = sorted(timed, key=lambda item: (item.time_ms, item.device_id))
    span = ordered[-1].time_ms - ordered[0].time_ms
    if span <= 0:
        return None
    best: Dict[str, Any] | None = None
    start = 0
    for end in range(len(ordered)):
        while ordered[end].time_ms - ordered[start].time_ms > window_ms:
            start += 1
        devices = {ordered[index].device_id for index in range(start, end + 1)}
        if len(devices) < min_devices:
            continue
        if best is not None and len(devices) <= len(best["coincident_devices"]):
            continue
        window = [ordered[index] for index in range(start, end + 1)]
        coincidence_span = window[-1].time_ms - window[0].time_ms
        if coincidence_span * span_ratio > span:
            continue
        best = {
            "detector": "near_simultaneous_across_devices",
            "coincident_devices": sorted(devices),
            "coincidence_span_ms": coincidence_span,
            "incident_span_ms": span,
            "window_ms": window_ms,
        }
    return best


def assess_time_quality(
    observations: Iterable[Any],
    *,
    source_declares_event_times: bool = False,
    duplicate_min_records: int = DEFAULT_DUPLICATE_MIN_RECORDS,
    coincidence_window_ms: int = DEFAULT_COINCIDENCE_WINDOW_MS,
    coincidence_min_devices: int = DEFAULT_COINCIDENCE_MIN_DEVICES,
    coincidence_span_ratio: float = DEFAULT_COINCIDENCE_SPAN_RATIO,
) -> TimeQualityAssessment:
    """Decide whether this incident's timestamps may order events.

    Resolution order, strongest evidence first:

    1. no timestamps at all -> ``missing``;
    2. a batch-collection signature -> ``batch_snapshot`` (unusable);
    3. an explicit ``source_declares_event_times`` -> ``verified_event_timestamp``
       (usable);
    4. otherwise -> ``unverified_source_timestamp`` (unusable).

    Step 3 sits below step 2 on purpose: a declaration cannot overrule evidence
    that the stamps are collection instants.
    """

    timed: List[TimeObservation] = []
    total = 0
    for raw in observations:
        observation = _coerce(raw)
        if observation is None:
            continue
        total += 1
        value = _coerce_time(observation.time_ms)
        if value is not None:
            timed.append(TimeObservation(value, str(observation.device_id or ""), observation.key))

    if not timed:
        return TimeQualityAssessment(
            quality=TIME_QUALITY_MISSING,
            score=0.0,
            reason=REASON_MISSING,
            evidence={"observation_count": total, "timed_observation_count": 0},
        )

    by_device: Dict[str, List[int]] = {}
    for observation in timed:
        by_device.setdefault(observation.device_id, []).append(observation.time_ms)

    base_evidence: Dict[str, Any] = {
        "observation_count": total,
        "timed_observation_count": len(timed),
        "device_count": len(by_device),
        "distinct_times": len({observation.time_ms for observation in timed}),
        "span_ms": max(observation.time_ms for observation in timed)
        - min(observation.time_ms for observation in timed),
    }

    signature = _duplicate_signature(by_device, duplicate_min_records) or _coincidence_signature(
        timed, coincidence_window_ms, coincidence_min_devices, coincidence_span_ratio
    )
    if signature is not None:
        return TimeQualityAssessment(
            quality=TIME_QUALITY_BATCH,
            score=0.0,
            reason=REASON_BATCH,
            evidence={**base_evidence, **signature},
        )

    if source_declares_event_times:
        return TimeQualityAssessment(
            quality=TIME_QUALITY_VERIFIED,
            score=VERIFIED_TIME_SCORE,
            reason=REASON_VERIFIED,
            evidence=base_evidence,
        )

    return TimeQualityAssessment(
        quality=TIME_QUALITY_UNVERIFIED,
        score=0.0,
        reason=REASON_UNVERIFIED,
        evidence=base_evidence,
    )
