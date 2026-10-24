import pytest

from grid.snapshot_coverage_contract import validate_regular_partition_coverage
from grid.snapshot_partition_contract import PartitionContractError


STEP = 60
KEY = ("bybit", "linear", "BTCUSDT", "candles", STEP)


def partition(first, last, **extra):
    data = dict(source_id="shard-1", epoch_id="epoch-1",
                exchange="bybit", market_type="linear", symbol="BTCUSDT",
                dataset="candles", timeframe_ns=STEP,
                first_event_ns=first, last_event_ns=last,
                knowledge_cutoff_ns=300, row_count=(last-first)//STEP+1,
                artifact_sha256="a"*64)
    data.update(extra)
    return data


def test_contiguous_coverage():
    validate_regular_partition_coverage(
        [partition(0, 60), partition(120, 180)],
        expected_epoch="epoch-1", expected_ranges={KEY: (0, 180)})


def test_gap_rejected():
    with pytest.raises(PartitionContractError, match="Missing"):
        validate_regular_partition_coverage(
            [partition(0, 60), partition(180, 240)],
            expected_epoch="epoch-1", expected_ranges={KEY: (0, 240)})


def test_false_row_count_rejected():
    with pytest.raises(PartitionContractError, match="Row count"):
        validate_regular_partition_coverage(
            [partition(0, 120, row_count=2)],
            expected_epoch="epoch-1", expected_ranges={KEY: (0, 120)})


def test_missing_source_range_rejected():
    with pytest.raises(PartitionContractError, match="Missing"):
        validate_regular_partition_coverage(
            [partition(0, 60)], expected_epoch="epoch-1",
            expected_ranges={KEY: (0, 60), ("bybit","spot","BTCUSDT","candles",60): (0,60)})
