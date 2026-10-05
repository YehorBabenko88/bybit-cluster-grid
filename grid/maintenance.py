import asyncio
import logging
import os
import pathlib
import time

from .ml_reservations import purge_expired

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


async def maintenance_scheduler(pool,settings):
    root=pathlib.Path(os.environ.get("ProgramData",r"C:\ProgramData"))/"BybitClusterGrid"
    while True:
        try:
            meta=await cleanup_control_metadata(pool)
            temps=cleanup_owned_temp_files(root)
            strategy=cleanup_strategy_cache(pathlib.Path(settings.strategy_cache_dir))
            archive=cleanup_orphan_archive_files(pathlib.Path(settings.archive_root))
            log.info("maintenance completed",extra={
                "event":"maintenance_complete",
                "component":str({"metadata":meta,"temp_files":temps,"strategy_cache":strategy,"archive_orphans":archive}),
            })
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("maintenance failed",extra={"event":"maintenance_failed"})
        await asyncio.sleep(3600)
