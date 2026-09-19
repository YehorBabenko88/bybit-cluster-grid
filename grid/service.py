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
        except Exception:
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
        await asyncio.sleep(10)

def bootstrap_logging():
    setup_logging()
