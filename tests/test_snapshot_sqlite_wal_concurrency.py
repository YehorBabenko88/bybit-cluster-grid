"""Disposable SQLite WAL snapshot isolation regression.

All databases are created inside pytest tmp_path; no production paths.
"""
import sqlite3


def test_reader_snapshot_stable_while_writer_commits(tmp_path):
    path = tmp_path / "fixture.sqlite"
    setup = sqlite3.connect(path)
    setup.execute("PRAGMA journal_mode=WAL")
    setup.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, value TEXT)")
    setup.execute("INSERT INTO events VALUES (1, 'original')")
    setup.commit()
    setup.close()

    reader = sqlite3.connect(path, isolation_level=None, timeout=1)
    writer = sqlite3.connect(path, isolation_level=None, timeout=1)
    try:
        reader.execute("PRAGMA query_only=ON")
        reader.execute("BEGIN")
        assert reader.execute("SELECT value FROM events WHERE id=1").fetchone()[0] == "original"
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE events SET value='changed' WHERE id=1")
        writer.execute("INSERT INTO events VALUES (2, 'new')")
        writer.execute("COMMIT")
        assert reader.execute("SELECT value FROM events WHERE id=1").fetchone()[0] == "original"
        assert reader.execute("SELECT count(*) FROM events").fetchone()[0] == 1
        reader.execute("COMMIT")
        assert reader.execute("SELECT count(*) FROM events").fetchone()[0] == 2
    finally:
        reader.close()
        writer.close()
