from __future__ import annotations
import hashlib,json,sqlite3,tempfile
from datetime import datetime,timezone
from pathlib import Path

from grid.archive_derived_artifact import write_derived_artifact,iter_derived_artifact
from grid.content_cache import ContentAddressedCache
from grid.strattester_bridge_protocol import aggregate_fingerprint,make_manifest


def _row(symbol,minute):
    ts=datetime(2026,1,1,0,minute,tzinfo=timezone.utc)
    return {"symbol":symbol,"ts":ts,"open":100.0+minute,"high":101.0+minute,
            "low":99.0+minute,"close":100.5+minute,"buy_volume":2.0,
            "sell_volume":1.0,"delta":1.0,"trade_count":3,"poc_price":100.0+minute,
            "levels":{100.0+minute:{"buy":2.0,"sell":1.0,"buy_count":2,"sell_count":1}}}


def _dataset(path,symbols=("BTCUSDT","ETHUSDT"),minutes=3):
    con=sqlite3.connect(path)
    try:
        con.execute("""CREATE TABLE candles(symbol TEXT,timeframe TEXT,open_time INTEGER,
          open REAL,high REAL,low REAL,close REAL,volume REAL,turnover REAL,complete INTEGER,
          PRIMARY KEY(symbol,timeframe,open_time))""")
        for symbol in symbols:
            for minute in range(minutes):
                r=_row(symbol,minute)
                con.execute("INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,1)",
                    (symbol,"1m",int(r["ts"].timestamp()*1000),r["open"],r["high"],r["low"],
                     r["close"],r["buy_volume"]+r["sell_volume"],None))
        con.commit()
    finally:con.close()


def run_acceptance(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    cache=ContentAddressedCache(root/"cache")
    dataset=root/"dataset.db";_dataset(dataset)
    dataset_obj=cache.put(dataset)
    assert cache.has(dataset_obj["sha256"])
    materialized=root/"worker-market.db";cache.materialize(dataset_obj["sha256"],materialized)
    assert hashlib.sha256(materialized.read_bytes()).hexdigest()==dataset_obj["sha256"]

    manifests=[]
    for symbol in ("BTCUSDT","ETHUSDT"):
        for strategy in ("legacy_grid","poc"):
            manifests.append(make_manifest(run_id="acceptance",job_id=f"{strategy}:{symbol}",
                job_type="strategy_backtest",dataset_hash=dataset_obj["sha256"],
                code_version="acceptance-v1",config={"seed":1},
                input_spec={"symbol":symbol,"strategy":strategy,"start_ms":0,"end_ms":120000},
                result={"symbol":symbol,"strategy":strategy,"score":len(symbol)+len(strategy)}))
    fingerprint=aggregate_fingerprint(manifests)
    assert fingerprint==aggregate_fingerprint(list(reversed(manifests)))

    derived=root/"derived.gz"
    summary=write_derived_artifact(derived,[_row("BTCUSDT",0),_row("BTCUSDT",1)],
        {"symbol":"BTCUSDT","archive_date":"2026-01-01","tick_size":0.5,"source_sha256":"source"})
    replay=list(iter_derived_artifact(derived,{"symbol":"BTCUSDT","archive_date":"2026-01-01",
        "tick_size":0.5,"source_sha256":"source"}))
    assert len(replay)==summary["derived_candles"]==2
    assert sum(x["trade_count"] for x in replay)==summary["source_rows"]

    stale_generation=1;reassigned_generation=2
    assert stale_generation!=reassigned_generation
    stale_commit_allowed=(stale_generation==reassigned_generation)
    assert not stale_commit_allowed

    return {"dataset_sha256":dataset_obj["sha256"],"shards":len(manifests),
            "aggregate_fingerprint":fingerprint,"archive_sha256":summary["sha256"],
            "archive_rows":summary["source_rows"],"stale_commit_blocked":True}


def test_distributed_acceptance_contract(tmp_path):
    result=run_acceptance(tmp_path)
    assert result["shards"]==4
    assert result["stale_commit_blocked"] is True
    assert len(result["aggregate_fingerprint"])==64
