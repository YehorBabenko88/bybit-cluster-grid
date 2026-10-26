"""Pure replay protection against a trusted previously observed export ledger.

A caller must supply authenticated ledger entries. This function does not
persist state and cannot detect replay when no trusted history is available.
"""
from __future__ import annotations


class ExportReplayBlocked(ValueError):
    pass


def verify_export_replay(
    *, export_id: str, artifact_sha256: str,
    trusted_prior_exports: dict[str, str],
    allow_identical_retry: bool = False,
) -> str:
    if type(export_id) is not str or not export_id:
        raise ExportReplayBlocked("Invalid export identity")
    if (type(artifact_sha256) is not str or len(artifact_sha256) != 64
            or any(c not in "0123456789abcdef" for c in artifact_sha256)):
        raise ExportReplayBlocked("Invalid artifact digest")
    if type(trusted_prior_exports) is not dict:
        raise ExportReplayBlocked("Missing trusted replay ledger")
    if export_id not in trusted_prior_exports:
        return "NEW_EXPORT"
    previous = trusted_prior_exports[export_id]
    if previous != artifact_sha256:
        raise ExportReplayBlocked("Export ID reused with different bytes")
    if not allow_identical_retry:
        raise ExportReplayBlocked("Repeated export ID requires explicit retry authorization")
    return "IDENTICAL_RETRY"
