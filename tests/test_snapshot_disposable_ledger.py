import pytest

from grid.snapshot_disposable_ledger import record_disposable_export
from grid.snapshot_replay_guard import ExportReplayBlocked


def test_ledger_persists_export_id_across_calls(tmp_path):
    directory = tmp_path / "disposable-ledger"
    directory.mkdir()
    assert record_disposable_export(
        directory, export_id="export-1", artifact_sha256="a"*64) == "RECORDED"
    assert (directory / "export-1.sha256").read_text() == "a"*64 + "\n"
    with pytest.raises(ExportReplayBlocked, match="Duplicate"):
        record_disposable_export(
            directory, export_id="export-1", artifact_sha256="b"*64)


def test_non_disposable_ledger_rejected(tmp_path):
    with pytest.raises(ExportReplayBlocked, match="disposable"):
        record_disposable_export(
            tmp_path, export_id="export-2", artifact_sha256="a"*64)


def test_path_traversal_export_id_rejected(tmp_path):
    directory = tmp_path / "disposable-ledger"
    directory.mkdir()
    with pytest.raises(ExportReplayBlocked, match="Invalid export ID"):
        record_disposable_export(
            directory, export_id="../escape", artifact_sha256="a"*64)
