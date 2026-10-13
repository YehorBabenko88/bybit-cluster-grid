"""Isolated SQLite claim registry for validated scientific handoff packages.

Claims are durable reservations, NOT completed imports. Recovery of an
abandoned claim requires a separate explicit process. No trading DB is used.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from grid.science_handoff_receiver import ScienceHandoffError, science_handoff_identity


def claim_science_handoff(manifest_path, registry_path):
    """Atomically reserve a verified package, with UNIQUE deduplication."""
    identity = science_handoff_identity(manifest_path)
    path = Path(registry_path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ScienceHandoffError("invalid scientific handoff registry path")
    if not path.parent.is_dir():
        raise ScienceHandoffError("scientific handoff registry directory is missing")
    try:
        with sqlite3.connect(str(path), timeout=10.0) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS handoff_claims "
                "(identity TEXT PRIMARY KEY CHECK(length(identity)=64), "
                "status TEXT NOT NULL CHECK(status='CLAIMED'))"
            )
            cursor = connection.execute(
                "INSERT OR IGNORE INTO handoff_claims(identity,status) VALUES (?, 'CLAIMED')",
                (identity,),
            )
            claimed = cursor.rowcount == 1
            connection.commit()
    except sqlite3.Error as exc:
        raise ScienceHandoffError(f"scientific handoff registry error: {exc}") from exc
    return {"identity": identity, "claimed": claimed}
