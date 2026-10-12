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
    assert "ts<=$1::timestamptz" in pool.query
    assert pool.args==(checkpoint,)


def test_feature_hydration_initial_empty_checkpoint_is_safe():
    pool=FakePool()
    service=ScientificResearchService(pool)
    asyncio.run(service._hydrate_features())
    assert pool.args==(None,)
