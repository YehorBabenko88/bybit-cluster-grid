"""Verify a disposable PostgreSQL 18 logical backup and isolated restore.

Runs only on GitHub-hosted CI with two named loopback databases.
Never accepts production DSNs or LS5 addresses.
"""
import hashlib
import os
import pathlib
import subprocess
import tempfile
import unittest
import psycopg

HOST = "127.0.0.1"
PORT = 55439
SOURCE = "grid_ci_disposable"
TARGET = "grid_ci_restore"
USER = "grid_ci"


def run(*args):
    # Client tools come from the same pinned major PostgreSQL image as the service.
    archive_paths = [a for a in args if isinstance(a, str) and a.endswith(".dump")]
    mounts = []
    if archive_paths:
        parent = str(pathlib.Path(archive_paths[0]).parent)
        mounts = ["--volume", parent + ":" + parent]
    cmd = ["docker", "run", "--rm", "--network", "host", *mounts,
           "--env", "PGPASSWORD=ci_only_disposable", "postgres:18", *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


class RestoreDrill(unittest.TestCase):
    def test_backup_and_restore(self):
        assert os.getenv("GITHUB_ACTIONS") == "true"
        assert os.getenv("GRID_DISPOSABLE_PG18") == "YES"
        assert os.getenv("GRID_DISPOSABLE_PG_DSN") == (
            "postgresql://grid_ci:ci_only_disposable@127.0.0.1:55439/grid_ci_disposable"
        )
        assert os.getenv("PGHOST") == HOST
        assert os.getenv("PGPORT") == str(PORT)
        assert os.getenv("PGUSER") == USER
        assert os.getenv("PGDATABASE") == SOURCE
        assert os.getenv("PGPASSWORD") == "ci_only_disposable"
        with psycopg.connect(os.environ["GRID_DISPOSABLE_PG_DSN"]) as c:
            v = int(c.execute("select current_setting('server_version_num')").fetchone()[0])
            assert 180000 <= v < 190000
            c.execute("create table if not exists ci_restore_probe (id integer primary key, payload text not null)")
            c.execute("insert into ci_restore_probe values (1,'alpha'),(2,'beta') on conflict (id) do update set payload=excluded.payload")
            c.commit()
            source_rows = c.execute("select id,payload from ci_restore_probe order by id").fetchall()
        with tempfile.TemporaryDirectory(prefix="grid-pg18-backup-") as directory:
            archive = pathlib.Path(directory) / "snapshot.dump"
            run("pg_dump", "--format=custom", "--no-owner", "--no-acl",
                "--host", HOST, "--port", str(PORT), "--username", USER,
                "--dbname", SOURCE, "--file", str(archive))
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            assert len(digest) == 64 and archive.stat().st_size > 0
            run("pg_restore", "--list", str(archive))
            run("createdb", "--host", HOST, "--port", str(PORT), "--username", USER, TARGET)
            try:
                run("pg_restore", "--exit-on-error", "--single-transaction", "--no-owner",
                    "--no-acl", "--host", HOST, "--port", str(PORT), "--username", USER,
                    "--dbname", TARGET, str(archive))
                with psycopg.connect(
                    f"postgresql://{USER}:ci_only_disposable@{HOST}:{PORT}/{TARGET}"
                ) as restored:
                    assert restored.execute("select id,payload from ci_restore_probe order by id").fetchall() == source_rows
                    assert restored.execute("select count(*) from pg_constraint where conrelid='ci_restore_probe'::regclass and contype='p'").fetchone()[0] == 1
                assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest
            finally:
                run("dropdb", "--if-exists", "--host", HOST, "--port", str(PORT),
                    "--username", USER, TARGET)


if __name__ == "__main__":
    unittest.main()
