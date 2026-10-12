"""Read-only validation of portable Strattester scientific handoff packages.

This is deliberately separate from the legacy research GRID_IMPORT_PENDING contract.
No import, DB writes, or live trading actions occur here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class ScienceHandoffError(ValueError):
    """The scientific handoff is not safe to consume."""


def verify_science_handoff(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ScienceHandoffError(f"cannot read handoff: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ScienceHandoffError("handoff must be a JSON object")
    if manifest.get("schema") != 1 or manifest.get("source") != "strattester":
        raise ScienceHandoffError("unsupported scientific handoff schema or source")
    if manifest.get("ready_for_grid_import") is not True:
        raise ScienceHandoffError("scientific handoff is not ready")
    science = manifest.get("science_bundle")
    if not isinstance(science, dict):
        raise ScienceHandoffError("science bundle is required")
    for key in ("science_bundle", "strategy_results", "phase_manifest"):
        item = manifest.get(key)
        if item is None:
            if key == "science_bundle":
                raise ScienceHandoffError("science bundle is required")
            continue
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"]:
            raise ScienceHandoffError(f"invalid {key} path")
        expected = item.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ScienceHandoffError(f"invalid {key} checksum")
        path = Path(item["path"])
        if path.is_absolute():
            raise ScienceHandoffError(f"{key} must use a portable relative path")
        resolved = (manifest_path.parent / path).resolve()
        if resolved == manifest_path or not resolved.is_relative_to(manifest_path.parent):
            raise ScienceHandoffError(f"{key} escapes the package directory")
        if not resolved.is_file() or (key == "science_bundle" and resolved.stat().st_size == 0):
            raise ScienceHandoffError(f"missing or empty {key}")
        digest = hashlib.sha256()
        with resolved.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ScienceHandoffError(f"{key} checksum mismatch")
    return manifest
