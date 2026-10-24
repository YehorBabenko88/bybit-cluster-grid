"""Synthetic snapshot isolation acceptance notes.

SQLite WAL provides a consistent read view *inside one database* once the
reader establishes its snapshot. It does not create a coherent transaction
across separate shard files or PostgreSQL. Source authority and epoch remain
producer obligations.
"""
import sqlite3
import pytest


def test_sqlite_read_only_connection_refuses_mutation(tmp_path):
    path = tmp_path / "fixture.sqlite"
    with sqlite3.connect(path) as setup:
        setup.execute("CREATE TABLE events (id INTEGER)")
    reader = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        reader.execute("PRAGMA query_only=ON")
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("INSERT INTO events VALUES (1)")
        assert reader.execute("SELECT count(*) FROM events").fetchone()[0] == 0
    finally:
        reader.close()
