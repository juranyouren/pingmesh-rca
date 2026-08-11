"""CLI wrapper for ``python Baseline/RCAcopilot/run.py ...``."""

from __future__ import annotations

import sys
from pathlib import Path


# Allow direct execution from the repository root without installing a package.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Baseline.RCAcopilot.rcacopilot import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
