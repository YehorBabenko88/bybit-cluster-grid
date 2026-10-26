import hashlib

from grid.snapshot_ledger_consistency import inspect_disposable_ledger


def directories(tmp_path):
    ledger = tmp_path / "disposable-ledger"
    snapshots = tmp_path / "disposable-snapshots"
    ledger.mkdir()
    snapshots.mkdir()
    return ledger, snapshots


def test_orphan_ledger_blocks(tmp_path):
    ledger, snapshots = directories(tmp_path)
    (ledger / "export-1.sha256").write_text("a"*64)
    result = inspect_disposable_ledger(ledger, snapshots)
    assert result["status"] == "BLOCKED"
    assert "export-1:missing_snapshot" in result["problems"]


def test_tampered_snapshot_blocks(tmp_path):
    ledger, snapshots = directories(tmp_path)
    (ledger / "export-1.sha256").write_text("a"*64)
    (snapshots / "export-1.snapshot").write_bytes(b"changed")
    result = inspect_disposable_ledger(ledger, snapshots)
    assert "export-1:digest_mismatch" in result["problems"]


def test_matching_artifact_is_structure_only(tmp_path):
    ledger, snapshots = directories(tmp_path)
    data = b"synthetic"
    (ledger / "export-1.sha256").write_text(hashlib.sha256(data).hexdigest())
    (snapshots / "export-1.snapshot").write_bytes(data)
    result = inspect_disposable_ledger(ledger, snapshots)
    assert result["status"] == "STRUCTURE_ONLY"
    assert result["authenticated"] is False
