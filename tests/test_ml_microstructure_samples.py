from datetime import datetime,timedelta,timezone
import asyncio,json\nimport pytest

from grid.ml_microstructure_samples import ContinuousMicrostructureSamples,_target


def test_target_uses_only_future_bars_and_full_horizon():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    sample={"horizon_seconds":120,"features":{"bid":99.0,"ask":101.0}}
    bars=[
        {"ts":t+timedelta(minutes=1),"open":100,"high":102,"low":99,"close":101},
        {"ts":t+timedelta(minutes=2),"open":101,"high":103,"low":98,"close":102},
    ]
    x=_target(sample,bars)
    assert x["reference_price"]==100.0
    assert x["future_return"]==pytest.approx(0.02)
    assert x["mfe"]==pytest.approx(0.03)
    assert x["mae"]==pytest.approx(-0.02)
    assert x["up"] is True
    assert _target({"horizon_seconds":180,"features":{"bid":99,"ask":101}},bars) is None


class Pool:
    def __init__(self,t):
        self.t=t; self.inserted=[]; self.updated=[]
    async def fetch(self,sql,*args):
        if "FROM microstructure_samples" in sql:
            return [{"symbol":"BTCUSDT","ts":self.t,"known_at":self.t+timedelta(milliseconds=20),
                     "payload":{"bid":99.0,"ask":101.0,"trade_available":True}}]
        if "FROM microstructure_ml_samples" in sql:
            return [{"id":1,"feature_ts":self.t,"known_at":self.t+timedelta(milliseconds=20),
                     "horizon_seconds":60,"features":{"bid":99.0,"ask":101.0},
                     "label_end_ts":self.t+timedelta(minutes=1)}]
        if "FROM candles_1m" in sql:
            assert args[1]==self.t
            return [{"ts":self.t+timedelta(minutes=1),"open":100,"high":101,"low":99,"close":100.5}]
        return []
    async def executemany(self,sql,rows):
        self.inserted.extend(rows)
    async def execute(self,sql,*args):
        self.updated.append((sql,args))


def test_materialize_freezes_known_at_and_labels_only_after_horizon():
    async def run():
        t=datetime(2026,1,1,tzinfo=timezone.utc)
        p=Pool(t); s=ContinuousMicrostructureSamples(p,horizons_seconds=(60,))
        assert await s.materialize("BTCUSDT",t+timedelta(minutes=2))==1
        row=p.inserted[0]
        assert row[1]==t
        assert row[2]==t+timedelta(milliseconds=20)
        assert row[5]==t+timedelta(minutes=1)
        assert await s.label_ready("BTCUSDT",t+timedelta(minutes=1))==1
        target=json.loads(p.updated[0][1][1])
        assert target["future_return"]==pytest.approx(0.005)
    asyncio.run(run())
