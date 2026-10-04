import pytest
from grid.strattester_bridge import validate_shard_dag


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
