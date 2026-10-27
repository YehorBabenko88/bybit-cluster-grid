"""Disposable SQLite WAL rollback and checkpoint tests."""
import sqlite3


def test_uncommitted_writer_rollback_does_not_leak(tmp_path):
    path = tmp_path / "rollback.sqlite"
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE events(id INTEGER PRIMARY KEY)")
    db.execute("INSERT INTO events VALUES(1)")
    db.commit()
    db.close()
    writer = sqlite3.connect(path, isolation_level=None)
    reader = sqlite3.connect(path, isolation_level=None)
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO events VALUES(2)")
        reader.execute("BEGIN")
        assert reader.execute("SELECT count(*) FROM events").fetchone()[0] == 1
        writer.execute("ROLLBACK")
        reader.execute("COMMIT")
        assert reader.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    finally:
        writer.close()
        reader.close()


def test_passive_checkpoint_does_not_change_reader_snapshot(tmp_path):
    path = tmp_path / "checkpoint.sqlite"
    setup = sqlite3.connect(path)
    setup.execute("PRAGMA journal_mode=WAL")
    setup.execute("CREATE TABLE events(id INTEGER PRIMARY KEY)")
    setup.execute("INSERT INTO events VALUES(1)")
    setup.commit()
    reader = sqlite3.connect(path, isolation_level=None)
    writer = sqlite3.connect(path, isolation_level=None)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT count(*) FROM events").fetchone()[0] == 1
        writer.execute("INSERT INTO events VALUES(2)")
        writer.commit()
        writer.execute("PRAGMA wal_checkpoint(PASSIVE)")
        assert reader.execute("SELECT count(*) FROM events").fetchone()[0] == 1
        reader.execute("COMMIT")
        assert reader.execute("SELECT count(*) FROM events").fetchone()[0] == 2
    finally:
        reader.close()
        writer.close()
        setup.close()
