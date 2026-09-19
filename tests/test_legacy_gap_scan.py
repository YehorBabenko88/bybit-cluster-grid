import sqlite3
from grid.legacy_gap_scan import scan_symbol,append_tail_gap
def test_detects_internal_and_tail_gaps():
    c=sqlite3.connect(":memory:")
    c.execute("create table candles(symbol text,ts integer)")
    c.executemany("insert into candles values('BTCUSDT',?)",[(0,),(60000,),(180000,)])
    s=scan_symbol(c,"BTCUSDT",180000)
    assert s["gap_minutes"]==1 and s["gaps"][0].start_ms==120000
    s=append_tail_gap(s,300000)
    assert s["gap_minutes"]==3 and s["gaps"][-1].kind=="TAIL"
