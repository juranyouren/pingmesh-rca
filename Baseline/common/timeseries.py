from __future__ import annotations

import math
from collections import Counter

from .schema import iso_timestamp, parse_timestamp, validate_incident


def build_timeseries(incident, bin_seconds=10, mode="count", require_coverage=True, max_bins=10000):
    """Unknown bins are None. Coverage is explicit collection coverage, not health."""
    validate_incident(incident)
    if not math.isfinite(bin_seconds) or bin_seconds <= 0 or mode not in {"count", "binary", "log1p"}:
        raise ValueError("Invalid bin width or transformation")
    tz = incident["window"].get("timezone", "Asia/Shanghai")
    start = parse_timestamp(incident["window"]["start"], tz)
    end = parse_timestamp(incident["window"]["cutoff"], tz)
    n_bins = max(1, math.ceil((end - start) / bin_seconds))
    ids = [d["id"] for d in incident["devices"]]
    base = {"device_ids": ids, "start": iso_timestamp(start), "bin_seconds": bin_seconds, "mode": mode,
            "values": [], "mask": [], "diagnostics": {"n_bins": n_bins, "n_devices": len(ids)}}
    if n_bins > max_bins:
        return {**base, "status": "input_ineligible", "reason": "bin_budget_exceeded"}
    coverage = incident.get("observation_coverage")
    complete = isinstance(coverage, dict) and coverage.get("complete") is True
    ranges = coverage.get("intervals", []) if isinstance(coverage, dict) else []
    coverage_unverified = require_coverage and not complete and not ranges
    index = {d: i for i, d in enumerate(ids)}
    masks = [[not complete for _ in ids] for _ in range(n_bins)]
    if not require_coverage and not complete and not ranges:
        masks = [[False for _ in ids] for _ in range(n_bins)]
        base["diagnostics"]["coverage_assumption"] = "record_count_only_zero_is_not_health"
    for interval in ranges:
        u, v = parse_timestamp(interval.get("start"), tz), parse_timestamp(interval.get("end"), tz)
        selected = interval.get("device_ids", ids)
        if u is None or v is None or u > v:
            raise ValueError("Invalid collection coverage interval")
        if not isinstance(selected, list) or not set(selected) <= set(ids):
            raise ValueError("Coverage references unknown devices")
        for b in range(n_bins):
            if u <= start + b * bin_seconds and min(end, start + (b + 1) * bin_seconds) <= v:
                for device in selected:
                    if device in index:
                        masks[b][index[device]] = False
    counts = [[0.0 for _ in ids] for _ in range(n_bins)]
    unknown_times = 0
    timestamps = []
    for event in incident["events"]:
        t = parse_timestamp(event.get("event_time"), tz)
        if t is None:
            unknown_times += 1
            continue
        timestamps.append(t)
        b = min(n_bins - 1, int((t - start) / bin_seconds))
        counts[b][index[event["device_id"]]] += 1.0
    values = [[None if masks[b][i] else (int(x > 0) if mode == "binary" else math.log1p(x) if mode == "log1p" else x)
               for i, x in enumerate(row)] for b, row in enumerate(counts)]
    stats = []
    for i, device in enumerate(ids):
        observed = [row[i] for row in values if row[i] is not None]
        avg = sum(observed) / len(observed) if observed else None
        variance = sum((x - avg) ** 2 for x in observed) / len(observed) if observed else None
        stats.append({"device_id": device, "observed_bins": len(observed), "nonzero_bins": sum(x > 0 for x in observed), "variance": variance})
    base.update(values=values, mask=masks, status="ok")
    if coverage_unverified:
        base.update(status="input_ineligible", reason="collection_coverage_unknown")
    base["diagnostics"].update({"unknown_event_times": unknown_times, "unique_event_times": len(set(timestamps)),
                                "missing_fraction": sum(sum(row) for row in masks) / (n_bins * len(ids)),
                                "nonempty_bin_fraction": sum(any(row) for row in counts) / n_bins,
                                "variables": stats})
    return base


def audit_incident(incident):
    counts = Counter(e["source"] for e in incident["events"])
    series = build_timeseries(incident)
    return {"case_id": incident["case_id"], "devices": len(incident["devices"]), "physical_links": len(incident["physical_links"]),
            "event_counts": dict(counts), "group_verified": incident.get("group_verified", False),
            "unknown_event_times": sum(e.get("event_time") is None for e in incident["events"]),
            "unknown_record_times": sum(e.get("record_time") is None for e in incident["events"]),
            "input_diagnostics": incident.get("input_diagnostics", {}),
            "timeseries": {key: series[key] for key in ("status", "diagnostics", "reason") if key in series},
            "conditional_baselines": {"REASON": "requires verified hierarchy and KPI series", "CORAL": "requires continuous metrics/KPI history and online state",
                                       "NetCause": "requires observed fault/action states and impact timing"}}


def dense_input(incident, *, bin_seconds=10, mode="log1p", min_bins=30, max_variables=50, require_coverage=True):
    import numpy as np
    series = build_timeseries(incident, bin_seconds, mode, require_coverage)
    if series["status"] != "ok":
        raise ValueError(series["reason"])
    if any(any(row) for row in series["mask"]):
        raise ValueError("v1 requires a fully observed common window; no missing-value imputation")
    matrix = np.asarray(series["values"], dtype=float)
    if len(matrix) < min_bins:
        raise ValueError("too_few_time_bins")
    active = np.flatnonzero(matrix.var(axis=0) > 1e-12)
    if len(active) < 2:
        raise ValueError("fewer_than_two_nonconstant_device_series")
    if len(active) > max_variables:
        raise ValueError("variable_budget_exceeded; no score-based candidate trimming")
    ids = [series["device_ids"][i] for i in active]
    series["diagnostics"]["constant_devices"] = sorted(set(series["device_ids"]) - set(ids))
    return matrix[:, active], ids, series["diagnostics"]
