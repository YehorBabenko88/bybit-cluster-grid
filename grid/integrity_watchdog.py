import asyncio,logging
from .integrity_guard import verify_manifest,repair_plan
log=logging.getLogger("integrity_watchdog")

async def integrity_watchdog(root,manifest,request_repair,interval_seconds=300):
    while True:
        try:
            report=verify_manifest(root,manifest)
            if not report["ok"]:
                plan=repair_plan(report)
                log.error("grid integrity mismatch",extra={"event":"integrity_mismatch","component":str(plan)})
                if plan: await request_repair(plan,report.get("version"))
        except asyncio.CancelledError:raise
        except Exception:
            log.exception("integrity watchdog failed",extra={"event":"integrity_watchdog_error"})
        await asyncio.sleep(max(60,int(interval_seconds)))
