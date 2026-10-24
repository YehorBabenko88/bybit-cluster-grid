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
import uuid
import psycopg

HOST = "127.0.0.1"
PORT = 55439
SOURCE = "grid_ci_disposable"
TARGET_PREFIX = "grid_ci_restore_"
USER = "grid_ci"


def run(*args):
    # Client tools come from the same pinned major PostgreSQL image as the service.
    # Never allow this helper to be called outside its isolated hosted job.
    if (os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.getenv("RUNNER_OS") != "Linux"
            or os.getenv("GITHUB_REPOSITORY") != "YehorBabenko88/bybit-cluster-grid"
            or os.getenv("GRID_DISPOSABLE_PG18") != "YES"
            or os.getenv("GRID_DISPOSABLE_PG_DSN") != "postgresql://grid_ci:ci_only_disposable@127.0.0.1:55439/grid_ci_disposable"):
        raise RuntimeError("PG18_RESTORE_SUBPROCESS_GUARD")
    archive_paths = [a for a in args if isinstance(a, str) and a.endswith(".dump")]
    mounts = []
    if archive_paths:
        parent = str(pathlib.Path(archive_paths[0]).parent)
        mounts = ["--volume", parent + ":" + parent]
    cmd = ["docker", "run", "--rm", "--network", "host", *mounts,
           "--env", "PGPASSWORD=ci_only_disposable", "postgres:18", *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=90)


class RestoreDrill(unittest.TestCase):
    def test_backup_and_restore(self):
        required = {
            "GITHUB_ACTIONS": "true",
            "GRID_DISPOSABLE_PG18": "YES",
            "RUNNER_ENVIRONMENT": "github-hosted",
            "RUNNER_OS": "Linux",
            "GITHUB_REPOSITORY": "YehorBabenko88/bybit-cluster-grid",
            "GRID_DISPOSABLE_PG_DSN": "postgresql://grid_ci:ci_only_disposable@127.0.0.1:55439/grid_ci_disposable",
            "PGHOST": HOST, "PGPORT": str(PORT), "PGUSER": USER,
            "PGDATABASE": SOURCE, "PGPASSWORD": "ci_only_disposable",
        }
        if any(os.getenv(key) != value for key, value in required.items()):
            raise RuntimeError("PG18_RESTORE_HOSTED_GUARD")
        with psycopg.connect(os.environ["GRID_DISPOSABLE_PG_DSN"]) as c:
            v = int(c.execute("select current_setting('server_version_num')").fetchone()[0])
            if not 180000 <= v < 190000: raise RuntimeError("PG18_RESTORE_VERSION_MISMATCH")
            c.execute("create table if not exists ci_restore_probe (id integer primary key, payload text not null)")
            c.execute("insert into ci_restore_probe values (1,'alpha'),(2,'beta') on conflict (id) do update set payload=excluded.payload")
            c.commit()
            source_rows = c.execute("select id,payload from ci_restore_probe order by id").fetchall()
        # Never adopt or DROP a fixed database name. Every run owns a unique target.
        target = TARGET_PREFIX + uuid.uuid4().hex
        created_target = False
        with tempfile.TemporaryDirectory(prefix="grid-pg18-backup-") as directory:
            archive = pathlib.Path(directory) / "snapshot.dump"
            run("pg_dump", "--format=custom", "--no-owner", "--no-acl",
                "--host", HOST, "--port", str(PORT), "--username", USER,
                "--dbname", SOURCE, "--file", str(archive))
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(len(digest), 64)
            self.assertGreater(archive.stat().st_size, 0)
            run("pg_restore", "--list", str(archive))
            run("createdb", "--host", HOST, "--port", str(PORT), "--username", USER, target)
            created_target = True
            try:
                run("pg_restore", "--exit-on-error", "--single-transaction", "--no-owner",
                    "--no-acl", "--host", HOST, "--port", str(PORT), "--username", USER,
                    "--dbname", target, str(archive))
                with psycopg.connect(
                    f"postgresql://{USER}:ci_only_disposable@{HOST}:{PORT}/{target}"
                ) as restored:
                    self.assertEqual(restored.execute("select id,payload from ci_restore_probe order by id").fetchall(), source_rows)
                    self.assertEqual(restored.execute("select count(*) from pg_constraint where conrelid='ci_restore_probe'::regclass and contype='p'").fetchone()[0], 1)
                self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), digest)
            finally:
                if created_target:
                    run("dropdb", "--host", HOST, "--port", str(PORT),
                        "--username", USER, target)


if __name__ == "__main__":
    unittest.main()
