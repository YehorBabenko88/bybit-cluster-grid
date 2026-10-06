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
    s=Path("installer/configure-postgres.ps1").read_text(encoding="utf-8")
    assert "max_wal_size = '2GB'" in s
    assert "min_wal_size = '256MB'" in s
    assert "log_rotation_age = 1d" in s
    assert "log_rotation_size = 100MB" in s
    assert "BybitClusterGridPostgres" in s


def test_ready_snapshot_gc_is_reference_fenced():
    s=Path("grid/maintenance.py").read_text(encoding="utf-8")
    block=s.split("orphan_ready=await pool.execute",1)[1].split("artifacts=await",1)[0]
    assert "d.status='READY'" in block
    assert "interval '30 days'" in block
    for table in (
        "model_registry","model_evaluations","markov_transition_edges",
        "strategy_comparison_results","historical_experiment_runs","ml_jobs"
    ):
        assert table in block
    assert "j.payload->>'dataset_id'=d.id::text" in block


def test_hot_tables_have_early_autovacuum_policy():
    s=Path("grid/migrations.py").read_text(encoding="utf-8")
    block=s.split('(35,"hot_table_autovacuum_policy"',1)[1]
    for table in ("market_events","orderbook_snapshots","footprint_1m",
                  "dataset_sample_payloads","ml_jobs","dataset_snapshots"):
        assert f"ALTER TABLE {table} SET" in block
    assert "autovacuum_vacuum_scale_factor=0.02" in block


def test_maintenance_tracks_relation_size_and_bloat_without_vacuum_full():
    s=Path("grid/maintenance.py").read_text(encoding="utf-8")
    assert "pg_total_relation_size" in s
    assert "dead_ratio" in s
    assert "postgres_bloat_pressure" in s
    executable=[line for line in s.splitlines()
                if "VACUUM FULL" in line and not line.lstrip().startswith("#")]
    assert not executable


def test_artifact_gc_is_bounded_multi_batch():
    s=Path("grid/ml_artifact_gc.py").read_text(encoding="utf-8")
    assert "max_batches=5" in s
    assert "batch_size=200" in s
    assert "for _ in range(max(1,int(max_batches)))" in s


def test_control_disk_pressure_sheds_collection_before_disk_full():
    s=Path("grid/coordinator.py").read_text(encoding="utf-8")
    heartbeat=s.split("async def heartbeat",1)[1].split('@app.post("/commands/',1)[0]
    assert "control_disk=control_disk_state()" in heartbeat
    assert "def control_disk_state():" in s
    assert "live_collection_allowed(control_disk" in heartbeat
    assert 'control_disk["state"]=="NORMAL"' in heartbeat
    assert '"control_disk_state":control_disk["state"]' in heartbeat


def test_retention_backlog_uses_planner_estimate_not_full_count():
    s=Path("grid/retention_v2.py").read_text(encoding="utf-8")
    block=s.split("async def retention_backlog",1)[1]
    assert "EXPLAIN (FORMAT JSON)" in block
    assert "SELECT count(*)" not in block
    scheduler=Path("grid/retention.py").read_text(encoding="utf-8")
    assert '"event":"retention_backlog"' in scheduler


def test_control_ingest_endpoints_enforce_disk_gate():
    s=Path("grid/coordinator.py").read_text(encoding="utf-8")
    minute=s.split("async def ingest_minute",1)[1].split('@app.post("/ingest/event")',1)[0]
    event=s.split("async def ingest_event",1)[1].split('@app.post("/ml/claim")',1)[0]
    assert 'live_collection_allowed(control_disk_state()["state"])' in minute
    assert 'HTTPException(507,"CONTROL disk pressure")' in minute
    assert 'control_disk_state()["state"]!="NORMAL"' in event
    assert 'HTTPException(507,"CONTROL disk pressure")' in event
