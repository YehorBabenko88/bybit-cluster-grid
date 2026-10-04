import asyncio,sqlite3,uuid
from datetime import datetime,timezone,timedelta
from grid.strattester_dataset_export import export_market_dataset
from grid.config import settings


class Pool:
    def __init__(self,rows):
        self.rows=rows;self.calls=[]
    async def fetch(self,sql,*args):
        return self.rows
    async def execute(self,sql,*args):
        self.calls.append((sql,args));return "INSERT 0 1" if sql.lstrip().startswith("INSERT") else "UPDATE 1"


def _row(symbol,minute):
    ts=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=minute)
    return {"symbol":symbol,"ts":ts,"open":100+minute,"high":101+minute,
            "low":99+minute,"close":100.5+minute,"buy_volume":2,"sell_volume":3}


def test_export_market_dataset_builds_contiguous_strattester_sqlite(tmp_path,monkeypatch):
    rows=[_row("BTCUSDT",i) for i in range(3)]
    p=Pool(rows);captured={}
    monkeypatch.setattr(settings,"content_cache_root",str(tmp_path/"cache"))
    async def fake_publish(pool,path,artifact_type,metadata,reusable):
        con=sqlite3.connect(path)
        try:
            captured["rows"]=con.execute("SELECT symbol,open_time,volume FROM candles ORDER BY open_time").fetchall()
            captured["format"]=con.execute("SELECT value FROM schema_meta WHERE key='dataset_format'").fetchone()[0]
        finally:
            con.close()
        return {"id":str(uuid.UUID(int=7)),"sha256":"a"*64}
    monkeypatch.setattr("grid.strattester_dataset_export.publish_compute_artifact",fake_publish)
    async def run():
        out=await export_market_dataset(p,symbols=["BTCUSDT"],
            start_ts=datetime(2026,1,1,tzinfo=timezone.utc),
            end_ts=datetime(2026,1,1,0,2,tzinfo=timezone.utc))
        assert out["sample_count"]==3
        assert len(out["dataset_hash"])==64
        assert captured["format"]=="strattester-sqlite-v1"
        assert captured["rows"][0][2]==5.0
        assert any("status='READY'" in sql for sql,_ in p.calls)
    asyncio.run(run())


def test_export_market_dataset_rejects_gaps(tmp_path,monkeypatch):
    p=Pool([_row("BTCUSDT",0),_row("BTCUSDT",2)])
    monkeypatch.setattr(settings,"content_cache_root",str(tmp_path/"cache"))
    async def run():
        try:
            await export_market_dataset(p,symbols=["BTCUSDT"],
                start_ts=datetime(2026,1,1,tzinfo=timezone.utc),
                end_ts=datetime(2026,1,1,0,2,tzinfo=timezone.utc))
        except ValueError as exc:
            assert "incomplete" in str(exc) or "gap" in str(exc)
        else:
            raise AssertionError("gapped dataset was accepted")
    asyncio.run(run())
