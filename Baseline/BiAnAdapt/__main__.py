"""Standalone runner; it can call a real local model or record its failure."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

from Baseline.common.io import dump_json, load_incidents
from .pipeline import BiAnAdapt, BiAnConfig, METHOD_NAME, PROMPT_VERSION, VERSION


def public_synthetic_incident() -> dict:
    """Public invented observations, with no embedded expected root or labels."""
    return {
        "case_id": "bian-public-synthetic-smoke", "group_id": "synthetic-smoke",
        "window": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T00:05:00Z",
                   "cutoff": "2026-01-01T00:05:00Z", "timezone": "UTC"},
        "devices": [{"id": "switch-a", "type": "switch"}, {"id": "switch-b", "type": "switch"},
                    {"id": "switch-c", "type": "switch"}],
        "physical_links": [{"u": "switch-a", "v": "switch-b", "evidence_ids": ["public-link-1"]},
                           {"u": "switch-b", "v": "switch-c", "evidence_ids": ["public-link-2"]}],
        "endpoint_context": {"source_ip": ["192.0.2.1"], "sink_ip": ["192.0.2.2"]},
        "events": [
            {"event_id": "public-event-1", "device_id": "switch-a", "event_type": "port_down",
             "event_time": "2026-01-01T00:01:00Z", "record_time": "2026-01-01T00:01:01Z",
             "severity": "warning", "message": "Port to switch-b reported down.", "source": "alarm",
             "related_device_ids": ["switch-b"], "link_endpoints": ["switch-a", "switch-b"]},
            {"event_id": "public-event-2", "device_id": "switch-b", "event_type": "packet_loss",
             "event_time": "2026-01-01T00:01:03Z", "record_time": "2026-01-01T00:01:04Z",
             "severity": "warning", "message": "A monitor reported packet loss; no counter series is available.",
             "source": "alarm"},
        ],
        "observation_coverage": None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run BiAn-adapt with a real local OpenAI-compatible model")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="common normalized JSON/JSONL, raw file, or supported case directory")
    source.add_argument("--synthetic-smoke", action="store_true", help="send only public invented observations to the real local backend")
    parser.add_argument("--output", type=Path, required=True, help="JSON artifact, including every failed case and stage request/output")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--base-url", help="loopback endpoint only; credentials belong in BIAN_API_KEY")
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("--retries", type=int)
    args = parser.parse_args(argv)
    config = BiAnConfig.from_file(args.config)
    overrides = {key: getattr(args, key) for key in ("model", "base_url", "timeout_seconds", "retries")
                 if getattr(args, key) is not None}
    config = replace(config, **overrides)
    cases = [public_synthetic_incident()] if args.synthetic_smoke else load_incidents(args.input)
    model = BiAnAdapt(config)
    predictions = [model.predict_root(case) for case in cases]
    files = sorted(Path(__file__).parent.glob("*.py"))
    manifest = {"method": METHOD_NAME, "version": VERSION, "prompt_version": PROMPT_VERSION,
                "input_contract_version": "baseline-incident-v1", "config": asdict(config),
                "code_sha256": {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files},
                "input_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                "synthetic_smoke": args.synthetic_smoke,
                "evaluation": "No root labels or accuracy metrics are supplied by this runner."}
    dump_json(args.output, {"manifest": manifest, "predictions": predictions})
    counts = {status: sum(row["status"] == status for row in predictions) for status in sorted({row["status"] for row in predictions})}
    print(json.dumps({"output": str(args.output.resolve()), "case_count": len(predictions), "status_counts": counts}, ensure_ascii=False))
    return 0 if all(row["status"] == "ok" for row in predictions) else 1


if __name__ == "__main__":
    raise SystemExit(main())
