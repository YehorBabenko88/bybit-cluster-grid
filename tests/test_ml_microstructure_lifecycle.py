from datetime import datetime,timezone
import asyncio
from grid.ml_microstructure_lifecycle import MicrostructureMLLifecycle,parse_horizons


def test_parse_horizons_is_sorted_unique_and_positive():
    assert parse_horizons("900,60,300,60")== (60,300,900)
    assert parse_horizons([300,60,300])==(60,300)


class Samples:
    def __init__(self): self.calls=[]
    async def materialize(self,symbol,through):
        self.calls.append(("materialize",symbol,through)); return 2
    async def label_ready(self,symbol,through):
        self.calls.append(("label",symbol,through)); return 1


class Pool:
    async def fetch(self,sql,*args):
        assert "SELECT DISTINCT symbol" in sql
        return [{"symbol":"BTCUSDT"},{"symbol":"ETHUSDT"}]
    async def fetchrow(self,sql,*args):
        assert "microstructure_ml_samples" in sql
        return {"ready":7,"pending":3,"degraded":1}


def test_lifecycle_tick_materializes_then_labels_each_symbol():
    async def run():
        p=Pool(); life=MicrostructureMLLifecycle(p,(60,),60); fake=Samples(); life.samples=fake
        now=datetime(2026,1,1,tzinfo=timezone.utc)
        x=await life.tick(now)
        assert x=={"symbols":2,"materialized":4,"labelled":2,"ready":7,"pending":3,"degraded":1}
        assert fake.calls==[
            ("materialize","BTCUSDT",now),("label","BTCUSDT",now),
            ("materialize","ETHUSDT",now),("label","ETHUSDT",now)]
    asyncio.run(run())
