"""Server entry point: python -m Sys.Preprocess.llm_encoder --help."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from Sys.LLM.engine import get_shared_engine
from Sys.Preprocess.evidence.encoder import EvidenceEncoder, stable_id
from Sys.utils.case_utils import case_node_path


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def run_case(encoder, case, output):
    source = case_node_path(str(case))
    if not source:
        raise ValueError(f"No nodes file in {case}")
    nodes = json.loads(Path(source).read_text(encoding="utf-8"))
    if isinstance(nodes, dict):
        nodes = list(nodes.values())
    if not isinstance(nodes, list) or not all(isinstance(n, dict) for n in nodes):
        raise ValueError(f"Expected node list or node mapping: {source}")
    result = encoder.encode_incident(case.name, nodes)
    destination = output / case.name
    # Whole incident is authoritative; manifest lists current per-device artifacts.
    write_json(destination / "incident.json", result)
    manifest = []
    for device in result["devices"]:
        name = stable_id("device_", device["device"]["device_id"]) + ".json"
        write_json(destination / "devices" / name, device)
        manifest.append({"device_id": device["device"]["device_id"], "path": "devices/" + name})
    for key in ("candidate_vocabulary", "incident_vocabulary", "evidence_graph"):
        write_json(destination / (key + ".json"), result[key])
    write_json(destination / "manifest.json", {"status": result["status"], "devices": manifest})
    return result["status"]


def main():
    parser = argparse.ArgumentParser(description="Encode node observations using one shared Ascend LLM engine")
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("PINGMESH_DATA", "data/node/nodes_max_labeled")))
    parser.add_argument("--output", type=Path, default=Path(os.environ.get("PINGMESH_ENCODER_OUTPUT", "output/llm_encoder")))
    parser.add_argument("--vocabulary", type=Path)
    args = parser.parse_args()
    if not args.data.is_dir():
        parser.error(f"Data directory does not exist: {args.data}")
    cases = [args.data] if case_node_path(str(args.data)) else [p for p in sorted(args.data.iterdir()) if p.is_dir() and case_node_path(str(p))]
    if not cases:
        parser.error("No incident nodes files found")
    vocabulary = json.loads(args.vocabulary.read_text(encoding="utf-8")) if args.vocabulary else None
    encoder = EvidenceEncoder(get_shared_engine(), vocabulary)
    incomplete = False
    for case in cases:
        status = run_case(encoder, case, args.output)
        print(f"{case.name}: {status}", flush=True)
        incomplete |= status != "completed"
    return 2 if incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
