import asyncio
from grid.startup_status import startup_status


class Pool:
    async def fetchrow(self,sql,*args):return {"state":"ACTIVE","reason":"","updated_at":None}
    async def fetchval(self,sql,*args):
        if "agent_credentials" in sql:return 2
        if "ohlcv_1m" in sql:return 1000
        if "candles_1m" in sql:return 500
        if "market_features_1m" in sql:return 400
        if "trade_archive_backfill" in sql:return 20
        if "materialized_at IS NOT NULL" in sql:return 5
        if "market_backfill_state" in sql:return 3
        if "archive_compute_jobs" in sql:return 7
        return 0


def test_startup_status_reports_end_to_end_pipeline_progress():
    s=asyncio.run(startup_status(Pool()))
    assert s["phase"]=="ANALYSIS_READY"
    assert s["registered_nodes"]==2
    assert s["ohlcv_rows"]==1000 and s["features"]==400
    assert s["archive_materialized"]==5 and s["archive_pending"]==7
