import pytest

from grid.snapshot_partition_contract import (
    PartitionContractError, validate_partitions,
)


def part(**changes):
    item = dict(source_id="shard-a", epoch_id="epoch-1",
                exchange="bybit", market_type="linear", symbol="BTCUSDT",
                dataset="candles", timeframe_ns=60_000_000_000,
                first_event_ns=0, last_event_ns=120,
                knowledge_cutoff_ns=200, row_count=3,
                artifact_sha256="a" * 64)
    item.update(changes)
    return item


def test_valid_disjoint_partitions():
    validate_partitions([part(), part(first_event_ns=121, last_event_ns=180)],
                        expected_epoch="epoch-1")


@pytest.mark.parametrize("change", [
    dict(epoch_id="other"), dict(market_type=""),
    dict(row_count=0), dict(timeframe_ns=True),
    dict(first_event_ns=300), dict(artifact_sha256="bad"),
])
def test_invalid_partition_rejected(change):
    with pytest.raises(PartitionContractError):
        validate_partitions([part(**change)], expected_epoch="epoch-1")


def test_overlap_across_sources_rejected():
    with pytest.raises(PartitionContractError, match="Overlapping"):
        validate_partitions([part(), part(source_id="shard-b",
                                         first_event_ns=100, last_event_ns=180)],
                            expected_epoch="epoch-1")


def test_same_symbol_different_market_types_are_distinct():
    validate_partitions([part(), part(market_type="spot")],
                        expected_epoch="epoch-1")
