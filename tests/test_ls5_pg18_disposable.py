"""Disposable PostgreSQL 18 integrity probes. Never run against LS5/production."""
import os
import unittest
import uuid
import psycopg


class Pg18Integrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (os.getenv("GRID_DISPOSABLE_PG18") != "YES"
                or os.getenv("GITHUB_ACTIONS") != "true"
                or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted"
                or os.getenv("RUNNER_OS") != "Linux"
                or os.getenv("GITHUB_REPOSITORY") != "YehorBabenko88/bybit-cluster-grid"):
            raise RuntimeError("PG18_DISPOSABLE_HOSTED_GUARD")
        cls.dsn = os.environ["GRID_DISPOSABLE_PG_DSN"]
        if cls.dsn != "postgresql://grid_ci:ci_only_disposable@127.0.0.1:55439/grid_ci_disposable":
            raise RuntimeError("PG18_DISPOSABLE_DSN_GUARD")
        with psycopg.connect(cls.dsn) as c:
            host, port, db, version = c.execute("select inet_server_addr()::text, inet_server_port(), current_database(), current_setting('server_version_num')::int").fetchone()
            # Docker publishes host loopback:55439 to container:5432.
            # inet_server_addr() is the container interface, not the client target.
            self_host = c.info.host
            if host is None or self_host != "127.0.0.1" or c.info.port != 55439:
                raise RuntimeError("PG18_DISPOSABLE_LOOPBACK_GUARD")
            if port != 5432: raise RuntimeError("PG18_CONTAINER_PORT_MISMATCH")
            if db != "grid_ci_disposable": raise RuntimeError("PG18_DATABASE_MISMATCH")
            if not 180000 <= version < 190000: raise RuntimeError("PG18_VERSION_MISMATCH")
            if c.execute("show fsync").fetchone()[0] != "on": raise RuntimeError("PG18_FSYNC_DISABLED")
            if c.execute("show full_page_writes").fetchone()[0] != "on": raise RuntimeError("PG18_FULL_PAGE_WRITES_DISABLED")

    def test_wal_durability_configuration(self):
        with psycopg.connect(self.dsn, autocommit=True) as c:
            settings=dict(c.execute("select name,setting from pg_settings where name in ('fsync','full_page_writes','synchronous_commit','wal_level')").fetchall())
            self.assertEqual(settings["fsync"], "on")
            self.assertEqual(settings["full_page_writes"], "on")
            self.assertEqual(settings["synchronous_commit"], "on")
            self.assertIn(settings["wal_level"], ("replica", "logical"))
            before=c.execute("select pg_current_wal_lsn()::text").fetchone()[0]
            self.assertRegex(before, r"^[0-9A-F]+/[0-9A-F]+$")

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

    def test_disconnect_rolls_back_uncommitted_write(self):
        name = "disconnect_" + uuid.uuid4().hex[:12]
        with psycopg.connect(self.dsn, autocommit=True) as admin:
            admin.execute(f"create table {name}(id integer primary key)")
            try:
                worker = psycopg.connect(self.dsn, autocommit=True)
                try:
                    worker.execute("begin")
                    worker.execute(f"insert into {name} values (1)")
                    worker.close()  # network/process disconnect before COMMIT
                finally:
                    if not worker.closed:
                        worker.close()
                with psycopg.connect(self.dsn, autocommit=True) as verifier:
                    self.assertEqual(verifier.execute(f"select count(*) from {name}").fetchone()[0], 0)
            finally:
                admin.execute(f"drop table if exists {name}")

    def test_unique_key_survives_reconnect(self):
        name = "replay_" + uuid.uuid4().hex[:12]
        with psycopg.connect(self.dsn, autocommit=True) as admin:
            admin.execute(f"create table {name}(operation_id text primary key, value integer)")
            try:
                with psycopg.connect(self.dsn, autocommit=True) as first:
                    with first.transaction():
                        first.execute(f"insert into {name} values ('event-1', 7)")
                with psycopg.connect(self.dsn, autocommit=True) as second:
                    with second.transaction():
                        second.execute(f"insert into {name} values ('event-1', 7) on conflict do nothing")
                    self.assertEqual(second.execute(f"select count(*),sum(value) from {name}").fetchone(), (1, 7))
            finally:
                admin.execute(f"drop table if exists {name}")

    def test_savepoint_recovery(self):
        with psycopg.connect(self.dsn, autocommit=True) as c:
            with c.transaction():
                with self.assertRaises(psycopg.errors.DivisionByZero):
                    with c.transaction():
                        c.execute("select 1/0")
                self.assertEqual(c.execute("select 42").fetchone()[0], 42)


if __name__ == "__main__":
    unittest.main()
