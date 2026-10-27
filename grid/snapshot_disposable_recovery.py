"""Read-only disposable snapshot publication recovery inspection.

Never removes, renames or trusts orphan staging files. Recovery is an
operator-controlled action after verifying producer receipts.
"""
from pathlib import Path


class RecoveryBlocked(ValueError):
    pass


def inspect_disposable_publication(directory: Path) -> dict:
    if not directory.is_dir() or directory.is_symlink() or directory.name != "disposable-snapshots":
        raise RecoveryBlocked("Disposable snapshot directory required")
    pending = []
    published = []
    for entry in directory.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise RecoveryBlocked("Unexpected filesystem object")
        if entry.name.startswith(".pending-"):
            pending.append(entry.name)
        elif entry.name.endswith(".snapshot"):
            published.append(entry.name)
        else:
            raise RecoveryBlocked("Unexpected publication artifact")
    return {
        "status": "BLOCKED" if pending else "STRUCTURE_ONLY",
        "orphan_staging": sorted(pending),
        "published_candidates": sorted(published),
        "authenticated": False,
    }
