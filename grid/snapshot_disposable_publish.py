"""Disposable-only atomic artifact publication helper.

This helper is not connected to production Grid storage. Caller must provide
an existing disposable output directory and independently attested bytes.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import tempfile


class PublicationBlocked(ValueError):
    pass


def publish_disposable_artifact(
    directory: Path, *, export_id: str, data: bytes, expected_sha256: str
) -> Path:
    if (not directory.is_dir() or directory.is_symlink()
            or directory.name != "disposable-snapshots"):
        raise PublicationBlocked("Explicit disposable directory required")
    if (type(export_id) is not str or not export_id
            or not all(c.isascii() and (c.isalnum() or c in "-_") for c in export_id)):
        raise PublicationBlocked("Invalid export identity")
    if type(data) is not bytes or hashlib.sha256(data).hexdigest() != expected_sha256:
        raise PublicationBlocked("Artifact hash mismatch")
    destination = directory / (export_id + ".snapshot")
    if destination.exists() or destination.is_symlink():
        raise PublicationBlocked("Duplicate export identity")
    descriptor, staging = tempfile.mkstemp(prefix=".pending-", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists() or destination.is_symlink():
            raise PublicationBlocked("Duplicate export identity")
        os.link(staging, destination)
        return destination
    finally:
        try:
            os.unlink(staging)
        except FileNotFoundError:
            pass
