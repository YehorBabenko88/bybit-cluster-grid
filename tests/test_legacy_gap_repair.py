import sqlite3
from grid.legacy_gap_repair import merge_rows
def test_repair_inserts_missing_but_refuses_conflicting_existing_candle():
    c=sqlite3.connect(":memory:")
    c.execute("""create table candles(symbol text,ts integer,open text,high text,low text,
      close text,volume text,turnover text,primary key(symbol,ts))""")
    c.execute("insert into candles values(?,?,?,?,?,?,?,?)",("BTCUSDT",0,"1","2","0","1","10","11"))
    assert merge_rows(c,"BTCUSDT",[[60000,"1","3","1","2","12","13"]])==1
    try:
        merge_rows(c,"BTCUSDT",[[0,"9","9","9","9","9","9"]])
        assert False
    except RuntimeError as e:
        assert "LEGACY_OHLCV_CONFLICT" in str(e)
