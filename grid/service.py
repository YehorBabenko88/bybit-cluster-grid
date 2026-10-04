import asyncio, logging
from .db import Database
from .migrations import apply_migrations
from .logging_setup import setup_logging
from .resources import snapshot
from .config import settings

log=logging.getLogger("service")

async def prepare_database():
    db=Database()
    delay=1
    while True:
        try:
            await db.connect()
            await db.ensure_schema()
            await apply_migrations(db.pool)
            return db
        except asyncio.CancelledError:
            if db.pool is not None:
                await db.pool.close()
                db.pool=None
            raise
        except Exception:
            # A failed schema/migration attempt can leave an otherwise live pool
            # behind. Close it before retrying so repeated startup failures cannot
            # leak connections or exhaust PostgreSQL.
            if db.pool is not None:
                try:
                    await db.pool.close()
                except Exception:
                    log.exception("failed to close database pool after startup error",
                                  extra={"event":"db_pool_close_failed"})
                finally:
                    db.pool=None
            log.exception("database startup failed",extra={"event":"db_start_retry","delay":delay})
            await asyncio.sleep(delay)
            delay=min(30,delay*2)

async def health_monitor(stop_event=None):
    while stop_event is None or not stop_event.is_set():
        s=snapshot()
        if s["cpu_pct"] >= settings.resource_cpu_limit:
            log.warning("cpu pressure",extra={"event":"resource_pressure"})
        if s["ram_pct"] >= settings.resource_ram_limit:
            log.warning("ram pressure",extra={"event":"resource_pressure"})
        if s["disk_free"] < settings.resource_disk_free_gb*1024**3:
            log.error("low disk space",extra={"event":"disk_pressure"})
        try:
            if stop_event is None:
                await asyncio.sleep(10)
            else:
                await asyncio.wait_for(stop_event.wait(),timeout=10)
        except asyncio.TimeoutError:
            pass

def bootstrap_logging():
    setup_logging()
