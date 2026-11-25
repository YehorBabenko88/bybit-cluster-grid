"""Actual discovery/backfill codec examples, fake transport/SQL only."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime,timezone
from decimal import Decimal,localcontext
from types import SimpleNamespace
import pytest
from market_data import bybit,market_backfill

@pytest.mark.asyncio
@pytest.mark.parametrize('source',['0.10000000000000000001','1e-1000','0.0100'])
async def test_discovery_exact_tick_is_versioned_decimal_string(monkeypatch,source):
    async def page(*args,**kwargs):return SimpleNamespace(items=({'symbol':'BTCUSDT','status':'Trading','contractType':'LinearPerpetual','priceFilter':{'tickSize':source}},),next_cursor=None)
    monkeypatch.setattr(bybit,'fetch_linear_instruments_page',page)
    row=(await bybit.linear_symbols('https://api.bybit.com',max_attempts=1))[0]
    assert type(row['tick_size']) is str and Decimal(row['tick_size'])==Decimal(source)
    assert row['schema']=='market_data.linear-instrument.v1' and row['tick_size_encoding']=='CANONICAL_EXACT_DECIMAL'

class Connection:
    def __init__(self):self.rows=[]
    @asynccontextmanager
    async def transaction(self):yield self
    async def executemany(self,sql,rows):self.rows.extend(rows)
class Pool:
    def __init__(self):self.c=Connection();self.acquired=0;self.updates=[]
    @asynccontextmanager
    async def acquire(self):self.acquired+=1;yield self.c
    async def execute(self,*args):self.updates.append(args)

def row(stamp):return [stamp,'1','1','1','1','1','1']

@pytest.mark.asyncio
@pytest.mark.parametrize('stamp,expected',[(10000000000001,datetime(2286,11,20,17,46,40,1000,tzinfo=timezone.utc)),(253402300799999,datetime(9999,12,31,23,59,59,999000,tzinfo=timezone.utc)),(0,datetime(1970,1,1,tzinfo=timezone.utc))])
async def test_stored_milliseconds_are_exact_utc_without_float(stamp,expected):
    pool=Pool();lo,hi=await market_backfill.store_kline_page(pool,'BTCUSDT',[row(str(stamp))])
    assert lo==hi==pool.c.rows[0][1]==expected

@pytest.mark.asyncio
@pytest.mark.parametrize('bad',[True,False,1.0,'01','-1','1e3',-1,253402300800000,Decimal(1)])
async def test_bad_timestamp_second_row_refuses_before_any_sql(bad):
    pool=Pool()
    with pytest.raises(ValueError):await market_backfill.store_kline_page(pool,'BTCUSDT',[row('1000'),row(bad)])
    assert pool.acquired==0 and pool.c.rows==[]

@pytest.mark.asyncio
async def test_backfill_cursor_roundtrip_uses_exact_milliseconds(monkeypatch):
    async def page(*args,**kwargs):return [row('10000000000001')]
    monkeypatch.setattr(market_backfill,'fetch_kline_page',page);pool=Pool()
    await market_backfill.backfill_symbol(pool,'https://api.bybit.com',dict(symbol='BTCUSDT',launch_time_ms=10000000000001),max_pages=1,pause=0)
    assert pool.updates[-1][-1]==10000000000000

@pytest.mark.parametrize('stamp,expected',[(0,datetime(1970,1,1,tzinfo=timezone.utc)),(1,datetime(1970,1,1,0,0,0,1000,tzinfo=timezone.utc)),(10000000000001,datetime(2286,11,20,17,46,40,1000,tzinfo=timezone.utc)),(253402300799999,datetime(9999,12,31,23,59,59,999000,tzinfo=timezone.utc))])
def test_strict_calendar_codec_literal_oracles_and_roundtrip(stamp,expected):
    from market_data.timestamp_codec import utc_from_epoch_milliseconds,epoch_milliseconds_from_utc
    assert utc_from_epoch_milliseconds(stamp)==expected
    assert epoch_milliseconds_from_utc(expected)==stamp

@pytest.mark.parametrize('value',[datetime(1970,1,1),datetime(1970,1,1,0,0,0,1,tzinfo=timezone.utc),True,None])
def test_datetime_cursor_refuses_naive_submillisecond_and_non_datetime(value):
    from market_data.timestamp_codec import epoch_milliseconds_from_utc
    with pytest.raises(ValueError):epoch_milliseconds_from_utc(value)

@pytest.mark.asyncio
@pytest.mark.parametrize('source',[True,0,-1,0.1,'NaN','Infinity','1e9999'])
async def test_discovery_has_no_float_or_invalid_tick_compatibility(monkeypatch,source):
    async def page(*args,**kwargs):return SimpleNamespace(items=({'symbol':'BTCUSDT','status':'Trading','contractType':'LinearPerpetual','priceFilter':{'tickSize':source}},),next_cursor=None)
    monkeypatch.setattr(bybit,'fetch_linear_instruments_page',page)
    with pytest.raises(RuntimeError):await bybit.linear_symbols('https://api.bybit.com',max_attempts=1)

@pytest.mark.asyncio
async def test_page_cardinality_refuses_before_iteration_and_sql():
    class Oversized(list):
        def __iter__(self):raise AssertionError('NO_ITERATION')
    pool=Pool()
    with pytest.raises(ValueError):await market_backfill.store_kline_page(pool,'BTCUSDT',Oversized([row('1')]*1001))
    assert pool.acquired==0

def test_archive_day_9999_uses_calendar_codec_not_platform_timestamp():
    from datetime import date
    from market_data.archive_day_boundary import utc_day_boundary
    got=utc_day_boundary(date(9999,12,30))
    assert got.start_ms==253402128000000 and got.end_ms==253402214400000

@pytest.mark.asyncio
async def test_actual_rest_strings_bind_exact_decimal_without_binary64():
    pool=Pool();values=['10000000000001','1.10000000000000000001','1.10000000000000000001','1.10000000000000000001','1.10000000000000000001','1e-1000','0']
    await market_backfill.store_kline_page(pool,'BTCUSDT',[values])
    bound=pool.c.rows[0]
    assert all(type(value) is Decimal for value in bound[2:])
    assert bound[2]==Decimal('1.10000000000000000001') and bound[6]==Decimal('1e-1000') and bound[6]!=0

@pytest.mark.asyncio
@pytest.mark.parametrize('bad',[True,1.1,'NaN','-1',{},'1e99999'])
async def test_invalid_last_numeric_row_refuses_before_pool_acquisition(bad):
    pool=Pool();second=row('2000');second[1]=bad
    with pytest.raises(ValueError):await market_backfill.store_kline_page(pool,'BTCUSDT',[row('1000'),second])
    assert pool.acquired==0 and pool.c.rows==[]

@pytest.mark.asyncio
async def test_validated_numeric_batch_is_detached_before_pool_await():
    original=[['1000','1.00000000000000000001','1.00000000000000000001','1.00000000000000000001','1.00000000000000000001','1e-1000','0']]
    class Mutating(Pool):
        @asynccontextmanager
        async def acquire(self):
            self.acquired+=1;original[0][1]='999';original[0][5]='999';original.append(row('2000'));yield self.c
    pool=Mutating();await market_backfill.store_kline_page(pool,'BTCUSDT',original)
    assert len(pool.c.rows)==1 and pool.c.rows[0][2]==Decimal('1.00000000000000000001') and pool.c.rows[0][6]==Decimal('1e-1000')

@pytest.mark.asyncio
async def test_exact_storage_codec_preserves_hostile_decimal_context():
    pool=Pool()
    with localcontext() as context:
        context.prec=2;context.Emax=2;context.Emin=-2
        for signal in context.traps:context.traps[signal]=True
        context.clear_flags()
        await market_backfill.store_kline_page(pool,'BTCUSDT',[['10000000000001','1.10000000000000000001','1.10000000000000000001','1.10000000000000000001','1.10000000000000000001','1e-1000','0']])
        assert pool.c.rows[0][2]==Decimal('1.10000000000000000001') and pool.c.rows[0][6]==Decimal('1e-1000')
        assert not any(context.flags.values())
