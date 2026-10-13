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


def test_claim_survives_reopening_database_after_simulated_restart(tmp_path):
    manifest, _ = make_package(tmp_path)
    db = tmp_path / "claims.sqlite3"
    initial = claim_science_handoff(manifest, db)
    assert initial["claimed"] is True
    # A fresh connection simulates the next process after the original exits.
    with sqlite3.connect(db) as connection:
        assert connection.execute(
            "SELECT status FROM handoff_claims WHERE identity = ?",
            (initial["identity"],),
        ).fetchone() == ("CLAIMED",)
    assert claim_science_handoff(manifest, db) == {
        "identity": initial["identity"], "claimed": False,
    }


def test_corrupt_registry_fails_closed_without_replacing_it(tmp_path):
    manifest, _ = make_package(tmp_path)
    db = tmp_path / "claims.sqlite3"
    db.write_bytes(b"not-a-sqlite-database")
    with pytest.raises(ScienceHandoffError, match="registry error"):
        claim_science_handoff(manifest, db)
    assert db.read_bytes() == b"not-a-sqlite-database"


def test_registry_parent_directory_must_exist(tmp_path):
    manifest, _ = make_package(tmp_path)
    db = tmp_path / "missing" / "claims.sqlite3"
    with pytest.raises(ScienceHandoffError, match="directory is missing"):
        claim_science_handoff(manifest, db)
    assert not db.parent.exists()


def test_failed_claim_transaction_rolls_back_without_reservation(tmp_path):
    manifest, _ = make_package(tmp_path)
    db = tmp_path / "claims.sqlite3"
    # Inject a database-side failure after table creation but before insertion.
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE handoff_claims (identity TEXT PRIMARY KEY, status TEXT)")
        connection.execute(
            "CREATE TRIGGER reject_claim BEFORE INSERT ON handoff_claims "
            "BEGIN SELECT RAISE(ABORT, 'simulated interruption'); END"
        )
    with pytest.raises(ScienceHandoffError, match="registry error"):
        claim_science_handoff(manifest, db)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT count(*) FROM handoff_claims").fetchone()[0] == 0
        connection.execute("DROP TRIGGER reject_claim")
    assert claim_science_handoff(manifest, db)["claimed"] is True


def test_existing_claim_is_not_changed_by_repeat_request(tmp_path):
    manifest, _ = make_package(tmp_path)
    db = tmp_path / "claims.sqlite3"
    first = claim_science_handoff(manifest, db)
    with sqlite3.connect(db) as connection:
        before = connection.execute("SELECT identity, status FROM handoff_claims").fetchall()
    assert claim_science_handoff(manifest, db)["claimed"] is False
    with sqlite3.connect(db) as connection:
        after = connection.execute("SELECT identity, status FROM handoff_claims").fetchall()
    assert before == after == [(first["identity"], "CLAIMED")]
