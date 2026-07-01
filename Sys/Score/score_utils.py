"""Backward-compatible shim — all helpers now live in ``Sys.utils.io_utils``.

New code should import directly from ``Sys.utils.io_utils``.
"""

from Sys.utils.io_utils import (  # noqa: F401  # re-exported for compatibility
    case_id_from_dir,
    dedupe,
    ensure_parent,
    hit_at,
    load_json,
    write_csv,
    write_json,
    write_jsonl,
)
