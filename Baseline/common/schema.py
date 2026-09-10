from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA_VERSION = "baseline-incident-v1"
PREDICTION_VERSION = "baseline-prediction-v1"
STATUSES = {"ok", "abstained", "input_ineligible", "runtime_failure", "unsupported_task"}


def timezone_info(name="Asia/Shanghai"):
    # Windows does not always ship an IANA database. These fixed zones suffice
    # for the modern incident data; historical civil-time conversion uses IANA.
    if name in ("UTC", "Z", "+00:00"):
        return dt_timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name == "Asia/Shanghai":
            return dt_timezone(timedelta(hours=8))
        raise ValueError(f"Timezone database unavailable for {name!r}") from None


def parse_timestamp(value, timezone="Asia/Shanghai"):
    """Return epoch seconds or None. Numeric epochs may be s, ms, us or ns."""
    if value is None or isinstance(value, bool) or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip()
        try:
            number = float(text)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00").replace("/", "-"))
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone_info(timezone))
            return parsed.timestamp()
    if not math.isfinite(number):
        return None
    magnitude = abs(number)
    divisor = 1e9 if magnitude >= 1e17 else 1e6 if magnitude >= 1e14 else 1e3 if magnitude >= 1e11 else 1
    try:
        datetime.fromtimestamp(number / divisor, dt_timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None
    return number / divisor


def iso_timestamp(value, timezone="Asia/Shanghai"):
    seconds = parse_timestamp(value, timezone)
    return datetime.fromtimestamp(seconds, dt_timezone.utc).isoformat() if seconds is not None else None


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_incident(incident):
    if not isinstance(incident, dict) or not incident.get("case_id"):
        raise ValueError("Incident needs a case_id")
    devices = incident.get("devices", [])
    ids = [row.get("id") for row in devices]
    if not ids or any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("Device IDs must be nonempty, unique strings")
    ids = set(ids)
    for edge in incident.get("physical_links", []):
        if edge.get("u") not in ids or edge.get("v") not in ids or edge["u"] == edge["v"]:
            raise ValueError("Physical link endpoints must be distinct candidate devices")
    window = incident.get("window", {})
    tz = window.get("timezone", "Asia/Shanghai")
    start, end, cutoff = [parse_timestamp(window.get(key), tz) for key in ("start", "end", "cutoff")]
    if None in (start, end, cutoff) or not start <= cutoff <= end or start == end:
        raise ValueError("Window must have start < end and start <= cutoff <= end")
    seen = set()
    for event in incident.get("events", []):
        if event.get("device_id") not in ids or not event.get("event_id") or not event.get("event_type"):
            raise ValueError("Event needs known device_id, event_id and event_type")
        if event["event_id"] in seen:
            raise ValueError("Event IDs must be unique after exact-record deduplication")
        seen.add(event["event_id"])
        t = parse_timestamp(event.get("event_time"), tz)
        recorded = parse_timestamp(event.get("record_time"), tz)
        if (t is not None and not start <= t <= cutoff) or (recorded is not None and recorded > cutoff):
            raise ValueError("Event is outside the permitted observation window")
    return incident


def input_fingerprint(incident):
    return stable_hash({key: incident.get(key) for key in ("window", "devices", "physical_links", "events", "endpoint_context", "observation_coverage")})
