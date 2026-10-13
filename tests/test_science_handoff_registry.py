import concurrent.futures
import sqlite3

import pytest

from grid.science_handoff_receiver import ScienceHandoffError
from grid.science_handoff_registry import claim_science_handoff
from test_science_handoff_receiver import make_package


def test_claim_once_and_keep_durable_reservation(tmp_path):
    manifest, _ = make_package(tmp_path)
    db = tmp_path / "claims.sqlite3"
    first = claim_science_handoff(manifest, db)
    second = claim_science_handoff(manifest, db)
    assert first["claimed"] is True
    assert second == {"identity": first["identity"], "claimed": False}
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM handoff_claims").fetchone()[0] == 1


def test_concurrent_claims_only_one_wins(tmp_path):
    manifest, _ = make_package(tmp_path)
    db = tmp_path / "claims.sqlite3"
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: claim_science_handoff(manifest, db), range(12)))
    assert sum(item["claimed"] for item in results) == 1
    assert len({item["identity"] for item in results}) == 1


def test_invalid_package_does_not_create_registry(tmp_path):
    manifest, science = make_package(tmp_path)
    science.write_bytes(b"tampered")
    db = tmp_path / "claims.sqlite3"
    with pytest.raises(ScienceHandoffError, match="checksum mismatch"):
        claim_science_handoff(manifest, db)
    assert not db.exists()


def test_registry_symlink_rejected(tmp_path):
    manifest, _ = make_package(tmp_path)
    db = tmp_path / "claims.sqlite3"
    try:
        db.symlink_to(tmp_path / "missing.sqlite3")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ScienceHandoffError, match="invalid scientific handoff registry"):
        claim_science_handoff(manifest, db)
