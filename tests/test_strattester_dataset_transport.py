import asyncio
from pathlib import Path
from grid.content_cache import ContentAddressedCache
from grid.strattester_compute_worker import _prepare_dataset_input
from grid.strattester_bridge_protocol import input_digest
from grid.config import settings


class NoNetwork:
    def get(self,*args,**kwargs):
        raise AssertionError("network should not be used for cache hit")


def test_cached_dataset_is_materialized_without_changing_logical_input(tmp_path,monkeypatch):
    cache_root=tmp_path/"cache"
    source=tmp_path/"dataset.db";source.write_bytes(b"sqlite-dataset-bytes")
    item=ContentAddressedCache(cache_root).put(source)
    monkeypatch.setattr(settings,"content_cache_root",str(cache_root))
    payload={"job_type":"strategy_backtest","input_spec":{
        "dataset_sha256":item["sha256"],"symbol":"BTCUSDT","strategy":"legacy_grid",
        "start_ms":0,"end_ms":60_000}}
    before=input_digest(payload["input_spec"])
    async def run():
        out=await _prepare_dataset_input(NoNetwork(),payload,tmp_path/"work")
        spec=out["input_spec"]
        assert Path(spec["local_market_db"]).read_bytes()==source.read_bytes()
        assert spec["local_results_db"].endswith("results.db")
        assert input_digest(spec)==before
    (tmp_path/"work").mkdir()
    asyncio.run(run())
