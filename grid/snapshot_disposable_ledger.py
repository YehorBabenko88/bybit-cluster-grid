"""Disposable-only append-once replay ledger.

This is a local fixture mechanism, not a trusted production replay database.
Each export ID is stored as an exclusive-created file. Crash recovery requires
operator inspection; no silent ledger rewriting is permitted.
"""
from __future__ import annotations
import os
from pathlib import Path

from .snapshot_replay_guard import ExportReplayBlocked, verify_export_replay


def record_disposable_export(
    directory: Path, *, export_id: str, artifact_sha256: str
) -> str:
    if (not directory.is_dir() or directory.is_symlink()
            or directory.name != "disposable-ledger"):
        raise ExportReplayBlocked("Explicit disposable ledger directory required")
    if (type(export_id) is not str or not export_id
            or not all(c.isascii() and (c.isalnum() or c in "-_") for c in export_id)):
        raise ExportReplayBlocked("Invalid export ID")
    verify_export_replay(
        export_id=export_id, artifact_sha256=artifact_sha256,
        trusted_prior_exports={})
    target = directory / (export_id + ".sha256")
    descriptor = None
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write((artifact_sha256 + "\n").encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ExportReplayBlocked("Duplicate export ID") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return "RECORDED"
