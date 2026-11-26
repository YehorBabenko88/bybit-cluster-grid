"""Retained internal-gap obligation on a literal frozen historical fixture."""
from contextlib import closing
import sqlite3
from market_data.sqlite_history import HistoricalMarketReader

def test_coverage_detects_internal_gap(tmp_path):
 path=tmp_path/'m.db'
 with closing(sqlite3.connect(path)) as db,db:
  db.execute('CREATE TABLE candles(symbol TEXT,timeframe TEXT,open_time INTEGER,open REAL,high REAL,low REAL,close REAL,volume REAL,turnover REAL,complete INTEGER,PRIMARY KEY(symbol,timeframe,open_time))')
  db.executemany('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)',[
   ('BTCUSDT','1m',stamp,1,1,1,1,1,None,1) for stamp in (0,60000,180000)])
 before=path.read_bytes();s=HistoricalMarketReader.open_snapshot(path)
 try:
  cov=s.coverage('BTCUSDT')
  assert cov.earliest==0 and cov.latest==180000 and cov.count==3
  assert [(g.start,g.end) for g in cov.gaps]==[(120000,120000)]
 finally:s.close()
 assert path.read_bytes()==before
 assert list(tmp_path.iterdir())==[path]
