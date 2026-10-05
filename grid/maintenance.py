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


async def cleanup_control_metadata(pool):
    # Reservations are advisory capacity locks and are invalid after expiry.
    reservations=await purge_expired(pool)
    # Keep recent operational history, but do not grow terminal jobs forever.
    jobs=await pool.execute("""DELETE FROM ml_jobs
      WHERE status IN ('done','failed','cancelled') AND finished_at<now()-interval '30 days'""")
    # Failed/incomplete snapshots are not immutable training inputs. READY snapshots
    # are deliberately retained because models/audits may reference them.
    datasets=await pool.execute("""DELETE FROM dataset_snapshots d
      WHERE d.status IN ('FAILED','BUILDING') AND d.created_at<now()-interval '7 days'
      AND NOT EXISTS(SELECT 1 FROM model_registry m WHERE m.dataset_id=d.id)""")
    return {"reservations":reservations,"jobs":jobs,"datasets":datasets}


async def maintenance_scheduler(pool,settings):
    root=pathlib.Path(os.environ.get("ProgramData",r"C:\ProgramData"))/"BybitClusterGrid"
    while True:
        try:
            meta=await cleanup_control_metadata(pool)
            temps=cleanup_owned_temp_files(root)
            log.info("maintenance completed",extra={
                "event":"maintenance_complete",
                "component":str({"metadata":meta,"temp_files":temps}),
            })
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("maintenance failed",extra={"event":"maintenance_failed"})
        await asyncio.sleep(3600)
