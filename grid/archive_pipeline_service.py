import asyncio,logging
from .archive_discovery_service import claim_discovery,scan_symbol
from .archive_job_queue import claim_archive_job,fail_archive_job,recover_stale_archive_jobs
from .archive_worker import process_archive
from .archive_download import ArchiveUnavailable

log=logging.getLogger("archive_pipeline")

async def run_discovery_worker(pool,base_url,probe_days=30,stop_event=None):
    stop_event=stop_event or asyncio.Event()
    done=failed=0
    while not stop_event.is_set():
        job=await claim_discovery(pool)
        if not job:break
        try:
            await scan_symbol(pool,base_url,job["symbol"],probe_days)
            done+=1
        except asyncio.CancelledError:
            raise
        except Exception:
            failed+=1
            log.exception("archive discovery failed",extra={"event":"archive_discovery_failed","component":job["symbol"]})
    return {"discovered_symbols":done,"failed_symbols":failed}

async def run_archive_worker(pool,archive_root,tick_sizes,max_attempts=5,stop_event=None):
    stop_event=stop_event or asyncio.Event()
    await recover_stale_archive_jobs(pool,max_attempts=max_attempts)
    done=unavailable=failed=0
    while not stop_event.is_set():
        job=await claim_archive_job(pool,max_attempts=max_attempts)
        if not job:break
        symbol=job["symbol"]
        tick=tick_sizes.get(symbol)
        if not tick:
            await fail_archive_job(pool,job,"missing tick size",max_attempts)
            failed+=1
            continue
        try:
            await process_archive(pool,job,archive_root,tick)
            done+=1
        except ArchiveUnavailable:
            await pool.execute("""UPDATE trade_archive_backfill SET status='unavailable',
              last_error='remote archive not found',updated_at=now()
              WHERE symbol=$1 AND archive_date=$2""",symbol,job["archive_date"])
            unavailable+=1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await fail_archive_job(pool,job,exc,max_attempts)
            failed+=1
            log.exception("archive processing failed",extra={"event":"archive_processing_failed","component":symbol})
    return {"processed":done,"unavailable":unavailable,"failed_attempts":failed}
