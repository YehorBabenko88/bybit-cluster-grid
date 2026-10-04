import asyncio,uuid
from grid.strattester_bridge import finalize_research_run
from grid.strattester_bridge_protocol import make_manifest,aggregate_fingerprint


class Pool:
    def __init__(self,run,rows):
        self.run=run;self.rows=rows;self.updates=[]
    async def fetchrow(self,sql,*args):
        if "FROM research_runs" in sql:return self.run
        return None
    async def fetch(self,sql,*args):
        if "FROM research_shards" in sql:return self.rows
        return []
    async def execute(self,sql,*args):
        self.updates.append((sql,args));return "UPDATE 1"


def _manifest(job_id):
    return make_manifest(run_id="run-1",job_id=job_id,job_type="strategy_backtest",
        dataset_hash="dataset-hash",code_version="v1",config={"seed":1},
        input_spec={"symbol":job_id},result={"job":job_id})


def test_complete_run_is_finalized_into_one_immutable_artifact(monkeypatch):
    m1=_manifest("s1");m2=_manifest("s2")
    run={"id":"run-1","kind":"backtest","dataset_id":"ds-1","dataset_hash":"dataset-hash",
         "config_hash":m1["config_hash"],"strattester_version":"v1",
         "status":"COMPLETE","aggregate_fingerprint":None,"result_artifact_id":None}
    rows=[
      {"id":"s2","job_type":"strategy_backtest","shard_key":"b","result_manifest":m2,"result_hash":m2["result_hash"]},
      {"id":"s1","job_type":"strategy_backtest","shard_key":"a","result_manifest":m1,"result_hash":m1["result_hash"]},
    ]
    captured={}
    async def fake_publish(pool,data,artifact_type,metadata,reusable):
        captured["data"]=bytes(data);captured["metadata"]=metadata
        return {"id":str(uuid.UUID(int=1)),"sha256":"f"*64}
    monkeypatch.setattr("grid.strattester_bridge.publish_compute_bytes",fake_publish)
    async def run_test():
        p=Pool(run,rows)
        out=await finalize_research_run(p,"run-1")
        assert out["aggregate_fingerprint"]==aggregate_fingerprint([m2,m1])
        assert out["result_artifact_id"]==str(uuid.UUID(int=1))
        assert b'"shards"' in captured["data"]
        assert any("result_artifact_id" in sql for sql,_ in p.updates)
    asyncio.run(run_test())


def test_incomplete_manifest_set_is_not_finalized(monkeypatch):
    run={"id":"run-1","kind":"backtest","dataset_id":"ds-1","dataset_hash":"dataset-hash",
         "config_hash":"x","strattester_version":"v1","status":"COMPLETE",
         "aggregate_fingerprint":None,"result_artifact_id":None}
    rows=[{"id":"s1","job_type":"strategy_backtest","shard_key":"a",
           "result_manifest":None,"result_hash":None}]
    async def run_test():
        p=Pool(run,rows)
        assert await finalize_research_run(p,"run-1") is None
    asyncio.run(run_test())
