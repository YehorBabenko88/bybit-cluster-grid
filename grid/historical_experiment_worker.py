import asyncio,logging
from .historical_experiment_state import claim_symbol,finish_symbol,recover_stale
from .historical_experiment_runner import run_symbol

log=logging.getLogger("historical_experiment")

async def run_experiment_worker(pool,run_id,dataset_id,strategy_name,config,stop_event=None):
    stop_event=stop_event or asyncio.Event()
    await recover_stale(pool,run_id,
      stale_minutes=int(config.get("stale_minutes",30)),
      max_attempts=int(config.get("max_symbol_attempts",3)))
    completed=failed=0
    while not stop_event.is_set():
        symbol=await claim_symbol(pool,run_id)
        if not symbol:break
        try:
            await run_symbol(pool,run_id,dataset_id,strategy_name,symbol,config)
            await finish_symbol(pool,run_id,symbol)
            completed+=1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            retryable=not isinstance(exc,(ValueError,KeyError,TypeError))
            await finish_symbol(pool,run_id,symbol,error=exc,retry=retryable)
            failed+=int(not retryable)
            log.exception("historical symbol failed",extra={"event":"historical_symbol_failed","component":symbol})
    return {"completed_this_worker":completed,"failed_this_worker":failed}
