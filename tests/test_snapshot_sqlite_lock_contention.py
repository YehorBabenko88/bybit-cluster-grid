"""Disposable SQLite lock contention and read-only timeout tests."""
import sqlite3
import time

import pytest


def test_read_only_reader_does_not_wait_indefinitely_for_exclusive_lock(tmp_path):
    path = tmp_path / "locked.sqlite"
    setup = sqlite3.connect(path)
    setup.execute("PRAGMA journal_mode=DELETE")
    setup.execute("CREATE TABLE events(id INTEGER PRIMARY KEY)")
    setup.commit()
    setup.close()
    writer = sqlite3.connect(path, isolation_level=None, timeout=1)
    reader = sqlite3.connect(path.as_uri() + "?mode=ro",
                             uri=True, isolation_level=None, timeout=0.05)
    try:
        reader.execute("PRAGMA query_only=ON")
        writer.execute("BEGIN EXCLUSIVE")
        writer.execute("INSERT INTO events VALUES(1)")
        start = time.monotonic()
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("SELECT count(*) FROM events").fetchone()
        assert time.monotonic() - start < 2
        writer.execute("ROLLBACK")
        assert reader.execute("SELECT count(*) FROM events").fetchone()[0] == 0
    finally:
        writer.close()
        reader.close()
