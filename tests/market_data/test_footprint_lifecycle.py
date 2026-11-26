from decimal import Decimal
from decimal import Context, Decimal, localcontext
import time
import pytest
from market_data.provenance import minute_record, producer

def test_event_time_ohlc_duplicate_and_late_trades():
    from market_data.footprint_state import FootprintBuilder
    from market_data.public_trades import Trade
    b=FootprintBuilder(1)
    assert b.add(Trade(symbol="BTCUSDT",ts_ms=2000,price=2,qty=1,side="Buy",trade_id="b"))
    assert b.add(Trade(symbol="BTCUSDT",ts_ms=1000,price=1,qty=1,side="Buy",trade_id="a"))
    assert not b.add(Trade(symbol="BTCUSDT",ts_ms=1000,price=1,qty=1,side="Buy",trade_id="a"))
    r=b.pop_closed(60000)[0]
    assert (r['open'],r['close'],r['trade_count'])==(1,2,2)
    assert not b.add(Trade(symbol="BTCUSDT",ts_ms=3000,price=3,qty=1,side="Buy",trade_id="c"))



def test_actual_builder_decimal_tick_rounding_retains_integrity():
    from market_data.footprint_state import FootprintBuilder
    from market_data.public_trades import Trade
    b=FootprintBuilder(.1)
    b.add(Trade(symbol='BTCUSDT',ts_ms=1000,price=Decimal("0.3"),qty=1,side='Buy',trade_id='decimal'))
    r=b.pop_closed(60000)[0]
    r['source_provenance']=producer('fixture','a'*40,'wss://stream.bybit.com/v5/public/linear')
    assert minute_record(r,int(time.time()*1000),'fixture')['status']=='PARTIAL'


def test_explicit_source_tie_policies_and_hostile_context():
    from market_data.footprint_state import FootprintBuilder
    from market_data.public_trades import Trade
    context = Context(prec=1, Emin=-2, Emax=2)
    for signal in context.traps:
        context.traps[signal] = True
    with localcontext(context) as caller:
        builder = FootprintBuilder("0.1")
        builder.add(Trade("BTCUSDT",1000,"0.25","100.00001","Buy","first"))
        builder.add(Trade("BTCUSDT",2000,"0.45","100.00001","Sell","second"))
        row = builder.pop_closed(60000)[0]
        assert not any(caller.flags.values())
    assert row["poc_price"] == 0.2
    assert [level["price"] for level in row["levels"]] == [0.2,0.4]
    assert row["buy_volume"] == 100.00001
    assert row["sell_volume"] == 100.00001
    assert row["delta"] == 0


def test_nonzero_volume_cannot_underflow_historical_dto_or_advance_watermark():
    from market_data.footprint_state import FootprintBuilder
    from market_data.public_trades import Trade
    builder = FootprintBuilder('1')
    assert builder.add(Trade('BTCUSDT', 1000, '1', '1e-1000', 'Buy', 'tiny'))
    with pytest.raises(ValueError, match='represent amount'):
        builder.pop_closed(60000)
    assert ('BTCUSDT', 0) in builder.buckets
    assert builder.finalized_through_ms == {}


def test_bad_second_bucket_never_discards_an_earlier_unreturned_row():
    from market_data.footprint_state import FootprintBuilder
    from market_data.public_trades import Trade
    builder = FootprintBuilder('1')
    assert builder.add(Trade('BTCUSDT', 1000, '1', '1', 'Buy', 'valid'))
    assert builder.add(Trade('BTCUSDT', 60001, '1', '1e1000', 'Buy', 'overflow'))
    with pytest.raises(ValueError, match='represent amount'):
        builder.pop_closed(120000)
    assert set(builder.buckets) == {('BTCUSDT', 0), ('BTCUSDT', 60000)}
    assert builder.finalized_through_ms == {}
