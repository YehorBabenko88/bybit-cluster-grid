import pytest

from grid.snapshot_replay_guard import ExportReplayBlocked, verify_export_replay


DIGEST = "a" * 64


def test_new_export():
    assert verify_export_replay(
        export_id="new", artifact_sha256=DIGEST,
        trusted_prior_exports={}) == "NEW_EXPORT"


def test_changed_export_id_replay_rejected():
    with pytest.raises(ExportReplayBlocked, match="different bytes"):
        verify_export_replay(
            export_id="existing", artifact_sha256=DIGEST,
            trusted_prior_exports={"existing": "b" * 64})


def test_identical_retry_requires_explicit_permission():
    with pytest.raises(ExportReplayBlocked, match="retry authorization"):
        verify_export_replay(
            export_id="existing", artifact_sha256=DIGEST,
            trusted_prior_exports={"existing": DIGEST})
    assert verify_export_replay(
        export_id="existing", artifact_sha256=DIGEST,
        trusted_prior_exports={"existing": DIGEST},
        allow_identical_retry=True) == "IDENTICAL_RETRY"
