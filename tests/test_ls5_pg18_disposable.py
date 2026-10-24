"""Disposable PostgreSQL 18 integrity probes. Never run against LS5/production."""
import os
import unittest
import uuid
import psycopg


class Pg18Integrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert os.getenv("GRID_DISPOSABLE_PG18") == "YES"
        assert os.getenv("GITHUB_ACTIONS") == "true"
        cls.dsn = os.environ["GRID_DISPOSABLE_PG_DSN"]
        with psycopg.connect(cls.dsn) as c:
            host, port, db, version = c.execute("select inet_server_addr()::text, inet_server_port(), current_database(), current_setting('server_version_num')::int").fetchone()
            assert host in ("127.0.0.1", "::1"), host
            assert port == 55439, port
            assert db == "grid_ci_disposable", db
            assert 180000 <= version < 190000, version
            assert c.execute("show fsync").fetchone()[0] == "on"
            assert c.execute("show full_page_writes").fetchone()[0] == "on"

    def test_rollback_and_idempotent_replay(self):
        name = "probe_" + uuid.uuid4().hex[:12]
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute(f"create table {name}(operation_id text primary key, amount int not null)")
            try:
                with self.assertRaises(RuntimeError):
                    with c.transaction():
                        c.execute(f"insert into {name} values ('once', 1)")
                        raise RuntimeError("simulated abort")
                self.assertEqual(c.execute(f"select count(*) from {name}").fetchone()[0], 0)
                with c.transaction():
                    c.execute(f"insert into {name} values ('once', 1) on conflict do nothing")
                    c.execute(f"insert into {name} values ('once', 1) on conflict do nothing")
                self.assertEqual(c.execute(f"select count(*),sum(amount) from {name}").fetchone(), (1, 1))
            finally:
                c.execute(f"drop table if exists {name}")

    def test_transaction_advisory_lock_contention(self):
        key = 91424018
        with psycopg.connect(self.dsn, autocommit=True) as a, psycopg.connect(self.dsn, autocommit=True) as b:
            with a.transaction():
                self.assertTrue(a.execute("select pg_try_advisory_xact_lock(%s)", (key,)).fetchone()[0])
                with b.transaction():
                    self.assertFalse(b.execute("select pg_try_advisory_xact_lock(%s)", (key,)).fetchone()[0])
            with b.transaction():
                self.assertTrue(b.execute("select pg_try_advisory_xact_lock(%s)", (key,)).fetchone()[0])

    def test_savepoint_recovery(self):
        with psycopg.connect(self.dsn, autocommit=True) as c:
            with c.transaction():
                with self.assertRaises(psycopg.errors.DivisionByZero):
                    with c.transaction():
                        c.execute("select 1/0")
                self.assertEqual(c.execute("select 42").fetchone()[0], 42)


if __name__ == "__main__":
    unittest.main()
