import hashlib
import pytest

from grid.snapshot_disposable_publish import (
    PublicationBlocked, publish_disposable_artifact,
)


def test_atomic_disposable_publication(tmp_path):
    directory = tmp_path / "disposable-snapshots"
    directory.mkdir()
    data = b"synthetic immutable fixture"
    digest = hashlib.sha256(data).hexdigest()
    target = publish_disposable_artifact(
        directory, export_id="export-1", data=data, expected_sha256=digest)
    assert target.read_bytes() == data
    assert not list(directory.glob(".pending-*"))
    with pytest.raises(PublicationBlocked, match="Duplicate"):
        publish_disposable_artifact(
            directory, export_id="export-1", data=data, expected_sha256=digest)


def test_wrong_digest_leaves_no_file(tmp_path):
    directory = tmp_path / "disposable-snapshots"
    directory.mkdir()
    with pytest.raises(PublicationBlocked, match="hash"):
        publish_disposable_artifact(
            directory, export_id="export-2", data=b"test",
            expected_sha256="0" * 64)
    assert list(directory.iterdir()) == []


def test_non_disposable_directory_rejected(tmp_path):
    with pytest.raises(PublicationBlocked, match="disposable"):
        publish_disposable_artifact(
            tmp_path, export_id="export-3", data=b"test",
            expected_sha256=hashlib.sha256(b"test").hexdigest())


def test_reused_export_id_with_different_bytes_cannot_replace(tmp_path):
    directory = tmp_path / "disposable-snapshots"
    directory.mkdir()
    original = b"first snapshot"
    changed = b"second snapshot"
    target = publish_disposable_artifact(
        directory, export_id="same-id", data=original,
        expected_sha256=hashlib.sha256(original).hexdigest())
    with pytest.raises((PublicationBlocked, FileExistsError)):
        publish_disposable_artifact(
            directory, export_id="same-id", data=changed,
            expected_sha256=hashlib.sha256(changed).hexdigest())
    assert target.read_bytes() == original
    assert not list(directory.glob(".pending-*"))


def test_link_failure_cleans_staging(tmp_path, monkeypatch):
    import os
    directory = tmp_path / "disposable-snapshots"
    directory.mkdir()
    data = b"fixture"
    def fail_link(source, destination):
        raise OSError("synthetic link failure")
    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(OSError, match="synthetic"):
        publish_disposable_artifact(
            directory, export_id="failed-export", data=data,
            expected_sha256=hashlib.sha256(data).hexdigest())
    assert list(directory.iterdir()) == []
