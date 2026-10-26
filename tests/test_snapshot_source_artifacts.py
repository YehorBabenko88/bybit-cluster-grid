from hashlib import sha256
import pytest

from grid.snapshot_source_artifacts import verify_source_artifacts
from grid.snapshot_source_epoch import SourceEpochBlocked


def sample():
    artifacts = {"pg": b"postgres fixture", "sqlite": b"sqlite fixture"}
    receipts = [
        dict(source_id=source, epoch_id="epoch-1", routing_generation=7,
             snapshot_id="snapshot-" + source,
             source_sha256=sha256(data).hexdigest())
        for source, data in artifacts.items()
    ]
    return receipts, artifacts


def check(receipts, artifacts):
    verify_source_artifacts(
        receipts, artifacts, required_sources=frozenset({"pg", "sqlite"}),
        expected_epoch="epoch-1", expected_routing_generation=7,
        max_bytes_per_source=1024)


def test_matching_source_artifacts():
    check(*sample())


def test_tampered_source_artifact_rejected():
    receipts, artifacts = sample()
    artifacts["pg"] = b"tampered"
    with pytest.raises(SourceEpochBlocked, match="SHA256"):
        check(receipts, artifacts)


def test_missing_source_artifact_rejected():
    receipts, artifacts = sample()
    del artifacts["sqlite"]
    with pytest.raises(SourceEpochBlocked, match="Incomplete"):
        check(receipts, artifacts)


def test_oversized_source_artifact_rejected():
    receipts, artifacts = sample()
    artifacts["pg"] = b"x" * 1025
    with pytest.raises(SourceEpochBlocked, match="oversized"):
        check(receipts, artifacts)
