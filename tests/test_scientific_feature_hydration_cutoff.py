import asyncio
from datetime import datetime,timezone
from grid.scientific_service import ScientificResearchService


class FakePool:
    def __init__(self):
        self.query=None
        self.args=None
    async def fetch(self,query,*args):
        self.query=query
        self.args=args
        return []


def test_feature_hydration_does_not_load_future_checkpoint_data():
    pool=FakePool()
    service=ScientificResearchService(pool)
    checkpoint=datetime(2026,10,9,tzinfo=timezone.utc)
    service.last_event_ts=checkpoint
    asyncio.run(service._hydrate_features())
    assert "ts<=$1::timestamptz - interval '1 minute'" in pool.query
    assert pool.args==(checkpoint,)


def test_feature_hydration_initial_empty_checkpoint_is_safe():
    pool=FakePool()
    service=ScientificResearchService(pool)
    asyncio.run(service._hydrate_features())
    assert pool.query is None


def test_feature_hydration_excludes_unclosed_checkpoint_minute():
    from datetime import timedelta
    checkpoint=datetime(2026,10,9,12,0,30,tzinfo=timezone.utc)
    closed=datetime(2026,10,9,11,59,tzinfo=timezone.utc)
    current=datetime(2026,10,9,12,0,tzinfo=timezone.utc)
    class RowsPool:
        async def fetch(self,query,*args):
            # Return an over-inclusive source to verify the availability fence
            # also protects the consumer, independent of the DB predicate.
            return [{"symbol":"BTC","ts":ts,"features":{},"quality_status":"GOOD"}
                    for ts in (closed,current)]
    service=ScientificResearchService(RowsPool())
    service.last_event_ts=checkpoint
    seen=[]
    service.orchestrator.ingest_feature_row=lambda symbol,ts,*args:seen.append(ts)
    asyncio.run(service._hydrate_features())
    assert seen==[int(closed.timestamp()*1000)]


def test_feature_hydration_includes_minute_at_exact_close():
    checkpoint=datetime(2026,10,9,12,1,tzinfo=timezone.utc)
    start=datetime(2026,10,9,12,0,tzinfo=timezone.utc)
    class RowsPool:
        async def fetch(self,query,*args):
            return [{"symbol":"BTC","ts":start,"features":{},"quality_status":"GOOD"}]
    service=ScientificResearchService(RowsPool())
    service.last_event_ts=checkpoint
    seen=[]
    service.orchestrator.ingest_feature_row=lambda symbol,ts,*args:seen.append(ts)
    asyncio.run(service._hydrate_features())
    assert seen==[int(start.timestamp()*1000)]
