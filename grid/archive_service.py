import asyncio,os,logging
from .service import prepare_database,bootstrap_logging
from .config import settings
from .bybit import linear_symbols
from .archive_discovery_service import seed_discovery
from .market_backfill import seed_backfill,run_backfill_worker
from .archive_pipeline_service import run_discovery_worker,run_archive_worker

log=logging.getLogger("archive_service")

async def service_loop(stop_event=None):
    stop_event=stop_event or asyncio.Event()
    db=await prepare_database()
    os.makedirs(settings.archive_root,exist_ok=True)
    while not stop_event.is_set():
        try:
            xs=await linear_symbols(settings.bybit_rest_url)
            await seed_discovery(db.pool,xs)
            await seed_backfill(db.pool,xs)
            ticks={x["symbol"]:x["tick_size"] for x in xs}
            await asyncio.gather(
                run_discovery_worker(db.pool,settings.bybit_archive_base_url,
                                     settings.archive_probe_days,stop_event),
                run_archive_worker(db.pool,settings.archive_root,ticks,5,stop_event),
                run_backfill_worker(db.pool,settings.bybit_rest_url,stop_event,max_pages=50),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("archive pipeline cycle failed",extra={"event":"archive_pipeline_cycle_failed"})
        try:
            await asyncio.wait_for(stop_event.wait(),timeout=30)
        except asyncio.TimeoutError:
            pass

def main():
    bootstrap_logging()
    asyncio.run(service_loop())

if __name__=="__main__":
    main()
