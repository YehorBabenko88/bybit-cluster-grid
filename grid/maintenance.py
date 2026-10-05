import asyncio
import logging
import os
import pathlib
import time

from .ml_reservations import purge_expired
from .disk_guard import DiskWatermarks,disk_state
from .ml_artifact_store import LocalArtifactStore
from .ml_artifact_gc import delete_owned_artifacts
from .schema_audit import schema_type_audit
from .update_manager import cleanup_release_storage

log=logging.getLogger("maintenance")


def cleanup_owned_temp_files(root,older_than_seconds=86400):
    root=pathlib.Path(root)
    if not root.exists():return 0
    cutoff=time.time()-max(3600,int(older_than_seconds));removed=0
    patterns=("*.tmp","*.part")
    for pattern in patterns:
        for p in root.rglob(pattern):
            try:
                if p.is_file() and p.stat().st_mtime<cutoff:
                    p.unlink();removed+=1
            except OSError:
                pass
    return removed


def cleanup_strategy_cache(root,older_than_seconds=7*86400):
    """Strategy cache is reproducible from DB source_code; remove only old materialized files."""
    root=pathlib.Path(root)
    if not root.exists():return 0
    cutoff=time.time()-max(86400,int(older_than_seconds));removed=0
    for p in root.rglob("strategy.py"):
        try:
            if p.is_file() and p.stat().st_mtime<cutoff:
                p.unlink();removed+=1
        except OSError:pass
    # Remove empty hash/version/name directories bottom-up.
    for p in sorted((x for x in root.rglob("*") if x.is_dir()),key=lambda x:len(x.parts),reverse=True):
        try:p.rmdir()
        except OSError:pass
    return removed


def cleanup_orphan_archive_files(root,older_than_seconds=86400):
    """Remove completed raw downloads left by failed processing; active .part files use temp cleanup."""
    root=pathlib.Path(root)
    if not root.exists():return 0
    cutoff=time.time()-max(3600,int(older_than_seconds));removed=0
    for p in root.glob("grid-archive-*"):
        try:
            if p.is_file() and not p.name.endswith(".part") and p.stat().st_mtime<cutoff:
                p.unlink();removed+=1
        except OSError:pass
    return removed


async def cleanup_control_metadata(pool):
    # Reservations are advisory capacity locks and are invalid after expiry.
    reservations=await purge_expired(pool)
    # Keep recent operational history, but do not grow terminal jobs forever.
    jobs=await pool.execute("""DELETE FROM ml_jobs j
      WHERE j.status IN ('done','failed','cancelled') AND j.finished_at<now()-interval '30 days'
      AND NOT EXISTS(SELECT 1 FROM ml_artifacts a WHERE a.owner_job=j.id AND a.status<>'DELETED')""")
    # Failed/incomplete snapshots are not immutable training inputs. READY snapshots
    # are deliberately retained because models/audits may reference them.
    datasets=await pool.execute("""DELETE FROM dataset_snapshots d
      WHERE d.status IN ('FAILED','BUILDING') AND d.created_at<now()-interval '7 days'
      AND NOT EXISTS(SELECT 1 FROM model_registry m WHERE m.dataset_id=d.id)""")
    artifacts=await pool.execute("""UPDATE ml_artifacts a SET status='DELETING'
      WHERE a.status='ACTIVE' AND a.reusable=false AND a.expires_at IS NOT NULL AND a.expires_at<now()
      AND NOT EXISTS(SELECT 1 FROM model_registry m WHERE m.artifact_id=a.id)""")
    return {"reservations":reservations,"jobs":jobs,"datasets":datasets,"artifacts_marked":artifacts}


async def maintain_postgres_statistics(pool):
    # ANALYZE is online and helps the planner after large retention batches.
    # VACUUM FULL is intentionally forbidden here because it takes exclusive locks.
    tables=("market_events","orderbook_snapshots","footprint_1m","candles_1m",
            "derivatives_metrics","ml_jobs","dataset_snapshots")
    async with pool.acquire() as c:
        for table in tables:
            try:await c.execute(f"ANALYZE {table}")
            except Exception:
                log.debug("analyze skipped",extra={"event":"analyze_skipped","component":table},exc_info=True)
        rows=await c.fetch("""SELECT relname,n_live_tup,n_dead_tup,
          last_autovacuum,last_autoanalyze
          FROM pg_stat_user_tables
          WHERE relname=ANY($1::text[])""",list(tables))
    return [dict(x) for x in rows]


async def maintenance_scheduler(pool,settings):
    root=pathlib.Path(os.environ.get("ProgramData",r"C:\ProgramData"))/"BybitClusterGrid"
    while True:
        try:
            policy=DiskWatermarks(
                soft_free_gb=float(settings.disk_soft_free_gb),
                hard_free_gb=float(settings.disk_hard_free_gb),
                emergency_free_gb=float(settings.disk_emergency_free_gb))
            disk=disk_state(root,policy)
            aggressive=disk["state"]!="NORMAL"
            meta=await cleanup_control_metadata(pool)
            artifact_gc=await delete_owned_artifacts(pool,LocalArtifactStore(settings.ml_artifact_root))
            temps=cleanup_owned_temp_files(root,3600 if aggressive else 86400)
            strategy=cleanup_strategy_cache(pathlib.Path(settings.strategy_cache_dir),
                                            86400 if aggressive else 7*86400)
            archive=cleanup_orphan_archive_files(pathlib.Path(settings.archive_root),
                                                 3600 if aggressive else 86400)
            install_root=pathlib.Path(os.environ.get("ProgramFiles",r"C:\\Program Files"))/"BybitClusterGrid"
            releases=cleanup_release_storage(install_root,root,keep_recent=2,
                                             older_than_seconds=3600 if aggressive else 86400)
            pgstats=await maintain_postgres_statistics(pool)
            schema=await schema_type_audit(pool)
            if not schema["ok"]:
                log.error("database schema type drift detected",extra={
                    "event":"schema_type_drift","component":str(schema)})
            log.info("maintenance completed",extra={
                "event":"maintenance_complete",
                "component":str({"metadata":meta,"temp_files":temps,"strategy_cache":strategy,
                                 "archive_orphans":archive,"release_cleanup":releases,"pg_tables":len(pgstats),
                                 "disk":disk["state"],"disk_free_gb":round(disk["free_gb"],2),
                                 "schema_ok":schema["ok"]}),
            })
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("maintenance failed",extra={"event":"maintenance_failed"})
        await asyncio.sleep(3600)
