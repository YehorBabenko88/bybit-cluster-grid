"""Fail-closed producer-side snapshot planning for Grid.

The native Grid tables currently inspected do not establish first-availability,
historical revisions or cross-store coherence. No export of those tables is
authorized by this module. This CLI never opens a database or network socket.
"""
from __future__ import annotations
import argparse
import json
import os
import stat
from pathlib import Path

BLOCKERS = (
    "historical_first_availability_not_attested",
    "historical_revision_provenance_not_attested",
    "cross_store_coherence_epoch_not_attested",
    "market_type_identity_not_attested",
    "source_watermark_not_attested",
)


def plan() -> dict:
    return {
        "status": "BLOCKED",
        "source": "grid/db.py PostgreSQL DDL (default branch)",
        "candidate_tables": [
            "market_events", "candles_1m", "footprint_1m",
            "orderbook_snapshots", "derivatives_metrics"
        ],
        "blockers": list(BLOCKERS),
        "writes_permitted": False,
    }


def verify_receipt_structure(path: Path) -> dict:
    """Non-authenticating structure inspection; NEVER returns VERIFIED."""
    if path.is_symlink() or not path.is_file():
        return {"status": "BLOCKED", "reason": "unsafe_receipt_path"}
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                return {"status": "BLOCKED", "reason": "unsafe_or_oversized_receipt"}
            raw = stream.read(65537)
        if len(raw) > 65536:
            return {"status": "BLOCKED", "reason": "oversized_receipt"}
        def unique_pairs(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError("duplicate JSON key")
                obj[key] = value
            return obj
        payload = json.loads(raw, object_pairs_hook=unique_pairs)
    except (OSError, ValueError, UnicodeError):
        return {"status": "BLOCKED", "reason": "invalid_receipt"}
    if not isinstance(payload, dict):
        return {"status": "BLOCKED", "reason": "invalid_receipt_shape"}
    return {"status": "BLOCKED", "reason": "trusted_signature_and_source_attestation_required"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Grid snapshot export safety CLI")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan", action="store_true")
    modes.add_argument("--verify", type=Path, metavar="RECEIPT_JSON")
    modes.add_argument("--export-disposable", type=Path, metavar="FIXTURE_DIR")
    args = parser.parse_args(argv)
    if args.plan:
        result = plan()
    elif args.verify is not None:
        result = verify_receipt_structure(args.verify)
    else:
        result = {"status": "BLOCKED", "reason":
                  "disposable producer signing/epoch adapter not implemented",
                  "writes_permitted": False}
    print(json.dumps(result, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
