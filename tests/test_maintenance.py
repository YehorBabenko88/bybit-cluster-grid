from pathlib import Path
import time
from grid.maintenance import cleanup_owned_temp_files


def test_control_starts_retention_and_maintenance():
    s=Path("grid/coordinator.py").read_text(encoding="utf-8")
    startup=s.split("async def startup():",1)[1].split('@app.on_event("shutdown")',1)[0]
    assert "retention_scheduler(db.pool,settings)" in startup
    assert "maintenance_scheduler(db.pool,settings)" in startup


def test_temp_cleanup_only_removes_old_owned_temp_files(tmp_path):
    old=tmp_path/"old.part";old.write_text("x")
    fresh=tmp_path/"fresh.tmp";fresh.write_text("x")
    keep=tmp_path/"model.bin";keep.write_text("x")
    age=time.time()-90000
    import os
    os.utime(old,(age,age))
    removed=cleanup_owned_temp_files(tmp_path,older_than_seconds=86400)
    assert removed==1
    assert not old.exists()
    assert fresh.exists()
    assert keep.exists()


def test_maintenance_never_deletes_ready_datasets_or_registered_models():
    s=Path("grid/maintenance.py").read_text(encoding="utf-8")
    assert "d.status IN ('FAILED','BUILDING')" in s
    assert "NOT EXISTS(SELECT 1 FROM model_registry" in s
    assert "DELETE FROM model_registry" not in s


def test_strategy_cache_cleanup_is_reproducible_only(tmp_path):
    from grid.maintenance import cleanup_strategy_cache
    import os,time
    p=tmp_path/"s"/"1"/"hash";p.mkdir(parents=True)
    f=p/"strategy.py";f.write_text("x")
    age=time.time()-8*86400;os.utime(f,(age,age))
    assert cleanup_strategy_cache(tmp_path)==1
    assert not f.exists()


def test_ml_cleanup_is_reference_aware_and_no_vacuum_full():
    s=Path("grid/maintenance.py").read_text(encoding="utf-8")
    assert "NOT EXISTS(SELECT 1 FROM ml_artifacts a WHERE a.owner_job=j.id" in s
    assert "NOT EXISTS(SELECT 1 FROM model_registry m WHERE m.artifact_id=a.id)" in s
    assert "status='DELETING'" in s
    assert "VACUUM FULL" in s  # documented prohibition
    executable=[line for line in s.splitlines() if "VACUUM FULL" in line and not line.lstrip().startswith("#")]
    assert not executable
    assert 'await c.execute(f"ANALYZE {table}")' in s


def test_archive_orphan_cleanup_does_not_touch_part_files(tmp_path):
    from grid.maintenance import cleanup_orphan_archive_files
    import os,time
    raw=tmp_path/"grid-archive-old";raw.write_text("x")
    part=tmp_path/"grid-archive-active.part";part.write_text("x")
    age=time.time()-90000
    os.utime(raw,(age,age));os.utime(part,(age,age))
    assert cleanup_orphan_archive_files(tmp_path)==1
    assert not raw.exists()
    assert part.exists()


def test_owned_postgres_log_cleanup_is_manifest_fenced(tmp_path):
    import json,os,time
    from grid.maintenance import cleanup_owned_postgres_logs
    data=tmp_path/"grid"; pg=data/"postgres"; pgdata=pg/"data"; logs=pgdata/"log"
    logs.mkdir(parents=True)
    old=logs/"postgresql-old.log"; old.write_text("x")
    os.utime(old,(time.time()-15*86400,)*2)
    # No ownership manifest: never touch PostgreSQL-looking paths.
    assert cleanup_owned_postgres_logs(data)==0
    assert old.exists()
    (data/"postgres-owned.json").write_text(json.dumps({
        "owned_by_grid":True,"service_name":"BybitClusterGridPostgres","port":55432,
        "root":str(pg),"data":str(pgdata)
    }),encoding="utf-8")
    assert cleanup_owned_postgres_logs(data)==1
    assert not old.exists()


def test_grid_owned_postgres_has_wal_and_log_bounds():
    s=Path("installer/install-postgres.ps1").read_text(encoding="utf-8")
    assert "max_wal_size = '2GB'" in s
    assert "min_wal_size = '256MB'" in s
    assert "log_rotation_age = 1d" in s
    assert "log_rotation_size = 100MB" in s
    assert "BybitClusterGridPostgres" in s
