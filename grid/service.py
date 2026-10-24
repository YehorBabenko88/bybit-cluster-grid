import asyncio, logging
from .db import Database
from .schema_contract import verify_runtime_schema
from .logging_setup import setup_logging
from .resources import snapshot
from .config import settings

log=logging.getLogger("service")

async def prepare_database():
    """Connect and verify only. Schema preparation is an explicit offline command.

    Incompatible schema/privileges are fatal; retries must never hide a partial
    installation or fall back to owner credentials.
    """
    db=Database()
    try:
        await db.connect()
        await verify_runtime_schema(db.pool)
        return db
    except BaseException:
        if db.pool is not None:
            try:
                await db.pool.close()
            finally:
                db.pool=None
        raise

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
