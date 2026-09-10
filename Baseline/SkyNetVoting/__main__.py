"""Run explicit input JSON/JSONL via the shared observational loader."""

import argparse
import json
from pathlib import Path

from Baseline.common.io import dump_json, load_incidents
from .voting import SkyNetVoting


def main() -> None:
    parser = argparse.ArgumentParser(description="SkyNet-inspired device alert voting")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", help="JSON configuration; defaults to attribution, alerts only")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8-sig")) if args.config else None
    model = SkyNetVoting(config)
    predictions = [model.predict_root(incident) for incident in load_incidents(args.input)]
    dump_json(args.output, predictions)


if __name__ == "__main__":
    main()
