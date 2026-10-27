"""Read-only inspection of disposable ledger/snapshot consistency.

No automatic repair. Missing or mismatched artifacts are BLOCKED.
"""
from __future__ import annotations
import hashlib
from pathlib import Path


class LedgerConsistencyBlocked(ValueError):
    pass


def inspect_disposable_ledger(ledger_dir: Path, snapshot_dir: Path) -> dict:
    if (ledger_dir.name != "disposable-ledger" or snapshot_dir.name != "disposable-snapshots"
            or not ledger_dir.is_dir() or not snapshot_dir.is_dir()
            or ledger_dir.is_symlink() or snapshot_dir.is_symlink()):
        raise LedgerConsistencyBlocked("Disposable directories required")
    problems = []
    count = 0
    for record in ledger_dir.iterdir():
        if record.is_symlink() or not record.is_file() or record.suffix != ".sha256":
            raise LedgerConsistencyBlocked("Unexpected ledger object")
        export_id = record.stem
        if not export_id or not all(c.isascii() and (c.isalnum() or c in "-_") for c in export_id):
            raise LedgerConsistencyBlocked("Invalid ledger export ID")
        count += 1
        expected = record.read_text(encoding="ascii").strip()
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            problems.append(export_id + ":invalid_digest")
            continue
        artifact = snapshot_dir / (export_id + ".snapshot")
        if artifact.is_symlink() or not artifact.is_file():
            problems.append(export_id + ":missing_snapshot")
            continue
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if digest != expected:
            problems.append(export_id + ":digest_mismatch")
    return {"status": "BLOCKED" if problems else "STRUCTURE_ONLY",
            "ledger_records": count, "problems": sorted(problems),
            "authenticated": False}
