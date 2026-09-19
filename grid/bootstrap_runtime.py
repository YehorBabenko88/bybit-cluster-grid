import asyncio,logging
from .bybit import fetch_linear_symbols
from .cold_start import readiness,research_allowed
from .migrations import apply_migrations

log=logging.getLogger("bootstrap_runtime")

async def bootstrap_runtime(db,coordinator=None):
    """Idempotent first-run sequence for an empty installation."""
    await apply_migrations(db.pool)
    symbols=await fetch_linear_symbols()
    if not symbols:raise RuntimeError("Bybit discovery returned no linear symbols")
    if coordinator is not None:
        await coordinator.refresh_instruments(symbols)
    snap=await readiness(db.pool)
    log.info("cold start readiness",extra={"event":"cold_start","component":str(snap)})
    return {"discovered_symbols":len(symbols),"readiness":snap}

async def wait_for_research_readiness(pool,interval=60,stop_event=None):
    stop_event=stop_event or asyncio.Event()
    while not stop_event.is_set():
        snap=await readiness(pool)
        if research_allowed(snap):return snap
        try:await asyncio.wait_for(stop_event.wait(),timeout=max(10,int(interval)))
        except asyncio.TimeoutError:pass
    return await readiness(pool)
