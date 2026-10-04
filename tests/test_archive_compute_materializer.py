import asyncio
from datetime import date,datetime,timezone
from grid.archive_derived_artifact import write_derived_artifact
from grid.archive_compute_materializer import materialize_archive_compute_results
from grid.content_cache import ContentAddressedCache


class Pool:
    def __init__(self,row):self.row=row;self.calls=[]
    async def fetch(self,sql,*args):return [self.row]
    async def execute(self,sql,*args):
        self.calls.append((sql,args));return "UPDATE 1"


def _row():
    return {"symbol":"BTCUSDT","ts":datetime(2026,1,1,tzinfo=timezone.utc),
            "open":100.0,"high":101.0,"low":99.0,"close":100.5,
            "buy_volume":2.0,"sell_volume":1.0,"delta":1.0,"trade_count":3,
            "poc_price":100.0,
            "levels":{100.0:{"buy":2.0,"sell":1.0,"buy_count":2,"sell_count":1}}}


def test_manifest_mismatch_is_rejected_before_database_materialization(tmp_path,monkeypatch):
    cache=ContentAddressedCache(tmp_path/"cache")
    built=write_derived_artifact(tmp_path/"d.gz",[_row()],
        {"symbol":"BTCUSDT","archive_date":"2026-01-01","tick_size":0.5,"source_sha256":"s"})
    cached=cache.put(built["path"],built["sha256"])
    manifest={"source_sha256":"s","derived_artifact_sha256":cached["sha256"],
              "source_rows":999,"derived_candles":1,"derived_footprint_rows":1,
              "min_ts":built["min_ts"],"max_ts":built["max_ts"]}
    job={"id":"j1","symbol":"BTCUSDT","archive_date":date(2026,1,1),"tick_size":0.5,
         "result_manifest":manifest,"derived_artifact_id":"a1",
         "storage_uri":"content://sha256/"+cached["sha256"],"artifact_status":"ACTIVE","artifact_bytes":cached["bytes"]}
    called={"materialize":False}
    async def no_materialize(*args,**kwargs):
        called["materialize"]=True
        raise AssertionError("must not materialize invalid artifact")
    monkeypatch.setattr("grid.archive_compute_materializer.materialize_archive_stream",no_materialize)
    async def run():
        p=Pool(job)
        assert await materialize_archive_compute_results(p,tmp_path/"cache")==0
        assert called["materialize"] is False
        assert any("materialize_error" in sql for sql,_ in p.calls)
    asyncio.run(run())
