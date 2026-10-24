import pytest

from grid.snapshot_disposable_recovery import (
    RecoveryBlocked, inspect_disposable_publication,
)


def test_orphan_staging_blocks(tmp_path):
    directory = tmp_path / "disposable-snapshots"
    directory.mkdir()
    (directory / ".pending-crash").write_bytes(b"partial")
    result = inspect_disposable_publication(directory)
    assert result["status"] == "BLOCKED"
    assert result["orphan_staging"] == [".pending-crash"]
    assert (directory / ".pending-crash").exists()


def test_published_candidate_not_authenticated(tmp_path):
    directory = tmp_path / "disposable-snapshots"
    directory.mkdir()
    (directory / "export-1.snapshot").write_bytes(b"fake")
    result = inspect_disposable_publication(directory)
    assert result["status"] == "STRUCTURE_ONLY"
    assert result["authenticated"] is False


def test_unexpected_file_rejected(tmp_path):
    directory = tmp_path / "disposable-snapshots"
    directory.mkdir()
    (directory / "unknown.txt").write_text("x")
    with pytest.raises(RecoveryBlocked):
        inspect_disposable_publication(directory)
