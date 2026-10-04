import pytest
from grid.strattester_bridge import validate_shard_dag,validate_distributed_input,strategy_backtest_shards


def test_research_dag_accepts_valid_dependencies():
    shards=[
        {"shard_key":"history","job_type":"history_sync"},
        {"shard_key":"features","job_type":"feature_build","depends_on":["history"]},
        {"shard_key":"backtest","job_type":"strategy_backtest","depends_on":["features"]},
    ]
    assert set(validate_shard_dag(shards))=={"history","features","backtest"}


def test_research_dag_rejects_unknown_dependency():
    with pytest.raises(ValueError,match="unknown dependency"):
        validate_shard_dag([{"shard_key":"a","job_type":"x","depends_on":["missing"]}])


def test_research_dag_rejects_cycle():
    shards=[
        {"shard_key":"a","job_type":"x","depends_on":["b"]},
        {"shard_key":"b","job_type":"x","depends_on":["a"]},
    ]
    with pytest.raises(ValueError,match="cycle"):
        validate_shard_dag(shards)


def test_research_dag_rejects_empty_run():
    with pytest.raises(ValueError,match="at least one shard"):
        validate_shard_dag([])


def test_distributed_backtest_requires_content_hash_and_rejects_local_paths():
    good={"dataset_sha256":"a"*64,"symbol":"BTCUSDT","strategy":"legacy_grid"}
    assert validate_distributed_input("strategy_backtest",good)==good
    with pytest.raises(ValueError,match="dataset_sha256"):
        validate_distributed_input("strategy_backtest",{"symbol":"BTCUSDT"})
    with pytest.raises(ValueError,match="worker-local"):
        validate_distributed_input("strategy_backtest",{"dataset_sha256":"a"*64,"local_market_db":"C:/x.db"})


def test_strategy_backtest_shards_are_deterministic_cartesian_product():
    shards=strategy_backtest_shards(symbols=["ETHUSDT","BTCUSDT","BTCUSDT"],
        strategies=["legacy_grid","legacy_grid","poc"],start_ms=0,end_ms=120000)
    assert [x["shard_key"] for x in shards]==[
        "strategy:legacy_grid:symbol:BTCUSDT",
        "strategy:legacy_grid:symbol:ETHUSDT",
        "strategy:poc:symbol:BTCUSDT",
        "strategy:poc:symbol:ETHUSDT",
    ]
    assert all(x["job_type"]=="strategy_backtest" for x in shards)
    assert all(x["input_spec"]["start_ms"]==0 and x["input_spec"]["end_ms"]==120000 for x in shards)
