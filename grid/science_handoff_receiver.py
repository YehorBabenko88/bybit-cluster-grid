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
        if key == "science_bundle":
            try:
                bundle = json.loads(resolved.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError) as exc:
                raise ScienceHandoffError(f"invalid science bundle JSON: {exc}") from exc
            if not isinstance(bundle, dict):
                raise ScienceHandoffError("science bundle must be a JSON object")
            if bundle.get("schema") != 1 or bundle.get("source") != "strattester":
                raise ScienceHandoffError("unsupported science bundle schema or source")
            if bundle.get("research_scope") != "HISTORICAL_BOOTSTRAP_ONLY":
                raise ScienceHandoffError("unsupported science research scope")
            if not isinstance(bundle.get("capabilities"), dict):
                raise ScienceHandoffError("science capabilities must be an object")
            if not isinstance(bundle.get("symbols"), list):
                raise ScienceHandoffError("science symbols must be a list")
            for row in bundle["symbols"]:
                if (not isinstance(row, dict)
                        or not isinstance(row.get("symbol"), str)
                        or not row["symbol"]
                        or row.get("status") not in ("READY", "INSUFFICIENT")):
                    raise ScienceHandoffError("invalid science symbol record")
            inner_sha = bundle.get("sha256")
            if not isinstance(inner_sha, str):
                raise ScienceHandoffError("science bundle fingerprint is missing")
            unsigned = dict(bundle)
            unsigned.pop("sha256")
            canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), default=str)
            if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != inner_sha:
                raise ScienceHandoffError("science bundle internal checksum mismatch")
    return manifest


def science_handoff_identity(manifest_path):
    """Stable content identity for deduplication planning; no state is written.

    Repacking the same scientific results at a different path or time must
    not create a different identity. This is not an import ledger.
    """
    manifest = verify_science_handoff(manifest_path)
    components = {
        key: (manifest.get(key) or {}).get("sha256")
        for key in ("science_bundle", "strategy_results", "phase_manifest")
    }
    raw = json.dumps(components, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def check_science_handoff_seen(manifest_path, ledger_path):
    """Read-only deduplication lookup; never treats an invalid package as seen.

    Ledger schema is intentionally minimal and independent of any trading DB.
    A future importer must own atomic commit/rollback of its processing state.
    """
    identity = science_handoff_identity(manifest_path)
    ledger_path = Path(ledger_path)
    if not ledger_path.exists():
        return {"identity": identity, "seen": False}
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ScienceHandoffError(f"invalid handoff ledger: {exc}") from exc
    if not isinstance(ledger, dict) or ledger.get("schema") != 1:
        raise ScienceHandoffError("unsupported handoff ledger schema")
    entries = ledger.get("imported")
    if not isinstance(entries, list) or any(
        not isinstance(value, str) or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
        for value in entries
    ):
        raise ScienceHandoffError("invalid handoff ledger entries")
    if len(set(entries)) != len(entries):
        raise ScienceHandoffError("duplicate handoff ledger entries")
    return {"identity": identity, "seen": identity in entries}
