import copy
import time
import uuid
import pytest
from grid.provenance import minute_record, producer, digest
from grid import terminan_gateway as gateway
from grid.research_handoff import accept_handoff

def row(start=None):
    start = start if start is not None else (int(time.time()*1000)//60000-1)*60000
    return dict(symbol="BTCUSDT",start_ms=start,source_event_start_ms=start+1,source_event_end_ms=start+59999,
        source_provenance=producer("fixture", "a"*40, "wss://stream.bybit.com/v5/public/linear"),
        open=1,high=2,low=1,close=2,buy_volume=1,sell_volume=0,delta=1,trade_count=1,poc_price=2,
        quality_status="GOOD",quality_reasons=[],levels=[{"price":2}])

def test_owner_declaration_and_digest_are_not_completeness_attestation():
    r=minute_record(row(),int(time.time()*1000),"fixture")
    assert r["status"]=="PARTIAL"
    assert r["coverage"]["exchange_completeness_attested"] is False
    assert r["dataset_fingerprint"]==digest({k:v for k,v in r.items() if k!="dataset_fingerprint"})

@pytest.mark.parametrize("mutate",[
    lambda r:r.pop("source_provenance"),lambda r:r["source_provenance"].update(identity="spoof"),
    lambda r:r["source_provenance"].update(market_type=None),lambda r:r["source_provenance"].update(epoch="bad"),
    lambda r:r.update(source_event_start_ms=True),lambda r:r.update(source_event_end_ms=r["start_ms"]+60000)])
def test_bad_attestations_fail_closed(mutate):
    r=row();mutate(r)
    assert minute_record(r,int(time.time()*1000),"fixture")["status"]=="UNAVAILABLE"

def test_restart_has_new_epoch():
    assert row()["source_provenance"]["epoch"] != row()["source_provenance"]["epoch"]

def test_gateway_integrity_gaps_stale_and_restart(monkeypatch):
    monkeypatch.setenv("TERMINAN_GRID_PROVENANCE_READ","1")
    now=int(time.time()*1000); r=row(); a=minute_record(r,now,"fixture")
    monkeypatch.setattr(gateway,"immutable_minutes",lambda *args:[a])
    assert gateway.snapshot("/internal/v1/candles")["status"]=="PARTIAL"
    a["candle"]["close"]=999
    assert gateway.snapshot("/internal/v1/candles")["reason"]=="SNAPSHOT_INTEGRITY_FAILED"
    a=minute_record(row(0),now,"fixture")
    monkeypatch.setattr(gateway,"immutable_minutes",lambda *args:[a])
    assert gateway.snapshot("/internal/v1/candles")["status"]=="STALE"
    b=minute_record(row(120000),now,"fixture")
    monkeypatch.setattr(gateway,"immutable_minutes",lambda *args:[a,b])
    assert gateway.snapshot("/internal/v1/candles")["status"]=="GAP"
    monkeypatch.setattr(gateway,"immutable_minutes",lambda *args:[a,a])
    assert gateway.snapshot("/internal/v1/candles")["reason"]=="AMBIGUOUS_MINUTE_REVISIONS"

def handoff():
    r=dict(api_version={"major":1,"minor":1},producer="strattester",producer_identity="fixture",
        source_revision="a"*40,producer_epoch=str(uuid.uuid4()),run_id=str(uuid.uuid4()),mode="HISTORICAL",execution_authority=False,
        dataset=dict(fingerprint="b"*64,source_identity="fixture",market_type="linear",symbol="BTCUSDT",timeframe="1m",start_ms=0,end_ms=60000,coverage="COMPLETE",missing_data=[]),
        strategy={"id":"fixture"},model={"id":"fixture"},execution_assumptions={"fees":1},metrics={"x":1},completed_at_ms=60001)
    r["completion_receipt"]=digest(r);return r

def test_research_handoff_requires_trust_and_never_trades():
    r=handoff();trust={("fixture","a"*40,r["run_id"],r["completion_receipt"])}
    assert accept_handoff(r,set())["reason"]=="SOURCE_IDENTITY_UNATTESTED"
    out=accept_handoff(r,trust)
    assert out["status"]=="ACCEPTED_HISTORICAL" and out["trading_authorized"] is False
    r["execution_authority"]=True
    assert accept_handoff(r,trust)["status"]=="UNAVAILABLE"

@pytest.mark.parametrize("change",[lambda r:r.update(completion_receipt="0"*64),lambda r:r.update(api_version={"major":2,"minor":0}),lambda r:r.update(completed_at_ms=True),lambda r:r["dataset"].update(missing_data=[1])])
def test_handoff_adversarial(change):
    r=handoff();change(r)
    assert accept_handoff(r,{("fixture","a"*40,r["run_id"],r["completion_receipt"])})["status"]=="UNAVAILABLE"


def test_event_time_ohlc_duplicate_and_late_trades():
    from grid.cluster import FootprintBuilder
    from grid.models import Trade
    b=FootprintBuilder(1)
    assert b.add(Trade(symbol="BTCUSDT",ts_ms=2000,price=2,qty=1,side="Buy",trade_id="b"))
    assert b.add(Trade(symbol="BTCUSDT",ts_ms=1000,price=1,qty=1,side="Buy",trade_id="a"))
    assert not b.add(Trade(symbol="BTCUSDT",ts_ms=1000,price=1,qty=1,side="Buy",trade_id="a"))
    r=b.pop_closed(60000)[0]
    assert (r['open'],r['close'],r['trade_count'])==(1,2,2)
    assert not b.add(Trade(symbol="BTCUSDT",ts_ms=3000,price=3,qty=1,side="Buy",trade_id="c"))


def test_cancellation_during_snapshot_write_propagates():
    import asyncio
    from grid.provenance import persist_minute
    class C:
        async def execute(self,*args):raise asyncio.CancelledError()
    async def check():
        with pytest.raises(asyncio.CancelledError):await persist_minute(C(),row(),"fixture")
    asyncio.run(check())


def test_disposable_pg_immutability_and_idempotency(monkeypatch):
    import os
    import asyncio
    dsn=os.environ.get('TERMINAN_DISPOSABLE_PG18_DSN')
    if not dsn:pytest.skip('explicit disposable PG18 required')
    import asyncpg
    from grid.migrations import MIGRATIONS
    from grid.provenance import persist_minute
    async def check():
        c=await asyncpg.connect(dsn)
        schema='fixture_'+uuid.uuid4().hex
        try:
            await c.execute('CREATE SCHEMA '+schema)
            await c.execute('SET search_path TO '+schema)
            for sql in next(sqls for version,name,sqls in MIGRATIONS if version==47):await c.execute(sql)
            r=row()
            async with c.transaction():await persist_minute(c,r,'fixture')
            async with c.transaction():await persist_minute(c,r,'fixture')
            assert await c.fetchval('SELECT count(*) FROM provenance_minutes')==1
            with pytest.raises(asyncpg.PostgresError):
                async with c.transaction():await c.execute("UPDATE provenance_minutes SET symbol='BAD'")
            with pytest.raises(asyncpg.PostgresError):
                async with c.transaction():await c.execute('DELETE FROM provenance_minutes')
            assert await c.fetchval('SELECT count(*) FROM provenance_minutes')==1
            with pytest.raises(RuntimeError):
                async with c.transaction():
                    await persist_minute(c,row(0),'fixture')
                    raise RuntimeError('cancel simulated')
            assert await c.fetchval('SELECT count(*) FROM provenance_minutes')==1
        finally:
            await c.execute('DROP SCHEMA '+schema+' CASCADE')
            await c.close()
    asyncio.run(check())
