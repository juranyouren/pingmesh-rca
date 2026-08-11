"""Evaluate BiAn-Pipeline1 predictions and report latency metrics.

This is an evaluation-only script. It is the only new BiAn entrypoint that
loads ground-truth labels indirectly through Score_N.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Sys.Score.Score_N import Scorer


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate BiAn-Pipeline1.")
    parser.add_argument("res_json", type=Path)
    args = parser.parse_args()

    scorer = Scorer(str(args.res_json))
    summary = scorer.calculate_metrics()
    timing_path = args.res_json.with_name("timing.json")
    timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.exists() else {}

    output = {
        "method": "BiAn-Pipeline1-32B",
        "ranking_metrics": summary.get("llm_evaluation", {}).get("ranking_metrics", {}),
        "timing_seconds": timing,
    }
    output_path = args.res_json.with_name("evaluation.json")
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"Saved to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
